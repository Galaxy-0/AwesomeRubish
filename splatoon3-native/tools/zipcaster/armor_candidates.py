#!/usr/bin/env python3
"""Three D2C close-lane incoming-hit controls; sensor readback, no HP writes."""
import argparse
import json
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
from probe import open_lab,NativeSession,sha
from serve import run
from validate_candidates import read_sensors,HOST,MODULES
import rl.session as session_module


def main(args):
    args.suite=f'c-armor-{args.delay}'+('-fixed'if args.future_aim else'');args.stage=1;args.host=HOST;args.patched=MODULES
    lab=open_lab(args);original=NativeSession.host_options;original_env=session_module.host_environment
    (lab.out/'tested-validate_candidates.py').write_bytes(Path(__file__).with_name('validate_candidates.py').read_bytes())
    def options(self,player):return original(self,player)|dict(DM_D2B_SENSOR='1',DM_RL_STALL_SECONDS='120')|({'DM_TEST_SPECIAL':'infinite'}if player==0 else{})
    def environment(*a,**kw):
        value=original_env(*a,**kw);value.pop('DM_WATCH',None);value.pop('DM_WATCH_STALL',None);return value
    def command(op,label,**kw):
        value=run(lab,dict(op=op,label=label,**kw))
        with (lab.out/'commands.jsonl').open('a')as f:f.write(json.dumps(value)+'\n')
        return value
    try:
        with patch.object(NativeSession,'host_options',options),patch.object(session_module,'host_environment',environment):
            lab.start()
            command('navigate','armor-setup',goals={'0':[0,3,8],'1':[-4,3,5.5]})
            command('align','armor-hook-aim',target=[0,6,4],fast=True)
            if args.future_aim:
                command('align','armor-enemy-aim',player=1,target=[.15,6.35,4.98],fast=True)
            else:command('align','armor-enemy-aim',player=1,target_player=0,offset=[0,1.1,0],fast=True)
            command('assert','armor-health',healthy=[0,1])
            command('status','armor-before')
            command('step','armor-RS',frames=1,actions={'player_0':{'buttons':[0,0,0,1,0,0]}})
            command('step','armor-startup',frames=30)
            if args.future_aim:command('step','armor-precharge',frames=21,actions={'player_1':{'buttons':[1,0,0,0,0,0]}})
            else:command('track_step','armor-precharge',frames=21,player=1,target_player=0,offset=[0,1.1,0],buttons=[1,0,0,0,0,0])
            command('step','armor-R',frames=1,actions={'player_0':{'buttons':[0,0,1,0,0,0]},'player_1':{'buttons':[1,0,0,0,0,0]}})
            if args.future_aim:command('step','armor-track-flight',frames=args.delay,actions={'player_1':{'buttons':[1,0,0,0,0,0]}})
            else:command('track_step','armor-track-flight',frames=args.delay,player=1,target_player=0,offset=[0,1.1,0],buttons=[1,0,0,0,0,0])
            command('status','armor-release-before')
            if args.future_aim:command('step','armor-enemy-release',frames=50)
            else:command('track_step','armor-enemy-release',frames=50,player=1,target_player=0,offset=[0,1.1,0],buttons=[0]*6)
            command('status','armor-after')
            lab.result.update(passed=True,driver_completed=True,release_delay=args.delay,aim_mode='fixed-future'if args.future_aim else'track-current',full_d2_passed=False)
    except BaseException as error:
        lab.result['errors'].append(repr(error));lab.result['traceback']=traceback.format_exc()
    finally:lab.close()
    rows=read_sensors(lab.result['session'])if lab.result.get('session')else[]
    path=lab.out/'sensors.jsonl';path.write_text(''.join(json.dumps(r,separators=(',',':'))+'\n'for r in rows))
    lab.result['post_sensor_sha256']=sha(path);lab.save()
    print('D2C_ARMOR '+str(lab.out),flush=True)
    return 0 if lab.result['passed']else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--delay',type=int,choices=[32,36,70],required=True)
    p.add_argument('--future-aim',action='store_true');p.add_argument('--timeout',type=float,default=1800);raise SystemExit(main(p.parse_args()))
