#!/usr/bin/env python3
"""UNQUALIFIED D3 native prototype; see notes/d3-blocker-20261021.md.

Defender receives filtered policy observations only. This driver has a known
90f attacker-aim failure and must not supply ranking/calibration benchmarks."""
import argparse,json,math,sys,traceback,re,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import DuelLab,owned_options,neutral,ROOT
from serve import fast_align
from validate_candidates import read_sensors
from stamper import FastTurn,fast_turn
from aim import PulseAim

def wrap(x):return math.atan2(math.sin(x),math.cos(x))
class Reactive52:
    def __init__(self,reaction=18):self.reaction=reaction;self.first=None;self.ticks=0;self.history=[]
    def act(self,obs):
        a=neutral();self.ticks+=1;e=next((e for e in obs['enemies']if e['visible']and e['position']is not None),None)
        if e and self.first is None:self.first=self.ticks
        if not e or self.first is None or self.ticks-self.first<self.reaction:
            self.history.append(dict(t=self.ticks,visible=bool(e),fired=False));return a
        own=obs['own'];p=own['position'];q=e['position'];dx,dz=q[0]-p[0],q[2]-p[2];distance=math.hypot(dx,dz);err=wrap(math.atan2(dx,dz)-own['view_yaw'])
        # Ordinary maximum stick: measured native angular acceleration applies.
        a['sticks'][2]=-math.copysign(1 if abs(err)>.13 else min(.35,abs(err)*3),err)if abs(err)>.012 else 0.
        desired=max(-.9,min(.9,math.atan2(q[1]-p[1]-.08*distance,max(distance,.05))))
        pitch=own['view_pitch']-desired;a['gyro'][0]=max(-.2,min(.2,pitch*.3))if abs(pitch)>.012 else 0.
        a['buttons'][0]=int(abs(err)<.14 and abs(pitch)<.12)
        self.history.append(dict(t=self.ticks,visible=True,target_sample=e['sample_frame'],yaw_error=err,pitch_error=pitch,fired=bool(a['buttons'][0])));return a

