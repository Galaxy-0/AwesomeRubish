"""Future-only native collector; imported solely by --execute-native.

No native code is imported at module scope. This file has NOT been run against
the game. The default command only emits the plan. Failures remain evidence.
"""
import datetime
import json
import math
from pathlib import Path
import subprocess
import sys
import traceback

ROOT=Path(__file__).resolve().parents[2]


def active_native():
    rows=subprocess.check_output(['ps','-axo','pid=,comm=,args='],text=True).splitlines()
    return [r.strip() for r in rows if len(r.split(None,2))>=2 and
            (Path(r.split(None,2)[1]).name.startswith('dmhost') or
             any(s in r for s in ('-m tests.test_a5','tests/test_a5.py','-m arena.t1_round','arena/t1_round.py','-m arena.proficiency')))]


def make_lab(case, directory, timeout):
    # Reuse read-only setup/trace methods, with our own current-host manifest.
    # A6 Lab.__init__/close enforce an obsolete protected T1 binary, so they
    # cannot be used after A7 changes the host. No old freeze gate is patched.
    sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'arena/lib'),str(ROOT)]
    from a6_lab import Lab
    from rl import NativeParallelEnv
    from rl.loadout import uniform_loadout
    from atlas import MapAtlas

    class CalibrationLab(Lab):
        def __init__(self):
            self.out=directory;self.out.mkdir(parents=True,exist_ok=True)
            self.stream=(directory/'steps.jsonl').open('w')
            self.result=dict(passed=False,errors=[],artifacts=str(directory),cases=[],
                             collection_only=True,case=case,surface_confirmation='unknown')
            self.loadouts=[case['loadout'],uniform_loadout()]
            self.result['loadouts']=self.loadouts
            self.env=NativeParallelEnv(players=2,stage_id=case['stage'],weapons=[8000]*2,
                loadouts=self.loadouts,frame_skip=1,reward_fn=None,timeout=timeout,step_timeout=150,state_dump=True)
            self.stage=case['stage'];self.atlas=MapAtlas.load(case['stage']);self.count=0
            self.api=None;self.origins={};self.budget=0

        def step(self,actions,label,frames=1):
            if self.budget+frames>case['frame_budget']:
                raise RuntimeError('case controlled-frame budget exhausted; retain partial, no acceptance')
            self.budget+=frames
            if label.startswith('measure') and frames>1:
                infos=None
                for _ in range(frames):infos=super().step(actions,label,1)
                return infos
            return super().step(actions,label,frames)

        def close(self):
            try:self.env.close()  # closes only this room's owned resources
            except Exception as e:self.result['errors'].append('owned-room cleanup: '+repr(e))
            self.stream.close();self.save()

    return CalibrationLab()


def series(lab,action,label,frames):
    # Retain per-present inputs plus both peers' own packet stamps and validity.
    for _ in range(frames):lab.act(0,action,label,1)


def flat(lab,surface='dry'):
    from skills import neutral
    source=(-8.,3.,8.);far=(18.,3.,-8.)
    lab.navigate({0:source,1:far})
    painter=0 if surface=='own' else 1
    if surface!='dry':
        for x in (-10.,-7.,-4.,-1.,2.,5.,8.):
            lab.navigate({painter:(x,3.,8.)});lab.paint_floor(painter)
        if painter==1:lab.navigate({1:far})
        lab.navigate({0:source})
    lab.align(0,(12.,4.1,8.))
    # Human neutral recovery does not add any paint to the dry/enemy lane.
    for _ in range(100):lab.step(lab.actions(),'baseline-rest',6)
    if lab.info(0)['ink']<.999:raise AssertionError('not full ink after neutral recovery')
    lab.capture('surface-before')
    confirmed='unknown'
    if surface=='own':
        a=neutral();a['buttons'][1]=1;series(lab,a,'confirm-own-submergence',12)
        if lab.obs(0)['own'].get('submerged') is True:confirmed='own_at_start'
        lab.step(lab.actions(),'surface-form',12)
    lab.result.update(requested_surface=surface,surface_confirmation=confirmed,
                      surface_note='Procedural paint identity is recorded; dry/enemy require visual/native paint confirmation, never inferred from speed.')


