#!/usr/bin/env python3
"""D3 resumed native C: actual arrival -> B6 -> bounded aim -> 21f/70+35.

Own-feedback aim uses the known fixture target; .52 sees only arena.policy.v1.
No blind native bind/aim failure is counted as a duel kill-rate observation.
"""
import argparse,json,sys,traceback,re,struct,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import DuelLab,owned_options,neutral,ROOT,sha
from serve import fast_align,run
from validate import Reactive52
from validate_candidates import read_sensors
class DuelEnded(Exception):pass
class HookFailed(Exception):pass

def main(args):
    p=next(p for p in json.loads(args.selection.read_text())['points']if p['id']==args.point and p.get('trial',args.trial)==args.trial)
    if args.source:p['source']=args.source
    if args.target:p['target']=args.target
    p['requested_anchor'][1]+=args.anchor_dy
    lab=DuelLab(('hint-cal-'+args.cohort+'-' if args.cohort else 'hint-duel-')+args.point+'-'+str(args.trial),p['stage']);defender=Reactive52();active=False;original=lab.step;events=[];qualified=False;stage='startup'
    def step(actions,label,frames=6):
        nonlocal active
        if label=='hint-duel-R':active=True
        if not active:return original(actions,label,frames)
        out=None
        for _ in range(frames):
            if not lab.info(0)['alive']or not lab.info(1)['alive']:raise DuelEnded()
            actions={k:{key:list(v)for key,v in a.items()}for k,a in actions.items()};actions['player_1']=defender.act(lab.obs(1));out=original(actions,label,1)
        return out
    lab.step=step
    lab.result.update(point=p,trial=args.trial,cohort=args.cohort,setup_attempt=args.attempt,reaction_frames=18,calibration_eligible=False,full_d3_passed=False,controller='arrival/B6/ordinary own-feedback aim <=180f/track charge21 release36 light1 release42',known_fixture_target_for_attacker=True)
    for name in ['native.py','validate.py']:
        helper=Path(__file__).with_name(name);(lab.out/('tested-'+name)).write_bytes(helper.read_bytes())
    for name in ['serve.py']:
        helper=ROOT/'tools/zipcaster'/name;(lab.out/('tested-'+name)).write_bytes(helper.read_bytes())
    def mark(event):events.append(dict(event=event,infos=lab.env.process_infos));lab.result['events']=events;lab.save()
    try:
        with owned_options(special=True,sensors=True,meter='full'):
            lab.start();stage='setup'
            if args.attempt>1:
                hub=list(lab.atlas.points[lab.atlas.nearest(lab.atlas.region('center'))]);lab.navigate({0:hub,1:hub},'hint-duel-hub')
            lab.navigate({0:p['source'],1:p['target']},'hint-duel-place')
            if min(lab.info(n)['hp']for n in (0,1))<.999:raise AssertionError('full health setup missing')
            fast_align(lab,0,p['requested_anchor'],'hint-duel-hook-aim')
            q=lab.info(1)['position'];h=p.get('heading',args.trial*math.pi/2)
            fast_align(lab,1,[q[0]+math.sin(h)*10,q[1]+1.1,q[2]+math.cos(h)*10],'hint-duel-defender-heading')
            # GeometricVision's cone uses body heading, not camera yaw. Match
            # both using ordinary movement before the measured reaction window.
            a=neutral();a['sticks'][1]=.85;lab.act(1,a,'hint-duel-defender-face',8);lab.step(lab.actions(),'hint-duel-defender-settle',12)
            a=neutral();a['buttons'][3]=1;lab.act(0,a,'hint-duel-RS',1);lab.step(lab.actions(),'hint-duel-startup',30)
            if min(lab.info(n)['hp']for n in (0,1))<.999:raise AssertionError('contact damage before measured window')
            mark('before-R');stage='hook';qualified=True;a=neutral();a['buttons'][2]=1;lab.act(0,a,'hint-duel-R',1)
            log=Path(lab.result['session'])/'player-0/host.log';cursor=0;saw_attack=False;bound=False;state=None
            for _ in range(120):
                lab.step(lab.actions(),'hint-duel-flight',1)
                with log.open(errors='replace')as f:f.seek(cursor);chunk=f.read();cursor=f.tell()
                for m in re.finditer(r'D2B_SNAPSHOT frame=(\d+) kind=superhook [^\n]*data=([0-9a-f]+)',chunk):
                    state=struct.unpack_from('<i',bytes.fromhex(m[2]),0x40)[0];saw_attack|=state==3;bound|=state in (2,3)
                if saw_attack and state==0:break
            if not saw_attack or state!=0:raise HookFailed('no native completed first hook witness within120f')
            mark('arrival');qualified=True;stage='B';a=neutral();a['buttons'][4]=1;lab.act(0,a,'hint-duel-B',6);mark('B-end')
            stage='aim';q=list(lab.info(1)['position']);q[1]+=1.1
            fast_align(lab,0,q,'hint-duel-target-aim',budget=180);mark('aim-end')
            a=neutral();a['sticks'][1]=.85;lab.act(0,a,'hint-duel-face',6);lab.step(lab.actions(),'hint-duel-face-settle',8)
            stage='combo';mark('charge-start')
            for label,n,buttons in [('charge',21,[1,0,0,0,0,0]),('full-release',36,[0]*6),('light',1,[1,0,0,0,0,0]),('light-release',42,[0]*6)]:
                run(lab,dict(op='track_step',label='hint-duel-'+label,frames=n,player=0,target_player=1,offset=[0,1.1,0],buttons=buttons))
            mark('combo-end');lab.result.update(passed=True,driver_completed=True)
    except DuelEnded:
        # A defeat interrupts the script; do not label it as an aim exception.
        qualified=qualified or stage=='hook';lab.result.update(passed=True,driver_completed=True,ended_stage=stage);mark('duel-end')
    except HookFailed as e:
        lab.result.update(passed=True,driver_completed=True,tactic_failure=str(e));mark('hook-failed')
    except AssertionError as e:
        if qualified and stage=='aim'and str(e)=='bounded fast alignment did not converge':
            lab.result.update(passed=True,driver_completed=True,tactic_failure='C aim budget180 exhausted');mark('aim-timeout')
        else:
            qualified=False;lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc(),failure_stage=stage)
    except BaseException as e:
        qualified=False;lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc(),failure_stage=stage)
    finally:
        lab.result.update(calibration_eligible=qualified,reactive_history=defender.history,outcome=dict(kill=not bool(lab.info(1).get('alive'))if lab.env.process_infos else None,attacker_alive=bool(lab.info(0).get('alive'))if lab.env.process_infos else None));lab.finish()
    if lab.result.get('session'):
        path=lab.out/'sensors.jsonl';path.write_text(''.join(json.dumps(s)+'\n'for s in read_sensors(lab.result['session'])));lab.result['sensor_sha256']=sha(path);lab.save()
    print('HINT_DUEL_CLOSED '+str(lab.out),flush=True);return 0 if lab.result['passed']else 1
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--selection',type=Path,default=ROOT/'work/d2c/selection.json');ap.add_argument('--point',required=True);ap.add_argument('--trial',type=int,default=0);ap.add_argument('--source',nargs=3,type=float);ap.add_argument('--target',nargs=3,type=float);ap.add_argument('--cohort',default='');ap.add_argument('--attempt',type=int,choices=[1,2],default=1);ap.add_argument('--anchor-dy',type=float,default=0.);raise SystemExit(main(ap.parse_args()))