def main(args):
    plan=json.loads(args.selection.read_text());p=next(p for p in plan['points']if p['id']==args.point)
    lab=DuelLab('duel-'+args.point+'-'+str(args.trial),p['stage']);defender=Reactive52();duel=False;events=[];stage='startup';original_step=lab.step
    def step(actions,label,frames=6):
        nonlocal duel
        if label=='duel-R':duel=True
        if not duel:return original_step(actions,label,frames)
        out=None
        for _ in range(frames):
            typed={k:{key:list(v)for key,v in action.items()}for k,action in actions.items()};typed['player_1']=defender.act(lab.obs(1));out=original_step(typed,label,1)
        return out
    lab.step=step
    lab.result.update(calibration_eligible=False,full_d3_passed=False,d3_point=p,trial=args.trial,reaction_frames=18,native_defender_visibility='arena.policy.v1 only',duel_outcome=None)
    try:
        with owned_options(special=True,sensors=True):
            lab.start();stage='placement';lab.navigate({0:p['source'],1:p['target']},'duel-setup')
            if min(lab.info(n)['hp']for n in (0,1))<.999:raise AssertionError('full-health setup missing')
            stage='hook-aim';fast_align(lab,0,p['requested_anchor'],'duel-hook-aim')
            # Pose defender camera before the measured window; record actual
            # native body/view headings for conditional model replay.
            q=lab.info(1)['position'];heading=args.trial*math.pi/2
            fast_align(lab,1,[q[0]+math.sin(heading)*10,q[1]+1.1,q[2]+math.cos(heading)*10],'duel-defender-heading')
            a=neutral();a['buttons'][3]=1;lab.act(0,a,'duel-RS',1);lab.step(lab.actions(),'duel-startup',30)
            if min(lab.info(n)['hp']for n in (0,1))<.999:raise AssertionError('activation damaged target before measured hook')
            lab.result['duel_initial']=dict(infos=lab.env.process_infos,observers={str(n):lab.obs(n)for n in (0,1)})
            stage='flight';a=neutral();a['buttons'][2]=1;lab.act(0,a,'duel-R',1)
            log_path=Path(lab.result['session'])/'player-0/host.log';cursor=0;saw_attack=False;saw_bind=False;state=None;turner=lab.d2_turners.get(0,FastTurn());aimer=PulseAim(turner.gain or .10472,turner.sign or 1.);lab.result['attacker_aim_gain']=dict(yaw=turner.gain,sign=turner.sign,pitch_prior=.145,method='four-frame gyro pulse, four neutral feedback frames');target=list(p['target']);target[1]+=1.1
            for tick in range(120):
                actions=lab.actions()
                if saw_bind:
                    own=lab.obs(0)['own'];q=own['position'];a,_,_=aimer.act(lab.obs(0),target);actions['player_0']=a
                lab.step(actions,'duel-release',1)
                with log_path.open(errors='replace')as stream:
                    stream.seek(cursor);chunk=stream.read();cursor=stream.tell()
                for match in re.finditer(r'D2B_SNAPSHOT frame=(\d+) kind=superhook [^\n]*data=([0-9a-f]+)',chunk):
                    data=bytes.fromhex(match[2]);state=struct.unpack_from('<i',data,0x40)[0];saw_attack|=state==3;saw_bind|=state in (2,3)
                    if state in (2,3):events.append(dict(frame=int(match[1]),event='native-bind',state=state))
                if not lab.info(0)['alive']or not lab.info(1)['alive']:break
                if saw_attack and state==0:events.append(dict(frame=lab.info(0)['frame'],event='native-arrival'));break
            lab.result['hook_events']=events
            if not saw_attack and lab.info(0)['alive']and lab.info(1)['alive']:raise AssertionError('no native Attack witness within 120 frames')
            if not lab.info(0)['alive']:stage='attacker-down'
            elif lab.info(1)['alive']:
                stage='full-light';target=list(p['target']);target[1]+=1.1
                stable=0
                for _ in range(90):
                    if not lab.info(0)['alive']or not lab.info(1)['alive']:break
                    own=lab.obs(0)['own'];q=own['position'];delta=wrap(math.atan2(target[0]-q[0],target[2]-q[2])-own['view_yaw']);desired=max(-.9,min(.9,math.atan2(target[1]-q[1]-1.1,max(math.hypot(target[0]-q[0],target[2]-q[2]),.05))));pitch=own['view_pitch']-desired
                    stable=stable+1 if abs(delta)<.035 and abs(pitch)<.025 else 0
                    if stable>=6:break
                    action,_,_=aimer.act(lab.obs(0),target);lab.act(0,action,'duel-target-aim',1)
                if stable<6 and lab.info(0)['alive']and lab.info(1)['alive']:raise AssertionError('bounded own-feedback aim did not settle')
                a=neutral();a['sticks'][1]=.85;lab.act(0,a,'duel-face',6);lab.step(lab.actions(),'duel-settle',8)
                if lab.info(0)['alive']:
                    a=neutral();a['buttons'][0]=1;lab.act(0,a,'duel-charge',21);lab.step(lab.actions(),'duel-full-release',36)
                    if lab.info(0)['alive']and lab.info(1)['alive']:
                        a=neutral();a['buttons'][0]=1;lab.act(0,a,'duel-light',1);lab.step(lab.actions(),'duel-light-release',42)
            lab.result.update(passed=True,driver_completed=True,duel_outcome=dict(kill=not bool(lab.info(1)['alive']),attacker_alive=bool(lab.info(0)['alive']),target_hp=lab.info(1)['hp'],attacker_hp=lab.info(0)['hp'],final=lab.env.process_infos))
    except BaseException as e:lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc(),failure_stage=stage)
    finally:
        lab.result['reactive_history']=defender.history;lab.finish()
    if lab.result.get('session'):
        sensors=read_sensors(lab.result['session']);path=lab.out/'sensors.jsonl';path.write_text(''.join(json.dumps(x)+'\n'for x in sensors))
    print('D3_DUEL_CLOSED '+str(lab.out),flush=True);return 0 if lab.result['passed']else 1
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--selection',type=Path,default=ROOT/'work/d2c/selection.json');p.add_argument('--point',required=True);p.add_argument('--trial',type=int,default=0);raise SystemExit(main(p.parse_args()))