def collect(lab,case):
    from skills import neutral
    from stamper import charge_slash,burst_bomb,zipcaster
    from probe_a6_combat import prepare,trial
    kind=case['kind'];s=case['settings']
    if kind in ('motion','ink','roll'):
        flat(lab,s.get('surface','own' if kind=='roll' else 'dry'))
    if kind=='motion':
        for repeat in range(case['repeats']):
            lab.restore(0,(-8.,3.,8.))
            for magnitude in (.25,.5,.75,1.):
                a=neutral();a['buttons'][1]=int(s['form']=='squid');a['sticks'][1]=magnitude
                series(lab,a,f'measure-{repeat}-accelerate-{magnitude}',45)
                a['sticks'][1]=0.;series(lab,a,f'measure-{repeat}-brake-{magnitude}',45)
                lab.restore(0,(-8.,3.,8.))
            a=neutral();a['buttons'][1]=int(s['form']=='squid');a['sticks'][1]=1.
            series(lab,a,'measure-forward',30);a['sticks'][1]=-1.;series(lab,a,'measure-reversal-no-b',30)
            a=neutral();a['buttons'][4]=1;series(lab,a,'measure-jump-edge',1)
            series(lab,neutral(),'measure-jump-landing',90)
            for axis in ('stick','gyro'):
                a=neutral()
                if axis=='stick':a['sticks'][2]=.5
                else:a['gyro'][2]=.15
                series(lab,a,'measure-turn-'+axis,20);series(lab,neutral(),'measure-turn-stop',30)
    elif kind=='ink':
        for repeat in range(case['repeats']):
            lab.look(0,.85)
            # Human/submerged refill curves are sampled through recovery stop.
            if case['skill']=='ink_saver_sub':
                lab.execute(0,burst_bomb(lab.obs(0)),f'measure-sub-{repeat}')
            else:
                for hold in (1,20,21,30):
                    a=neutral();a['buttons'][0]=1;series(lab,a,f'measure-hold-{hold}',hold)
                    series(lab,neutral(),'measure-release-reserve-refund',40)
            series(lab,neutral(),'measure-human-refill',240)
            # A human-refill trace can already have reached full. Drain again
            # before the submerged curve, rather than sampling a full tank.
            for _ in range(3):
                a=neutral();a['buttons'][0]=1;series(lab,a,'submerged-refill-drain-hold',21)
                series(lab,neutral(),'submerged-refill-drain-release',40)
            a=neutral();a['buttons'][1]=1;series(lab,a,'measure-submerged-refill',240)
            lab.step(lab.actions(),'emerge',12)
    elif kind=='roll':
        for runup in s['runups']:
            for angle in s['angles']:
                lab.restore(0,(-8.,3.,8.));lab.align(0,(12.,4.1,8.))
                a=neutral();a['buttons'][1]=1;series(lab,a,'roll-submerge',12)
                a['sticks'][1]=1.;series(lab,a,f'measure-runup-{runup}',runup)
                a['sticks'][:2]=[math.sin(math.radians(angle)),math.cos(math.radians(angle))]
                a['buttons'][4]=1;series(lab,a,f'measure-reverse-{angle}-b',1)
                a['buttons'][4]=0;series(lab,a,'measure-roll-land',s['travel_frames'])
    elif kind=='surge':
        lab.navigate({0:(0.,3.,8.),1:(18.,3.,-8.)});lab.paint_floor(0)
        for height in (3.8,5.2,7.):
            lab.align(0,(0.,height,4.2))
            for _ in range(3):
                a=neutral();a['buttons'][0]=1;lab.act(0,a,'wall-paint',1);lab.step(lab.actions(),'wall-paint-release',29)
        for charge in s['charges']:
            lab.navigate({0:(0.,3.,8.)});lab.refill(0)
            lab.align(0,(0.,4.1,4.5))
            a=neutral();a['buttons'][1]=1;a['sticks'][1]=1.
            for _ in range(90):
                lab.act(0,a,'climb-to-wall',1)
                if lab.info(0)['position'][1]>=4.8:break
            else:raise AssertionError('painted-wall contact not established')
            a['sticks'][1]=0.;a['buttons'][4]=1;series(lab,a,f'measure-charge-{charge}',charge)
            a['buttons'][4]=0;a['sticks'][1]=1.;series(lab,a,'measure-wall-release',60)
            a['sticks'][1]=-1.;series(lab,a,'leave-wall',60);series(lab,neutral(),'land',60)
    elif kind=='terrain':
        points=lab.atlas.points;choices=[]
        for i,edges in enumerate(lab.atlas.edges):
            for j in edges:
                dy=abs(points[i][1]-points[j][1]);dx=math.dist(points[i],points[j])
                if (.03<dy<.2 if s['shape']=='step' else .2<=dy<1.3) and .4<dx<2.:
                    choices.append((i,j))
        if not choices:raise AssertionError('no geometry candidate; do not invent ramp/step label')
        i,j=choices[len(choices)//2];start,end=points[i],points[j]
        lab.result['geometry_candidate']=dict(start=start,end=end,label_unverified=s['shape'])
        # The atlas edge is only a candidate. Images and native trajectories
        # must establish whether it was a slope, step or blocked prop.
        for repeat in range(case['repeats']):
            lab.navigate({0:start});lab.align(0,(end[0],end[1]+1.1,end[2]));lab.capture('terrain-before')
            a=neutral();a['sticks'][1]=1.;series(lab,a,f'measure-traverse-{repeat}',30)
            series(lab,neutral(),'measure-support-settle',60);lab.capture('terrain-after')
    elif kind in ('contact','recovery','dash','bomb'):
        for repeat in range(case['repeats']):
            distance=s.get('distance',6.)
            prepare(lab,distance,source=(8.,3.,8.),precise_pose=True)
            factory=(lambda obs:burst_bomb(obs)) if kind=='bomb' else (lambda obs:charge_slash(obs,21 if kind=='dash' else 1,dash=kind=='dash'))
            trial(lab,f'measure-{kind}-{repeat}',factory)
            if kind=='recovery':series(lab,neutral(),'measure-peer-hp-recovery',240)
    elif kind=='zip':
        # Natural fill only. No DM_TEST_SPECIAL environment variable is set.
        from probe_a6_movement import walking_fill
        walking_fill(lab)
        lab.execute(0,zipcaster(lab.obs(0)), 'measure-natural-zip')
        series(lab,neutral(),'measure-zip-return',720)
    else:raise ValueError('unknown calibration kind')
    lab.capture('case-after')


def execute(plan,out,only,timeout):
    import fcntl
    lock_path=ROOT/'work/sim/native-calibration.lock'
    lock_path.parent.mkdir(parents=True,exist_ok=True)
    with lock_path.open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('another calibration collector holds the serial-room lock')
        return _execute(plan,out,only,timeout)


def _execute(plan,out,only,timeout):
    active=active_native()
    if active:raise RuntimeError('scheduled native window is busy; no processes signaled: '+repr(active))
    if any(k.startswith('DM_TEST_SPECIAL') for k in __import__('os').environ):
        raise RuntimeError('natural special calibration cannot use test-special switches')
    from sim.parameters import sha256
    out.mkdir(parents=True,exist_ok=True)
    sources=[ROOT/'upstream/dm/host/dmhost',*(ROOT/'sim/calibration').glob('*.py'),
             *(ROOT/'tests').glob('*a6*.py'),*(ROOT/'arena/lib').glob('*.py')]
    sources.extend(p for stage in ('Yunohana','District00','Yagara') for p in
                   (ROOT/f'work/arena/maps/{stage}').iterdir() if p.name in ('human.npz','sight.npz','navigation.json'))
    binding=dict(plan=plan,expected_game_build_id='28c4287aee36f7499da60f3e68b54c70',
                 build_id_status='Expected from accepted 11.3.0 A6; audit future native session logs before fitting.',
                 source_sha256={str(p.relative_to(ROOT)):sha256(p) for p in sources})
    manifest=out/'manifest.json';encoded=json.dumps(binding,indent=2)+'\n'
    if manifest.exists() and manifest.read_text()!=encoded:raise ValueError('calibration binding changed; choose a new output directory')
    manifest.write_text(encoded)
    selected=[c for c in plan['cases'] if only is None or c['id'] in only]
    if only and set(only)!={c['id'] for c in selected}:raise ValueError('unknown case IDs')
    statuses=[]
    for case in selected:
        file=out/case['id']/'status.json'
        if file.exists() and json.loads(file.read_text())['status']=='collected':
            statuses.append(json.loads(file.read_text()));continue
        if active_native():raise RuntimeError('native window acquired by another session; no processes signaled')
        attempt=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        directory=file.parent/attempt;lab=None
        status=dict(id=case['id'],status='failed',attempt=attempt,native_mechanism_accepted=False)
        try:
            lab=make_lab(case,directory,timeout);lab.start();collect(lab,case)
            lab.result['passed']=True
            status.update(status='collected',surface_confirmation=lab.result['surface_confirmation'],
                          note='Collected, not fitted/accepted; unknown surfaces and geometry require annotation.')
        except Exception as error:
            status.update(error=repr(error),traceback=traceback.format_exc())
            if lab:lab.result['errors'].append(repr(error))
        finally:
            if lab:
                lab.close()
                if lab.result['errors']:
                    status.update(status='failed',errors=lab.result['errors'])
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text(json.dumps(status,indent=2)+'\n');statuses.append(status)
            (out/'summary.json').write_text(json.dumps(dict(collection_only=True,cases=statuses,
                complete=len(statuses)==len(selected),native_mechanism_accepted=False),indent=2)+'\n')
            print(json.dumps(status),flush=True)
    return 0 if all(s['status']=='collected' for s in statuses) else 1
