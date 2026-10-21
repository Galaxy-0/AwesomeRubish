#!/usr/bin/env python3
"""Bounded flat .52 reactive hit control; no Zipcaster or actor writes."""
import argparse,json,sys,traceback,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import DuelLab,owned_options,neutral,ROOT,sha
from serve import fast_align
from validate import Reactive52

def main(args):
    lab=DuelLab('hint-reactive-control-'+args.name,host=ROOT/'work/d3/bullet-build-r2/dmhost-bullets',modules=ROOT/'work/a7/patched-seeds-v16');defender=Reactive52();capture=lab.out/'capture-bullets'
    lab.result.update(control_kind='flat static .52 current-visible reactive aim',calibration_eligible=False)
    try:
        with owned_options(bullets=True,capture=capture):
            lab.start();lab.navigate({0:[0,3,8],1:[-8,3,8]},'control-setup')
            q=lab.info(0)['position'];target=[q[0],q[1]+1.1-.08*8,q[2]]
            fast_align(lab,1,target,'control-preaim');a=neutral();a['sticks'][1]=.85;lab.act(1,a,'control-body-face',8);lab.step(lab.actions(),'control-stop',90)
            lab.result['initial']=lab.env.process_infos;capture.touch(exist_ok=False)
            for t in range(150):
                a=lab.actions();a['player_1']=defender.act(lab.obs(1));lab.step(a,'control-reactive',1)
                if not lab.info(0)['alive']:break
            capture.unlink();lab.result.update(passed=True,driver_completed=True,final=lab.env.process_infos)
    except BaseException as e:lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc())
    finally:lab.result['reactive_history']=defender.history;lab.finish()
    print('REACTIVE_CONTROL_CLOSED '+str(lab.out),flush=True)
    return 0 if lab.result['passed']else 1
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);raise SystemExit(main(p.parse_args()))
