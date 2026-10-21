#!/usr/bin/env python3
"""A paused, coordinator-only D2 measurement room driven by a recorded JSONL plan.

All game changes are ordinary controller inputs, except scoped A6 test-meter
refills. This is not a policy interface. EOF waits without advancing fixed60.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
from probe import open_lab,sha,wait_idle,neutral,NativeSession
from stamper import FastTurn
from skills import wrap
import rl.session as session_module


def fast_align(lab,player,target,label,budget=180):
    if not hasattr(lab,'d2_turners'):lab.d2_turners={}
    turner=lab.d2_turners.setdefault(player,FastTurn());stable=0
    for _ in range(budget):
        obs=lab.obs(player);own=obs['own'];p=own['position'];dx,dz=target[0]-p[0],target[2]-p[2]
        desired=max(-.9,min(.9,math.atan2(target[1]-p[1]-1.1,max(math.hypot(dx,dz),.05))))
        yaw=wrap(math.atan2(dx,dz)-own['view_yaw']);pitch=own['view_pitch']-desired
        stable=stable+1 if abs(yaw)<.035 and abs(pitch)<.025 else 0
        if stable>=6:return
        result=turner.aim(obs,target);result.action['gyro'][0]=max(-.2,min(.2,pitch*.3)) if abs(pitch)>.012 else 0.
        lab.act(player,result.action,label,1)
    raise AssertionError('bounded fast alignment did not converge')


def run(lab,command):
    kind=command['op'];label=command['label']
    if command.get('require_active') and not .001<lab.info(0)['special']<.999:raise AssertionError('required active special is absent; do not count a normal attack as special evidence')
    if kind=='navigate':lab.navigate({int(k):v for k,v in command['goals'].items()},label)
    elif kind=='align':
        target=command.get('target')
        if target is None:
            q=lab.info(command['target_player'])['position'];offset=command.get('offset',[0,.7,0]);target=[x+y for x,y in zip(q,offset)]
        if command.get('fast',False):fast_align(lab,command.get('player',0),target,label,command.get('budget',180))
        else:lab.align(command.get('player',0),target,label,precise=command.get('precise',False))
    elif kind=='step':
        remaining=command['frames'];stride=command.get('sample_every',1)
        if type(remaining)is not int or not 1<=remaining<=3600 or type(stride)is not int or not 1<=stride<=60:raise ValueError('invalid measurement frame budget')
        while remaining:
            a=lab.actions()
            for player,action in command.get('actions',{}).items():a[player].update(action)
            frames=min(stride,remaining);lab.step(a,label,frames);remaining-=frames
    elif kind=='restore':lab.restore(command.get('player',0),command['target'],command.get('radius',.12))
    elif kind=='track_step':
        player=command.get('player',0);target_player=command['target_player'];turner=getattr(lab,'d2_turners',{}).get(player)
        if turner is None:raise AssertionError('track_step requires a completed own-feedback fast alignment')
        for _ in range(command['frames']):
            obs=lab.obs(player);own=obs['own'];q=lab.info(target_player)['position'];offset=command.get('offset',[0,.7,0]);target=[x+y for x,y in zip(q,offset)]
            result=turner.aim(obs,target);p=own['position'];desired=max(-.9,min(.9,math.atan2(target[1]-p[1]-1.1,max(math.hypot(target[0]-p[0],target[2]-p[2]),.05))))
            error=own['view_pitch']-desired;result.action['gyro'][0]=max(-.2,min(.2,error*.3)) if abs(error)>.012 else 0.
            result.action['buttons']=command.get('buttons',[0]*6);lab.act(player,result.action,label,1)
    elif kind=='assert':
        for n in command.get('healthy',[]):
            info=lab.info(n)
            if not (info.get('alive_valid') and info.get('alive') and info.get('hp_valid') and info['hp']>.999):raise AssertionError('full-health precondition missing')
    elif kind=='paint_floor':lab.paint_floor(command.get('player',0))
    elif kind=='refill':lab.refill(command.get('player',0),command.get('frames',180),command.get('surface',True))
    elif kind=='finish_special':
        if lab.info(0)['special']>=.999 or not lab.info(0).get('alive'):lab.step(lab.actions(),label+'-already-ended',120)
        else:wait_idle(lab,label)
    elif kind=='capture':lab.capture(label)
    elif kind=='status':pass
    else:raise ValueError('unknown D2 operation: '+kind)
    result=dict(command=command,infos=lab.env.process_infos,observers={f'player_{n}':lab.obs(n)['own'] for n in (0,1)})
    lab.add(dict(kind=label,command=command,after=lab.env.process_infos))
    return result


def main(args):
    args.suite=args.name;lab=open_lab(args);lab.result.update(test_special_mode=args.meter,measurement_watchdogs=dict(generic_wall_idle_disabled=True,active_present_stall_seconds=120));original=NativeSession.host_options;cursor=0;done=False
    lab.result.update(driver_sha256=sha(__file__),helper_sha256=sha(Path(__file__).with_name('probe.py')),full_d2_passed=False)
    (lab.out/'tested-serve.py').write_bytes(Path(__file__).read_bytes())
    args.commands.parent.mkdir(parents=True,exist_ok=True);args.commands.touch(exist_ok=False)
    results=args.commands.with_suffix('.results.jsonl')
    original_environment=session_module.host_environment
    def environment(*a,**kw):
        result=original_environment(*a,**kw)
        # Presence enables crash.c's generic watchdog: zero/empty means a 15s fallback.
        # Omit both variables; keep hle_rl.c's active-present watchdog unchanged.
        result.pop('DM_WATCH',None);result.pop('DM_WATCH_STALL',None);return result
    def options(self,player):return original(self,player)|dict(DM_RL_STALL_SECONDS='120')|({'DM_TEST_SPECIAL':args.meter} if player==0 else {})
    try:
        with patch.object(NativeSession,'host_options',options),patch.object(session_module,'host_environment',environment):
            lab.start();print('D2_READY '+str(lab.out),flush=True)
            with args.commands.open() as source,results.open('w') as output:
                while not done:
                    pos=source.tell();line=source.readline()
                    if not line or not line.endswith('\n'):
                        source.seek(pos);time.sleep(.1);continue
                    command=json.loads(line);cursor+=1
                    if command['op']=='close':done=True;break
                    before=lab.env.process_infos
                    try:
                        record=run(lab,command);record.update(sequence=cursor,completed=True,before=before)
                    except AssertionError as error:
                        # A bounded fixture placement failure is evidence, not permission
                        # to rewrite game state. Remain paused for a different input plan.
                        record=dict(sequence=cursor,command=command,completed=False,error=repr(error),before=before,infos=lab.env.process_infos)
                        lab.add(dict(kind=command['label'],status='fixture_failed',error=repr(error)))
                    output.write(json.dumps(record)+'\n');output.flush()
                    print('D2_COMMAND '+json.dumps(dict(sequence=cursor,label=command['label'],completed=record['completed'])),flush=True)
            lab.result.update(passed=True,probe_completed=True,driver_completed=True)
    except BaseException as error:
        lab.result['errors'].append(repr(error));lab.result['traceback']=traceback.format_exc()
    finally:lab.close()
    lab.result['commands']=str(args.commands);lab.result['commands_sha256']=sha(args.commands)
    lab.result['raw_sha256']={str(lab.out/'steps.jsonl'):sha(lab.out/'steps.jsonl')}
    for n in (0,1):
        p=Path(lab.result.get('session',''))/f'player-{n}/host.log'
        if p.is_file():lab.result['raw_sha256'][str(p)]=sha(p)
    lab.result['passed']=bool(lab.result['passed'] and not lab.result['errors']);lab.save();print('D2_CLOSED '+str(lab.out),flush=True);return 0 if lab.result['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--name',required=True);p.add_argument('--commands',type=Path,required=True)
    p.add_argument('--stage',type=int,choices=(1,2,3),default=1)
    p.add_argument('--host',type=Path,default=ROOT/'work/a8/dmhost-arena-special-v15')
    p.add_argument('--patched',type=Path,default=ROOT/'work/a7/patched-seeds-v16');p.add_argument('--timeout',type=float,default=7200);p.add_argument('--meter',choices=('full','infinite'),default='infinite')
    raise SystemExit(main(p.parse_args()))
