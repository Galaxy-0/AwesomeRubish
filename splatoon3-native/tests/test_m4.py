#!/usr/bin/env python3
"""M4: real private settings and a complete local 1v1, using controller input only."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from byml import read as read_byml
from test_m1 import ROOT, FAILURE, FRAME
from test_m2 import SAVE_SHA256

# These addresses are read-only diagnostics for the build guarded by DM_FULL_UNLOCK.
# Native stage insertion / completed list; native UniqueSequence vtable +0x118
# (enter) for InGame, ResultJudge and ResultWinners. Never alter match state.
PROBES = ('main:3904a18@x0+10,main:3904b28@x19+8,'
          'main:4367644@x25+0,main:4367810@x19+318,'
          'main:38fa2cc@x20+cf0,'
          'main:3db55d0,main:3dcc710,main:3dd9370')
A_ROUTE = (',f3300:Y,f3900:A,f4500:Right*5/300,f6300:Down,f6600:A,'
           'f7200:R,f7800:R,f8400:L,f8700:L,f9000:Right,f9300:A,'
           'f9600:Down,f9900:A,f10500:Right,f10800:Down,f11100:Right,'
           'f11400:Right,f11700:Down,f12000:A,f12900:A')
B_ROUTE = ',f3900:A,f4500:A,f9000:A'
MODES = ('Turf War', 'Splat Zones', 'Tower Control', 'Rainmaker', 'Clam Blitz')


def stage_evidence(text):
    rows = re.findall(r'PROBE main\+0x3904a18 .*?\[x0\+0x10\]=([0-9a-f]{32})', text)
    ids = sorted({int.from_bytes(bytes.fromhex(row)[4:8], 'little') for row in rows})
    counts = [int.from_bytes(bytes.fromhex(row)[:4], 'little') for row in re.findall(
        r'PROBE main\+0x3904b28 .*?\[x19\+0x8\]=([0-9a-f]{32})', text)]
    picker_ids = sorted({int.from_bytes(bytes.fromhex(row)[:4], 'little') for row in re.findall(
        r'PROBE main\+0x4367644 .*?\[x25\+0\]=([0-9a-f]{32})', text)})
    picker_counts = [int.from_bytes(bytes.fromhex(row)[:4], 'little') for row in re.findall(
        r'PROBE main\+0x4367810 .*?\[x19\+0x318\]=([0-9a-f]{32})', text)]
    return dict(ids=ids, completed_counts=counts, picker_ids=picker_ids, picker_counts=picker_counts)


def enters(text, address):
    return [float(x) for x in re.findall(rf'PROBE main\+0x{address} .*?\[([\d.]+)s\]', text)]


def recognize(executable, paths, output):
    if not paths:
        return []
    run = subprocess.run([str(executable), *map(str, paths)], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, timeout=180, check=True)
    output.write_text(run.stdout)
    return [json.loads(line) for line in run.stdout.splitlines()]


def main(args):
    out = ROOT/'work/tests'/datetime.datetime.now().strftime('m4-%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True)
    print(f'M4 artifacts: {out}', flush=True)
    result = dict(milestone='M4', passed=False, errors=[], hosts=[])
    processes = []; streams = []; air = None
    seed = ROOT/'work/save_ref/save.dat'
    original = ROOT.parent/'splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat'
    ocr = out/'vision-ocr'

    def spawn(player, path):
        d = out/f'player-{player}'; d.mkdir()
        for name in ('save', 'temp'): (d/name).mkdir()
        shutil.copyfile(seed, d/'save/save.dat')
        env = {k: v for k, v in os.environ.items() if not k.startswith('DM_')}
        route = (ROOT/'tools/routes/m2-local-lobby.keys').read_text().strip()+',f2700:A'
        route += args.a_route if player == 0 else args.b_route
        env.update(DM_ROOT=str(ROOT/'work'), DM_ROMFS=str(ROOT/'work/data/v720896/RomFS'),
                   DM_SAVE=str(d/'save'), DM_TEMP=str(d/'temp'),
                   DM_MSL_DIR=str(ROOT/'work/build/cache/metal_shader_cache'),
                   DM_FONT_DIR=str(ROOT/'work/build/font'), DM_PLAYER=str(player),
                   DM_FULL_UNLOCK='1', DM_LDN_AIR=str(path), DM_PROBE=PROBES,
                   DM_KEYS=route, DM_WATCH_STALL='30', DM_WATCH_SAMPLE=str(d/'stall.txt'),
                   DM_NVN_SHOT=','.join(map(str, range(2400, 60001, 300)))+':'+str(d/'frame_%d.png'))
        (d/'input.json').write_text(json.dumps({k:v for k,v in env.items() if k.startswith('DM_')}, indent=2)+'\n')
        log = (d/'host.log').open('wb'); streams.append(log)
        p = subprocess.Popen([str(ROOT/'upstream/dm/host/dmhost'), str(ROOT/'work/build/patched_v720896')],
                             env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
        processes.append((p,d))

    try:
        for path in (seed, original):
            if hashlib.sha256(path.read_bytes()).hexdigest() != SAVE_SHA256:
                raise ValueError(f'reference hash mismatch: {path}')
        table = ROOT/'work/data/v720896/RomFS/RSDB/VersusSceneInfo.Product.b30.rstbl.byml.zs'
        rows = read_byml(subprocess.check_output(['zstd', '-dc', str(table)]))
        expected = sorted(r['Id'] for r in rows if r['IsDisplayInStageList'])
        if len(set(expected)) != len(expected): raise ValueError('duplicate stage IDs')
        result.update(catalog_rows=len(rows), expected_stage_ids=expected,
                      catalog_sha256=hashlib.sha256(table.read_bytes()).hexdigest())
        subprocess.run(['swiftc', str(ROOT/'tools/vision-ocr.swift'), '-o', str(ocr)], check=True, timeout=90)
        with tempfile.TemporaryDirectory(prefix='s3-m4-') as tmp:
            path = Path(tmp)/'air.sock'
            log = (out/'air.log').open('wb'); streams.append(log)
            air = subprocess.Popen([os.sys.executable, str(ROOT/'tools/ldn/air.py'), '--socket', str(path)],
                                   stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic()+5
            while not path.exists():
                if air.poll() is not None or time.monotonic() > deadline: raise RuntimeError('air startup failed')
                time.sleep(.02)
            spawn(0, path)
            started = last_print = time.monotonic(); finished_at = None
            while time.monotonic()-started < args.timeout:
                airtext = (out/'air.log').read_text(errors='replace')
                if air.poll() is not None: raise RuntimeError('air exited early')
                texts = []
                for p,d in processes:
                    text = (d/'host.log').read_text(errors='replace'); texts.append(text)
                    if p.poll() is not None or FAILURE.search(text):
                        raise RuntimeError(f'{d.name}: runtime failure or early exit {p.poll()}')
                if 'create player=0 ' in airtext and len(processes) == 1: spawn(1,path)
                joins = re.findall(r'join player=1 host=0 session=(\w+) nodes=2',airtext)
                if joins: result['session'] = joins[-1]
                # A real result sequence must be entered on both sides. Wait for
                # visible result screenshots as well; stage constructors don't pass.
                if len(texts) == 2 and all(enters(t,'3dd9370') for t in texts):
                    if finished_at is None: finished_at = time.monotonic()
                    if time.monotonic()-finished_at > 25: break
                if time.monotonic()-last_print > 15:
                    frames = {d.name:max(map(int,FRAME.findall((d/'host.log').read_text(errors='replace'))),default=0) for p,d in processes}
                    print(f'M4 {time.monotonic()-started:.0f}s frames={frames} joined={bool(joins)}',flush=True)
                    last_print=time.monotonic()
                time.sleep(.5)
            else: raise TimeoutError('both games did not reach native result sequences before deadline')
    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
        result['errors'].append(str(error))
    finally:
        for p,d in processes:
            if p.poll() is None: p.terminate()
            try: p.wait(8)
            except subprocess.TimeoutExpired:
                p.kill();p.wait();result['errors'].append(f'{d.name}: forced kill')
            text=(d/'host.log').read_text(errors='replace')
            if p.returncode or FAILURE.search(text) or '优雅退出完成' not in text:
                result['errors'].append(f'{d.name}: unclean exit {p.returncode}')
            evidence=stage_evidence(text)
            game=enters(text,'3db55d0');judge=enters(text,'3dcc710');winners=enters(text,'3dd9370')
            evidence.update(player=d.name, returncode=p.returncode,
                            last_frame=max(map(int,FRAME.findall(text)),default=0),
                            in_game=game,result_judge=judge,result_winners=winners)
            if d.name == 'player-0':
                for ids, counts in [('ids','completed_counts'), ('picker_ids','picker_counts')]:
                    if evidence[ids] != result.get('expected_stage_ids') or not evidence[counts] or any(
                            n != len(result.get('expected_stage_ids',[])) for n in evidence[counts]):
                        result['errors'].append(f'{d.name}: {ids} differs from catalog')
            if not game or not judge or not winners or not (game[0]+178 <= judge[-1] <= winners[-1]):
                result['errors'].append(f'{d.name}: no full three-minute game/result sequence')
            result['hosts'].append(evidence)
        if air and air.poll() is None: air.terminate();air.wait(5)
        for stream in streams: stream.close()
        for path in (seed,original):
            try:
                if hashlib.sha256(path.read_bytes()).hexdigest()!=SAVE_SHA256:
                    result['errors'].append(f'reference changed: {path}')
            except OSError as error: result['errors'].append(str(error))
        try:
            # Snapshot intervals bracket each mode change. Recognition is local
            # macOS Vision, no image upload or external service.
            a=out/'player-0'
            settings=sorted((p for p in a.glob('frame_*.png') if 4200<=int(p.stem.split('_')[1])<=6300))
            recognized=recognize(ocr,settings,out/'settings-ocr.jsonl')
            visible='\n'.join(line for row in recognized for line in row['lines'])
            result['modes']={mode:mode.lower() in visible.lower() for mode in MODES}
            if not all(result['modes'].values()): result['errors'].append('five modes not all observed in native settings')
            for host in result['hosts']:
                d=out/host['player']
                paths=sorted(d.glob('frame_*.png'),key=lambda p:int(p.stem.split('_')[1]))[-8:]
                rows=recognize(ocr,paths,d/'result-ocr.jsonl')
                host['visible_result']=[row['path'] for row in rows if any(
                    re.search(r'victory|defeat',line,re.I) for line in row['lines'])]
                if not host['visible_result']: result['errors'].append(f'{d.name}: no visible victory/defeat result')
        except (OSError,ValueError,subprocess.SubprocessError) as error:
            result['errors'].append(f'screenshot recognition: {error}')
        result['passed'] = not result['errors'] and len(result['hosts'])==2 and bool(result.get('session'))
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2),flush=True)
    return not result['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout',type=float,default=1200)
    parser.add_argument('--a-route',default=A_ROUTE)
    parser.add_argument('--b-route',default=B_ROUTE)
    args=parser.parse_args()
    if not 300<=args.timeout<=2400: parser.error('timeout must be 300..2400 seconds')
    raise SystemExit(main(args))
