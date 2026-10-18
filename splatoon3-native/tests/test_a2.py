#!/usr/bin/env python3
"""A2 native loadout readback, same-distance swim time and full-tank air slashes."""
import argparse
import datetime
import json
from pathlib import Path
import re
import sys
import traceback
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rl import NativeParallelEnv
from rl.loadout import uniform_loadout,encode_loadout
from probe_a1_time import neutral,sample_hosts
from a2_metrics import full_tank_capacity


def main(args):
    out=ROOT/'work/tests'/datetime.datetime.now().strftime('a2-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    baseline=uniform_loadout('quick_super_jump');boosted=uniform_loadout('ink_saver_main')
    boosted['head']=dict(main='swim_speed_up',subs=['swim_speed_up']*3)
    result=dict(passed=False,full_a2_passed=False,errors=[],artifacts=str(out),rounds=[])
    log=(out/'steps.jsonl').open('w');env=None
    try:
        for swapped in (False,True):
            configs=[boosted,baseline] if swapped else [baseline,boosted]
            env=NativeParallelEnv(players=2,weapons=[8000]*2,loadouts=configs,reward_fn=None,
                                  timeout=args.timeout,step_timeout=30,state_dump=True)
            _,infos=env.reset();agents=env.possible_agents;number=0
            round_result=dict(swapped=swapped,session=str(env.session.out),loadouts=configs);result['rounds'].append(round_result)
            def actions():return {a:neutral() for a in agents}
            def step(action,label,frames=15):
                nonlocal infos,number
                env.frame_skip=frames;_,_,_,truncated,infos=env.step(action);number+=1
                if any(truncated.values()):raise TimeoutError('A2 deadline')
                for info in infos.values():
                    if info['phase']!=1:raise AssertionError('A2 measurement exceeded game duration')
                    if not info['position_valid'] or not info['ink_valid']:raise AssertionError('native sample expired')
                log.write(json.dumps(dict(swapped=swapped,step=number,label=label,infos=infos))+'\n');log.flush()
                return infos
            for _ in range(30):step(actions(),'warmup')
            readbacks=[]
            for n in range(2):
                rows=re.findall(r'SPL3_GEAR piece=(\d+) id=(-?\d+) main=(\d+) subs=(-?\d+),(-?\d+),(-?\d+) count=(\d+) override=(\d+)',env.session.text(n))
                actual={int(row[0]):list(map(int,row[2:6])) for row in rows if row[6:] == ('3','1')}
                expected=list(map(int,encode_loadout(configs[n]).split(',')))
                if actual!={p:expected[p*4:p*4+4] for p in range(3)}:raise AssertionError(f'player-{n}: native gear readback {actual} != {expected}')
                if 'backend=owned_read' not in env.session.text(n):raise AssertionError('loadout did not use native owned-row construction')
                readbacks.append(actual)
            round_result['readbacks']=readbacks
            # Raise the camera before stationary air swings. No target or aim
            # accuracy is needed to measure the game's actual ink deductions.
            a=actions()
            for v in a.values():v['gyro'][0]=-.08
            step(a,'look-up',45);step(actions(),'settle',60)
            if min(i['ink'] for i in infos.values())<.999:raise AssertionError('air-swing test did not start with full ink')
            counts={a:0 for a in agents};dry={a:0 for a in agents};costs={a:[] for a in agents};ink_history=[]
            for cycle in range(80):
                before={a:infos[a]['ink'] for a in agents};a=actions()
                for agent in agents:a[agent]['buttons'][0]=int(not dry[agent])
                step(a,'air-slash-press',1);step(actions(),'air-slash-release',29)
                losses={a:before[a]-infos[a]['ink'] for a in agents};ink_history.append(dict(cycle=cycle,before=before,after={a:infos[a]['ink'] for a in agents},losses=losses))
                for agent,loss in losses.items():
                    if not dry[agent]:
                        if loss>.005:counts[agent]+=1;costs[agent].append(loss)
                        else:
                            if not costs[agent] or before[agent]>min(costs[agent])*1.15:
                                raise AssertionError('air-slash cadence failed with sufficient ink; not a dry tank')
                            dry[agent]=1
                if min(dry.values())>=1:break
            else:raise AssertionError('full-tank swing count did not reach dry within 80 attempts')
            capacity={a:full_tank_capacity(ink_history,a) for a in agents}
            positive_deductions=counts;counts={a:v['full_cost_swings'] for a,v in capacity.items()}
            round_result['air_slashes']=dict(counts=counts,capacity=capacity,positive_deductions=positive_deductions,
                                             costs=costs,history=ink_history,
                                             stop='complete-cost prefix only; insufficient remainder and later recovery excluded')
            buff_agent=agents[0 if swapped else 1];base_agent=next(a for a in agents if a!=buff_agent)
            if capacity[buff_agent]['normal_cost']>=capacity[base_agent]['normal_cost']*.95:
                raise AssertionError('ink saver did not lower ordinary slash cost by at least 5%')
            if counts[base_agent]<10 or counts[buff_agent]<=counts[base_agent]+1:raise AssertionError('ink saver did not increase full-tank air slashes')
            # Move off the spawn's drop before making a level ink lane.
            a=actions()
            for v in a.values():v['gyro'][0]=.08
            step(a,'restore-camera',45);step(actions(),'settle-camera',30)
            a=actions()
            for v in a.values():v['sticks'][1]=1
            step(a,'leave-spawn-drop',90);step(actions(),'land-on-lane',60)
            # Downward paint prepares the floor; no target aiming is needed.
            a=actions()
            for v in a.values():v['gyro'][0]=.08
            step(a,'look-at-floor',45)
            a=actions()
            for v in a.values():v['buttons'][0]=1
            step(a,'paint-lane',180)
            a=actions()
            for v in a.values():v['buttons'][1]=1
            step(a,'recover-in-ink',180)
            start={a:np.array(infos[a]['position']) for a in agents}
            forward={a:np.array([np.sin(infos[a]['heading']),np.cos(infos[a]['heading'])]) for a in agents}
            samples={a:[(infos[a]['position_sample_frame'],0.)] for a in agents}
            crossings={a:{} for a in agents};trajectory=[]
            for frame in range(1,241):
                a=actions()
                for agent in agents:
                    a[agent]['buttons'][1]=1;a[agent]['sticks'][1]=float(9 not in crossings[agent])
                step(a,'same-distance-swim',1)
                poses={a:infos[a]['position'] for a in agents};trajectory.append(dict(frame=frame,infos=infos))
                for agent in agents:
                    pos=np.array(poses[agent]);delta=pos[[0,2]]-start[agent][[0,2]]
                    distance=float(delta@forward[agent]);stamp=infos[agent]['position_sample_frame']
                    old_stamp,old_distance=samples[agent][-1]
                    if stamp<=old_stamp:continue
                    samples[agent].append((stamp,distance))
                    if 3<=distance<=9:
                        sideways=abs(float(delta@np.array([forward[agent][1],-forward[agent][0]])))
                        if abs(pos[1]-start[agent][1])>.1 or sideways>.1:
                            raise AssertionError('swim measurement left the flat straight lane')
                    for threshold in (3,9):
                        if old_distance<threshold<=distance and threshold not in crossings[agent]:
                            crossings[agent][threshold]=old_stamp+(stamp-old_stamp)*(threshold-old_distance)/(distance-old_distance)
                if all(9 in c for c in crossings.values()):break
            round_result['swim']=dict(distance=6,start_offset=3,end_offset=9,
                                      crossings=crossings,samples=samples,trajectory=trajectory)
            if not all(len(c)==2 for c in crossings.values()):raise AssertionError('painted lane did not permit both same-distance swims')
            durations={a:c[9]-c[3] for a,c in crossings.items()}
            speeds={a:6/v for a,v in durations.items()}
            round_result['swim'].update(frames=durations,seconds={a:v/60 for a,v in durations.items()},speeds=speeds)
            # Native packets are less frequent than presents. Interpolate using
            # their actual sample frames, not the enclosing ACK timestamp.
            if min(speeds.values())<.14:raise AssertionError('lane motion did not reach native ink-swimming speed')
            if durations[buff_agent]>=durations[base_agent]*.97:
                raise AssertionError('swim speed skill did not reduce same-distance time by at least 3%')
            env.close();env=None
        result['passed']=result['full_a2_passed']=True
    except BaseException as error:
        result['errors'].append(repr(error));result['traceback']=traceback.format_exc()
        if env and env.session:sample_hosts(env.session,out)
    finally:
        if env:
            try:env.close()
            except BaseException as error:result['errors'].append('cleanup: '+repr(error))
        log.close()
    result['passed']=result['full_a2_passed']=result['passed'] and not result['errors']
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--timeout',type=float,default=2400)
    raise SystemExit(main(parser.parse_args()))
