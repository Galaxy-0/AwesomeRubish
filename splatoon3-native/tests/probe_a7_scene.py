#!/usr/bin/env python3
"""One owned A7 boot-scene experiment, with no menu input or OCR."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from PIL import Image,ImageStat

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.private_battle import host_environment
from tools.m5_resources import Monitor
from rl.session import FAILURE,SAVE_HASH


def main(args):
    out=ROOT/'work/a7'/datetime.datetime.now().strftime('scene-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    for part in ('save','temp'):(out/part).mkdir()
    seed=ROOT/'work/save_ref/save.dat'
    if hashlib.sha256(seed.read_bytes()).hexdigest()!=SAVE_HASH:raise AssertionError('reference save changed')
    shutil.copyfile(seed,out/'save/save.dat')
    env=host_environment(ROOT,out,out,0,1,None,[8000])
    env.update(DM_KEYS='',DM_SCENE_BOOT=args.scene,DM_WATCH_STALL='120',
               DM_PROBE='main:3cf5004,main:3cf53d0',
               DM_NVN_SHMAP=str(ROOT/'upstream/dm/games/0100C2500FC20000/shader_map.tsv'),
               DM_NVN_SHOT=f'600,1200,1800,2400,3000:{out}/frame-%d.png')
    for key in ('DM_HID_FIFO','DM_LOAD_SLOTS'):env.pop(key,None)
    (out/'input.json').write_text(json.dumps({k:v for k,v in env.items() if k.startswith('DM_')},indent=2)+'\n')
    report=dict(schema='arena.a7.scene-prototype.v1',passed=False,full_a7_passed=False,
                errors=[],artifacts=str(out),scene=args.scene,menu_inputs=[],ocr_used=False,
                host=str(args.host),patched=str(args.patched),
                host_sha256=hashlib.sha256(args.host.read_bytes()).hexdigest(),
                default_host_sha256=hashlib.sha256((ROOT/'upstream/dm/host/dmhost').read_bytes()).hexdigest())
    monitor=Monitor(out);started=time.time();process=None
    def save():
        report['elapsed_wall_seconds']=time.time()-started
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out,flush=True);save()
    with (out/'host.log').open('wb') as log:
        try:
            process=subprocess.Popen([str(args.host),str(args.patched)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            report['owned_pid']=process.pid;save();last_print=0
            while time.time()-started<args.timeout:
                text=(out/'host.log').read_text(errors='replace')
                if process.poll() is not None or FAILURE.search(text):raise RuntimeError('native exit/failure; retained host.log')
                report['native_scene_events']=[line for line in text.splitlines() if 'A7_SCENE ' in line]
                frames=re.findall(r'RESOURCE_FRAME frame=(\d+)',text);report['last_frame']=int(frames[-1]) if frames else 0
                monitor.sample([(0,process,out)]);save()
                if time.time()-last_print>30:
                    print(dict(elapsed=round(time.time()-started),frame=report['last_frame'],events=report['native_scene_events'][-2:]),flush=True);last_print=time.time()
                # This only bounds the survey. A redirect is not native entry proof.
                if report['last_frame']>=3000:break
                time.sleep(2)
        except BaseException as error:report['errors'].append(repr(error))
        finally:
            if process is not None:
                if process.poll() is None:process.terminate()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait();report['errors'].append('forced kill of own host')
                report['returncode']=process.returncode
                if process.returncode:report['errors'].append('unclean native exit')
    text=(out/'host.log').read_text(errors='replace')
    report['native_scene_events']=[line for line in text.splitlines() if 'A7_SCENE ' in line]
    report['images']=[]
    for path in sorted(out.glob('frame-*.png')):
        im=Image.open(path).convert('RGB');report['images'].append(dict(path=str(path),size=list(im.size),variance=ImageStat.Stat(im).var))
    report['redirect_observed']=any('boot_redirect ' in line for line in report['native_scene_events'])
    report['native_destination_observed']=any(' request=' in line and 'destination='+args.scene+' ' in line for line in report['native_scene_events'])
    report['request_transport_passed']=report['redirect_observed'] and report['native_destination_observed']
    report['training_enter_hits']=len(re.findall(r'PROBE main\+0x3cf5004 ',text))
    report['training_calc_hits']=len(re.findall(r'PROBE main\+0x3cf53d0 ',text))
    report['training_entry_observed']=report['training_enter_hits']>0 and report['training_calc_hits']>1
    report['passed']=not report['errors'] and report['request_transport_passed'] and report['training_entry_observed'] and len(report['images'])>=2
    report['proof_scope']='single-process ShootingRange entry/update and images only; no private match or continuous match acceptance'
    report['resources']=monitor.summary()
    if hashlib.sha256(seed.read_bytes()).hexdigest()!=SAVE_HASH:raise AssertionError('reference save changed')
    if hashlib.sha256((ROOT/'upstream/dm/host/dmhost').read_bytes()).hexdigest()!=report['default_host_sha256']:raise AssertionError('default host changed')
    save();print(json.dumps(report,indent=2),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scene',choices=('ShootingRange','LobbyLocal','trace'),default='ShootingRange')
    p.add_argument('--host',type=Path,default=ROOT/'work/a7/dmhost-scene')
    p.add_argument('--patched',type=Path,default=ROOT/'work/a7/patched_v720896')
    p.add_argument('--timeout',type=float,default=240)
    raise SystemExit(main(p.parse_args()))
