"""One owned native room for A6; referee setup stays outside public skills."""
import datetime
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
import sys
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'arena/lib'),str(ROOT/'arena/lib_a6')]
from rl import NativeParallelEnv
from rl.loadout import uniform_loadout,encode_loadout
from arena.referee_api import RefereeAPI
from arena.policy import encode_policy
from atlas import MapAtlas
from skills import Skills,aim_at,neutral

MANIFEST=ROOT/'work/arena/tournament-20261019-113138-347725/runtime-sha256.json'

def t1_running():
    pid_file=ROOT/'work/codex/t1/arena.pid'
    if not pid_file.is_file():return False
    pid=int(pid_file.read_text().strip())
    return subprocess.run(['ps','-p',str(pid),'-o','pid='],capture_output=True,text=True).returncode==0

def frozen_check():
    if not MANIFEST.is_file():return dict(files=0,mismatches=[],active=False,reason='no local T1 manifest')
    frozen=json.loads(MANIFEST.read_text())
    bad=[p for p,h in frozen.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
    if str(ROOT/'upstream/dm/host/dmhost') in bad:
        raise AssertionError('default dmhost differs from protected T1 binary')
    active=t1_running()
    if bad and active:raise AssertionError('T1 frozen files changed: '+repr(bad))
    return dict(files=len(frozen),mismatches=bad,active=active)

class Lab:
    def __init__(self,name,timeout=3600,stage=1,loadouts=None):
        self.out=ROOT/'work/a6'/datetime.datetime.now().strftime(name+'-%Y%m%d-%H%M%S-%f')
        self.out.mkdir(parents=True);self.stream=(self.out/'steps.jsonl').open('w')
        self.result=dict(passed=False,full_a6_passed=False,errors=[],artifacts=str(self.out),cases=[],freeze_before=frozen_check())
        paths=[Path(__file__),Path(sys.argv[0]).resolve()]+list((ROOT/'arena/lib').glob('*.py'))+list((ROOT/'arena/lib_a6').glob('*.py'))
        self.result['code_sha256']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        for p in paths:
            (self.out/('tested-'+p.name)).write_bytes(p.read_bytes())
        self.loadouts=loadouts or [uniform_loadout() for _ in range(2)]
        self.result['loadouts']=self.loadouts
        self.env=NativeParallelEnv(players=2,stage_id=stage,weapons=[8000]*2,loadouts=self.loadouts,frame_skip=6,reward_fn=None,timeout=timeout,step_timeout=150,state_dump=True)
        self.stage=stage;self.atlas=MapAtlas.load(stage);self.count=0;self.api=None;self.origins={}
    def start(self):
        _,self.origins=self.env.reset();self.result['session']=str(self.env.session.out)
        self.result['owned_pids']=[p.pid for _,p,_ in self.env.session.hosts]
        readbacks=[]
        for n in (0,1):
            rows=re.findall(r'SPL3_GEAR piece=(\d+) id=(-?\d+) main=(\d+) subs=(-?\d+),(-?\d+),(-?\d+) count=(\d+) override=(\d+)',self.env.session.text(n))
            actual={int(row[0]):list(map(int,row[2:6])) for row in rows if row[6:]==('3','1')}
            expected=list(map(int,encode_loadout(self.loadouts[n]).split(',')))
            if actual!={p:expected[4*p:4*p+4] for p in range(3)}:raise AssertionError('A6 native loadout readback mismatch')
            readbacks.append(actual)
        self.result['loadout_readbacks']=readbacks
        self.api=RefereeAPI(self.out.name,self.origins,dict.fromkeys(self.env.possible_agents,8000),dict(zip(self.env.possible_agents,(0,1))),ROOT/f"work/arena/maps/{self.atlas.data['name']}/sight.npz",stage_id=self.stage)
        self.api.update(self.origins)
        for _ in range(30):self.step(self.actions(),'warmup',15)
        self.save();return self
    def actions(self):return {p:neutral() for p in self.env.possible_agents}
    def info(self,n):return self.env.process_infos[f'player_{n}']
    def obs(self,n):
        result=json.loads(encode_policy(self.api.policy_observation(f'player_{n}')))
        # Own charge is human-visible. This lab-only extension never exposes
        # enemy HP or raw metadata and does not modify the frozen policy wire.
        i=self.info(n);result['own']['special']=i.get('special') if i.get('special_valid') else None
        return result
    def step(self,a,label,frames=6):
        typed={p:{k:np.asarray(v,dtype=np.int8 if k=='buttons' else np.float32) for k,v in action.items()} for p,action in a.items()}
        self.env.frame_skip=frames;_,_,_,truncated,infos=self.env.step(typed)
        if any(truncated.values()):raise TimeoutError('A6 session deadline')
        for p,i in infos.items():
            if i['phase']!=1 or i.get('time_valid') and i['remaining_time']<=0:
                raise RuntimeError('A6 normal match duration exhausted')
            elapsed=i['frame']-self.origins[p]['frame']
            if i['guest_time_ns']-self.origins[p]['guest_time_ns']!=elapsed*1000000000//60:raise AssertionError('fixed60 drift')
        self.api.update(infos);self.count+=1
        self.stream.write(json.dumps(dict(step=self.count,label=label,frames=frames,actions=a,infos=infos))+'\n');self.stream.flush()
        return infos
    def act(self,n,action,label,frames=1):
        a=self.actions();a[f'player_{n}']=action;return self.step(a,label,frames)
    def capture(self,label):
        for p,o in self.env.observations.items():Image.fromarray(o['pixels']).save(self.out/f'{label}-{p}.png')
    def save(self):
        self.result['steps']=self.count
        (self.out/'result.json').write_text(json.dumps(self.result,indent=2)+'\n')
    def add(self,case):
        self.result['cases'].append(case);self.save()
        print(json.dumps({k:v for k,v in case.items() if k not in ('before','after','history','roll_run_up')}),flush=True)
    def align(self,n,target,label='align',precise=False):
        def evaluate():
            obs=self.obs(n);result=aim_at(obs,target)
            if precise and result.status!='unavailable':
                own=obs['own'];p=own['position'];dx,dz=target[0]-p[0],target[2]-p[2]
                error=math.atan2(math.sin(math.atan2(dx,dz)-own['view_yaw']),math.cos(math.atan2(dx,dz)-own['view_yaw']))
                desired=max(-.9,min(.9,math.atan2(target[1]-p[1]-1.1,max(math.hypot(dx,dz),.05))))
                pitch=own['view_pitch']-desired
                if abs(error)>.015:result.action['sticks'][2]=-math.copysign(.35,error)
                if abs(pitch)>.015:result.action['gyro'][0]=max(-.12,min(.12,pitch*.16))
                result.done=abs(error)<=.015 and abs(pitch)<=.015
            return result
        for _ in range(160):
            r=evaluate()
            if r.done:
                self.step(self.actions(),label+'-settle',8)
                if evaluate().done:return
            else:
                own=self.obs(n)['own'];p=own['position'];yaw=math.atan2(target[0]-p[0],target[2]-p[2])
                error=abs(math.atan2(math.sin(yaw-own['view_yaw']),math.cos(yaw-own['view_yaw'])))
                self.act(n,r.action,label,3 if error>.12 or abs(r.action['gyro'][0])>.02 else 1)
                self.step(self.actions(),label+'-sample',5)
        raise AssertionError('A6 setup aim failed')
    def look(self,n,pitch):
        o=self.obs(n)['own'];p=o['position'];yaw=o['view_yaw'];d=2.
        self.align(n,(p[0]+math.sin(yaw)*d,p[1]+1.1+math.tan(pitch)*d,p[2]+math.cos(yaw)*d),'look')
    def paint_floor(self,n):
        self.look(n,-.65)
        for _ in range(4):
            a=neutral();a['buttons'][0]=1;self.act(n,a,'floor-press',1);self.step(self.actions(),'floor-release',29)
    def refill(self,n,frames=150,surface=True):
        a=neutral();a['buttons'][1]=1;self.act(n,a,'refill',frames)
        if surface:self.step(self.actions(),'surface',12)
    def navigate(self,goals,label='navigate'):
        controls={n:Skills(self.atlas) for n in goals}
        respawning={}
        for _ in range(600):
            a=self.actions();done=True
            for n,target in goals.items():
                info=self.info(n)
                if info.get('alive_valid') and not info.get('alive'):
                    respawning[n]=None
                    # The native respawn launcher waits for ZR. Navigation's
                    # dead-state neutrality alone cannot launch a dummy target.
                    # Pulse only our own setup-controlled player, never a
                    # tournament peer or a policy-controlled evaluation window.
                    done=False
                    if info.get('position_valid') and info['position'][1]>20:
                        a[f'player_{n}']['buttons'][0]=int(self.count%2==0)
                    continue
                if n in respawning:
                    # Alive switches on as the launch begins, before landing.
                    # Match initial warmup's neutral landing allowance before
                    # asking the ground graph to anchor this actor.
                    if respawning[n] is None:respawning[n]=info['frame']
                    if info['frame']-respawning[n]<180:
                        done=False
                        continue
                    del respawning[n]
                    controls[n]=Skills(self.atlas)
                r=controls[n].move_to(self.obs(n),target)
                if r.status=='blocked':raise AssertionError(f'{label} blocked: {self.info(n)["position"]}')
                if not r.done:done=False;a[f'player_{n}']=r.action
            if done:self.step(self.actions(),label+'-settle',30);return
            self.step(a,label,6)
        raise AssertionError(label+' budget exhausted')
    def restore(self,n,goal,radius=.12):
        for _ in range(140):
            own=self.obs(n)['own'];p=own['position'];d=math.dist(p,goal)
            if d<radius:return
            dx,dz=goal[0]-p[0],goal[2]-p[2];yaw=own['view_yaw']
            x=-dx*math.cos(yaw)+dz*math.sin(yaw);y=dx*math.sin(yaw)+dz*math.cos(yaw);norm=max(.001,math.hypot(x,y))
            a=neutral();a['sticks'][:2]=[.85*x/norm,.85*y/norm]
            self.act(n,a,'restore',3 if d>.3 else 1);self.step(self.actions(),'restore-sample',8)
        raise AssertionError('A6 pose restore exhausted')
    def execute(self,n,plan,label,other=None):
        history=[]
        for _ in range(400):
            result=plan.tick(self.obs(n))
            if result.done:
                if result.status!='complete':raise AssertionError(label+': '+result.status)
                return history
            a=self.actions();a[f'player_{n}']=result.action
            if other is not None:a[f'player_{1-n}']=other(self.obs(1-n))
            infos=self.step(a,label+'-'+result.phase,result.frames)
            history.append(dict(phase=result.phase,frames=result.frames,infos=infos))
        raise AssertionError(label+' macro budget')
    def close(self):
        try:self.env.close()
        except BaseException as e:self.result['errors'].append('cleanup: '+repr(e))
        self.stream.close();self.result['freeze_after']=frozen_check();self.save()
