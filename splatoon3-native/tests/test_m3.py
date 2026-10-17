#!/usr/bin/env python3
"""M3: two real dmhosts create, scan and join through the local virtual medium."""
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
import tempfile
import time

from test_m1 import ROOT, FAILURE, FRAME
from test_m2 import SAVE_SHA256


def main(args):
    out=ROOT/'work/tests'/datetime.datetime.now().strftime('m3-%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True)
    print(f'M3 artifacts: {out}',flush=True)
    result=dict(milestone='M3',passed=False,errors=[],hosts=[])
    processes=[];streams=[];air=None
    seed=ROOT/'work/save_ref/save.dat'
    original=ROOT.parent/'splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat'
    def spawn(player,path):
        d=out/f'player-{player}';d.mkdir();(d/'save').mkdir();(d/'temp').mkdir()
        shutil.copyfile(seed,d/'save/save.dat')
        fifo=d/'pad.fifo';os.mkfifo(fifo)
        env={k:v for k,v in os.environ.items() if not k.startswith('DM_')}
        extra=args.a_route if player==0 else args.b_route
        route=(ROOT/'tools/routes/m2-local-lobby.keys').read_text().strip()+',f2700:A'+extra
        env.update(DM_ROOT=str(ROOT/'work'),DM_ROMFS=str(ROOT/'work/data/v720896/RomFS'),
                   DM_SAVE=str(d/'save'),DM_TEMP=str(d/'temp'),DM_MSL_DIR=str(ROOT/'work/build/cache/metal_shader_cache'),
                   DM_FONT_DIR=str(ROOT/'work/build/font'),DM_PLAYER=str(player),DM_FULL_UNLOCK='1',DM_LDN_AIR=str(path),
                   DM_HID_FIFO=str(fifo),DM_KEYS=route,DM_WATCH_STALL='20',DM_WATCH_SAMPLE=str(d/'stall.txt'),
                   DM_NVN_SHOT=','.join(str(i) for i in range(2400,18001,600))+':'+str(d/'frame_%d.png'))
        (d/'input.json').write_text(json.dumps({k:v for k,v in env.items() if k.startswith('DM_')},indent=2)+'\n')
        log=(d/'host.log').open('wb');streams.append(log)
        p=subprocess.Popen([str(ROOT/'upstream/dm/host/dmhost'),str(ROOT/'work/build/patched_v720896')],
                           env=env,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
        processes.append((p,d))
    try:
        for p in (seed,original):
            if hashlib.sha256(p.read_bytes()).hexdigest()!=SAVE_SHA256:raise ValueError(f'reference hash mismatch: {p}')
        with tempfile.TemporaryDirectory(prefix='s3-m3-') as tmp:
            path=Path(tmp)/'air.sock'
            stream=(out/'air.log').open('wb');streams.append(stream)
            air=subprocess.Popen([sys.executable,str(ROOT/'tools/ldn/air.py'),'--socket',str(path)],stdout=stream,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+5
            while not path.exists():
                if air.poll() is not None or time.monotonic()>deadline:raise RuntimeError('air failed to start')
                time.sleep(.02)
            spawn(0,path)
            started=time.monotonic();joined_at=None;held_session=None;last_print=0
            while time.monotonic()-started<args.timeout:
                airtext=(out/'air.log').read_text(errors='replace')
                if air.poll() is not None:raise RuntimeError('medium exited early')
                for p,d in processes:
                    text=(d/'host.log').read_text(errors='replace')
                    if p.poll() is not None or FAILURE.search(text):raise RuntimeError(f'{d.name}: runtime failure or early exit {p.poll()}')
                # B starts only after the real game created a room, never a fake beacon.
                if 'create player=0 ' in airtext and len(processes)==1:spawn(1,path)
                joins=list(re.finditer(r'join player=1 host=0 session=(\w+) nodes=2',airtext))
                joined=joins[-1] if joins else None
                if joined:
                    a=(out/'player-0/host.log').read_text(errors='replace')
                    b=(out/'player-1/host.log').read_text(errors='replace')
                    states=[re.findall(r'LDN state=(\d+) node=(-?\d+) nodes=(\d+) session=(\w+)',text) for text in (a,b)]
                    both=bool(states[0] and states[1] and states[0][-1][:3]==('3','0','2') and states[1][-1][:3]==('5','1','2')
                              and states[0][-1][3]==states[1][-1][3]==joined.group(1)[:8])
                    session=joined.group(1)
                    discovery=bool(re.search(rf'create player=0 session={session} ',airtext)
                                   and re.search(rf'scan player=1 count=\d+ session={session} ',airtext))
                    data=all(re.search(rf'recv player={i} frames=[1-9]\d* session={session}',airtext) for i in (0,1)) and discovery
                    if held_session!=session:joined_at=None;held_session=session
                    if both and data:
                        if joined_at is None:joined_at=time.monotonic()
                    else:joined_at=None
                    if both and data and joined_at is not None and time.monotonic()-joined_at>=args.hold_seconds:
                        result.update(session=joined.group(1),both_hosts_observed_membership=True,datagrams_forwarded=True,
                                      stable_seconds=time.monotonic()-joined_at,
                                      received_frames_lower_bound={str(i):max(map(int,re.findall(rf'recv player={i} frames=(\d+) session={session}',airtext)),default=0) for i in (0,1)})
                        break
                if time.monotonic()-last_print>10:
                    frames={d.name:max(map(int,FRAME.findall((d/'host.log').read_text(errors='replace'))),default=0) for p,d in processes}
                    print(f'M3 {time.monotonic()-started:.0f}s frames={frames} joined={bool(joined)}',flush=True);last_print=time.monotonic()
                time.sleep(.5)
            else:raise TimeoutError('two real games did not reach stable same-room membership and datagram delivery before deadline')
    except (OSError,ValueError,RuntimeError,TimeoutError,subprocess.SubprocessError) as e:
        result['errors'].append(str(e))
    finally:
        for p,d in processes:
            if p.poll() is None:p.terminate()
            try:p.wait(8)
            except subprocess.TimeoutExpired:p.kill();p.wait();result['errors'].append(f'{d.name}: forced kill')
            text=(d/'host.log').read_text(errors='replace')
            if p.returncode or FAILURE.search(text) or '优雅退出完成' not in text:result['errors'].append(f'{d.name}: unclean exit {p.returncode}')
            result['hosts'].append(dict(player=d.name,returncode=p.returncode,last_frame=max(map(int,FRAME.findall(text)),default=0)))
        if air and air.poll() is None:air.terminate();air.wait(5)
        for stream in streams:stream.close()
        for p in (seed,original):
            try:
                if hashlib.sha256(p.read_bytes()).hexdigest()!=SAVE_SHA256:result['errors'].append(f'reference changed: {p}')
            except OSError as e:result['errors'].append(str(e))
        result['passed']=not result['errors'] and result.get('both_hosts_observed_membership',False) and result.get('datagrams_forwarded',False)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2),flush=True)
    return not result['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout',type=float,default=360)
    parser.add_argument('--hold-seconds',type=float,default=10)
    parser.add_argument('--a-route',default=',f3300:Y,f3900:A')
    parser.add_argument('--b-route',default=',f3900:A,f4500:A')
    args=parser.parse_args()
    if not 1<=args.timeout<=1800 or not 1<=args.hold_seconds<=120:parser.error('invalid timeout/hold range')
    raise SystemExit(main(args))
