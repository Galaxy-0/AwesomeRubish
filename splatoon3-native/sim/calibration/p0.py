"""Time-bounded P0 native window, fresh accepted default host per case.

Only calibration owns these inputs. No T1 runner/policy source is executed.
Existing Session resource guards remain active; never signal foreign rooms.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import datetime
import json
import os
from pathlib import Path
import time
import traceback

from .native import ROOT,make_lab,active_native
from .plan import loadout


def controls():
    from sim.engine import neutral
    return {f'player_{i}':neutral() for i in (0,1)}


def sequence(lab,actions,label,frames):
    for _ in range(frames):lab.step(actions,label,1)


def opening(lab,case):
    a=controls();a['player_1']['sticks'][1]=.85
    sequence(lab,a,'measure-opening-neutral-vs-steer',180)
    sequence(lab,controls(),'measure-opening-settle',60)
    lab.result['landing']={str(i):lab.info(i) for i in (0,1)};lab.save()
    for magnitude in (.5,.85,1.):
        a=controls()
        for value in a.values():value['sticks'][1]=magnitude
        sequence(lab,a,f'measure-straight-{magnitude}',45)
        sequence(lab,controls(),f'measure-brake-{magnitude}',25)
    a=controls()
    for value in a.values():value['sticks'][1]=.85;value['buttons'][4]=1
    sequence(lab,a,'measure-jump-edge',1)
    for value in a.values():value['buttons'][4]=0
    sequence(lab,a,'measure-jump-and-ledge',100)
    sequence(lab,controls(),'measure-landing-settle',60)
    # Ordinary controller input deliberately walks off the map. No health or
    # pose writes; retain failure if the geometry prevents reaching the edge.
    death=None
    for f in range(720):
        a=controls();a['player_0']['sticks'][0]=1.;a['player_0']['sticks'][1]=.25
        a['player_0']['buttons'][4]=int(f%90==0)
        lab.step(a,'measure-walk-to-environmental-death',1)
        i=lab.info(0)
        if i.get('alive_valid') and not i['alive']:
            death=i;break
    lab.result['environmental_death']=death;lab.save()
    if death is None:
        lab.result['respawn_status']='not_observed_no_death';return
    launched=False
    for f in range(1000):
        a=controls();i=lab.info(0)
        if i.get('hp_valid') and i['hp']>.99 and i.get('position_valid') and i['position'][1]>20:
            a['player_0']['buttons'][0]=int(f%30==0)
        lab.step(a,'measure-respawn-and-launch-pulses',1)
        i=lab.info(0)
        if i.get('alive_valid') and i['alive']:
            launched=True;break
    lab.result['respawn_status']='launched' if launched else 'no_launch_within_budget'
    if launched:sequence(lab,controls(),'measure-respawn-flight-and-land',240)


def run_case(job):
    case,out,deadline=job;directory=Path(out)/case['id'];directory.mkdir(parents=True,exist_ok=False)
    status=dict(id=case['id'],kind=case['kind'],stage=case['stage'],started_wall=time.time(),status='failed',errors=[])
    lab=None
    try:
        if (Path(out)/'STOP').exists():raise TimeoutError('owned batch cancellation before admission')
        if time.time()>deadline:raise TimeoutError('calibration window ended before admission')
        lab=make_lab(case,directory,min(1500,max(1,deadline-time.time())))
        original=lab.step
        def checkpoint():
            if (Path(out)/'STOP').exists():raise TimeoutError('owned batch cancellation')
            if time.time()>deadline:raise TimeoutError('calibration window ended')
        lab.checkpoint=checkpoint
        def bounded(actions,label,frames=1):
            checkpoint()
            return original(actions,label,frames)
        lab.step=bounded
        lab.start()
        if case['kind']=='p0_opening':opening(lab,case)
        elif case['kind']=='p0_paint':
            from .paint import collect
            collect(lab,case)
        elif case['kind']in('p0_motion','p0_scan','p0_combat','p0_bends'):
            from .probes import collect
            collect(lab,case)
        else:
            from .native import collect
            collect(lab,case)
        lab.result['passed']=True
        status.update(status='collected',session=lab.result['session'],owned_pids=lab.result['owned_pids'])
    except BaseException as error:
        status.update(errors=[repr(error)],traceback=traceback.format_exc())
        if lab:lab.result['errors'].append(repr(error))
    finally:
        if lab:
            lab.close()
            if lab.result['errors']:status.update(status='failed',errors=lab.result['errors'])
        status['ended_wall']=time.time()
        (directory/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps(status),flush=True)
    return status


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute-native',action='store_true');p.add_argument('--window',choices=['A7_A8_IDLE'])
    p.add_argument('--phase',choices=['opening','generic'],default='opening')
    p.add_argument('--plan',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--deadline',type=float,required=True,help='Absolute wall-clock epoch; never extended by retries')
    p.add_argument('--parallel',type=int,choices=(1,2,3),default=3)
    a=p.parse_args()
    if not a.execute_native or a.window!='A7_A8_IDLE':p.error('explicit approved native window required')
    out=a.out.resolve()
    if not out.is_relative_to(ROOT/'work'):p.error('raw artifacts must stay under work/')
    if active_native():raise RuntimeError('foreign native activity present; no processes signaled')
    if any(k.startswith('DM_TEST_SPECIAL') for k in os.environ):raise RuntimeError('no test special in calibration')
    from arena.native_runtime import default_runtime,runtime_files
    from sim.parameters import sha256
    runtime=default_runtime();out.mkdir(parents=True,exist_ok=False)
    if a.phase=='opening':
        cases=[dict(id=f'p0-opening-map{s}',kind='p0_opening',stage=s,loadout=loadout('run_speed_up',0),
                    frame_budget=9000,settings=dict(warmup_frames=0)) for s in (1,2,3)]
    else:cases=json.loads(a.plan.read_text())['cases']
    sources=[*runtime_files(runtime),*Path(__file__).parent.glob('*.py'),
             *(ROOT/'tests').glob('*a6*.py'),*(ROOT/'arena/lib').glob('*.py'),
             ROOT/'arena/native_runtime.py',ROOT/'arena/native_session.py',ROOT/'rl/env.py',
             ROOT/'tools/m5_resources.py']
    sources=[p for p in sources if p.exists()]
    sources.extend(p for stage in ('Yunohana','District00','Yagara') for p in
        (ROOT/f'work/arena/maps/{stage}').iterdir() if p.name in ('human.npz','sight.npz','navigation.json'))
    plan=dict(started_wall=time.time(),deadline=a.deadline,parallel=a.parallel,cases=cases,runtime=runtime,
              source_sha256={str(p.relative_to(ROOT)):sha256(p) for p in sources},fresh_process_per_case=True)
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    for path in sources:
        if path.suffix not in ('.py','.json'):continue
        copy=out/'sources'/path.relative_to(ROOT);copy.parent.mkdir(parents=True,exist_ok=True);copy.write_bytes(path.read_bytes())
    import fcntl
    lock=(ROOT/'work/sim/native-calibration.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    import signal
    def request_stop(signum,frame):
        (out/'STOP').touch()
        print('Requested owned batch shutdown; no foreign process signals.',flush=True)
    signal.signal(signal.SIGINT,request_stop);signal.signal(signal.SIGTERM,request_stop)
    results=[]
    with ProcessPoolExecutor(max_workers=a.parallel) as pool:
        jobs=[pool.submit(run_case,(case,str(out),a.deadline)) for case in cases]
        for done in as_completed(jobs):
            results.append(done.result())
            (out/'summary.json').write_text(json.dumps(dict(complete=len(results)==len(cases),cases=results),indent=2)+'\n')
    lock.close()


if __name__=='__main__':main()
