#!/usr/bin/env python3
"""M2.5 acceptance: catalog/selector equality and real process identities.

Per GOAL.md (2026-10-18), M2.5 covers weapons and identities.
Stage/mode unlock and settings validation belong to M4.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from PIL import Image, ImageStat
from byml import read as read_byml
from test_m1 import ROOT, FRAME, FAILURE
from test_m2 import SAVE_SHA256

ROUTE = 'f300:ZL+ZR~0.2,f450:Plus,f750:A'
EQUIP = ',f1200:L,f1500:A,f1800:B,f2100:B,f2400:Plus,f2700:A'
PROBES = 'main:4402764@x8+0?x20=0,main:4401c24@x0+668?x20=0,main:3571e24@x23+194'


def dumps(text, address, field):
    return [int.from_bytes(bytes.fromhex(x)[:4], 'little') for x in re.findall(
        rf'PROBE main\+0x{address} .*?\[{re.escape(field)}\]=([0-9a-f]{{32}})', text)]


def host(out, seed, player, unlock, timeout):
    out.mkdir()
    for name in ('save', 'temp'):
        (out / name).mkdir()
    shutil.copyfile(seed, out / 'save/save.dat')
    env = {k: v for k, v in os.environ.items() if not k.startswith('DM_')}
    target = 3300 if unlock else 2400
    env.update(DM_ROOT=str(ROOT / 'work'), DM_ROMFS=str(ROOT / 'work/data/v720896/RomFS'),
               DM_SAVE=str(out / 'save'), DM_TEMP=str(out / 'temp'),
               DM_MSL_DIR=str(ROOT / 'work/build/cache/metal_shader_cache'),
               DM_FONT_DIR=str(ROOT / 'work/build/font'), DM_PLAYER=str(player),
               DM_FULL_UNLOCK=str(int(unlock)), DM_LDN_FRONTEND='1', DM_PROBE=PROBES,
               DM_KEYS=ROUTE + (EQUIP if unlock else ''), DM_WATCH_STALL='20',
               DM_WATCH_SAMPLE=str(out / 'watchdog.sample.txt'),
               DM_NVN_SHOT=f'{target}:{out}/selector.png')
    (out / 'input.json').write_text(json.dumps({k: v for k, v in env.items() if k.startswith('DM_')}, indent=2) + '\n')
    log = out / 'host.log'
    started = time.monotonic()
    errors = []
    with log.open('wb') as stream:
        proc = subprocess.Popen([str(ROOT / 'upstream/dm/host/dmhost'), str(ROOT / 'work/build/patched_v720896')],
                                cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            while True:
                text = log.read_text(errors='replace')
                if proc.poll() is not None:
                    errors.append(f'host exited early: {proc.returncode}')
                    break
                if FAILURE.search(text):
                    errors.append('runtime failure marker')
                    break
                if 'selector.png 成功' in text:
                    break
                if time.monotonic() - started > timeout:
                    errors.append('selector screenshot timeout')
                    break
                print(f'M2.5 player={player} unlock={int(unlock)} {time.monotonic()-started:.0f}s frame={max(map(int, FRAME.findall(text)), default=0)}', flush=True)
                time.sleep(5)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    errors.append('graceful shutdown timeout')
    text = log.read_text(errors='replace')
    if proc.returncode or '优雅退出完成' not in text or FAILURE.search(text):
        errors.append(f'unclean run: {proc.returncode}')
    ids = dumps(text, '4402764', 'x8+0')
    counts = dumps(text, '4401c24', 'x0+0x668')
    equipped = dumps(text, '3571e24', 'x23+0x194')
    # A reopened selector produces another complete list. Inspect every rebuild.
    lists, cursor = [], 0
    for count in counts:
        lists.append(ids[cursor:cursor + count])
        cursor += count
    if not counts or cursor != len(ids) or any(len(set(x)) != n for x, n in zip(lists, counts)):
        errors.append('selector insertion/count evidence inconsistent')
    uid = re.findall(r'SPL3_PLAYER_UID player=\d uid=(\w+:\w+)', text)
    nick = re.findall(r'SPL3_PLAYER_NICK player=\d nickname=(\S+)', text)
    if not uid or nick != [f'RL-{player}']:
        errors.append('game account read evidence missing')
    image_result = None
    if not (out / 'selector.png').is_file():
        errors.append('selector screenshot missing')
    else:
        with Image.open(out / 'selector.png') as im:
            variance = sum(ImageStat.Stat(im.convert('RGB')).var) / 3
            image_result = dict(size=list(im.size), variance=variance)
            if im.size != (1920, 1080) or variance < 25:
                errors.append('selector screenshot blank or wrong size')
    result = dict(player=player, unlock=unlock, uid=uid[-1] if uid else None,
                  nickname=nick[-1] if nick else None, counts=counts, lists=lists,
                  equipped=equipped, image=image_result, returncode=proc.returncode,
                  seconds=time.monotonic()-started, errors=errors)
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main(args):
    out = ROOT / 'work/tests' / datetime.datetime.now().strftime('m25-%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True)
    print(f'M2.5 artifacts: {out}', flush=True)
    errors = []
    result = dict(milestone='M2.5', passed=False, weapons_passed=False, errors=errors)
    seed = ROOT / 'work/save_ref/save.dat'
    original = ROOT.parent / 'splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat'
    try:
        for p in (seed, original):
            if hashlib.sha256(p.read_bytes()).hexdigest() != SAVE_SHA256:
                raise ValueError(f'reference save hash mismatch: {p}')
        table = ROOT / 'work/data/v720896/RomFS/RSDB/WeaponInfoMain.Product.b30.rstbl.byml.zs'
        data = subprocess.run(['zstd', '-d', '-c', str(table)], check=True, stdout=subprocess.PIPE).stdout
        rows = read_byml(data)
        versus = [r for r in rows if r['Type'] == 'Versus']
        expected = {r['Id'] for r in versus}
        if len(expected) != len(versus) or not all(r['SubWeapon'] and r['SpecialWeapon'] for r in versus):
            raise ValueError('catalog has duplicate IDs or incomplete kits')
        result.update(catalog_rows=len(rows), versus_kits=len(expected),
                      catalog_sha256=hashlib.sha256(table.read_bytes()).hexdigest(),
                      reference_save_sha256=SAVE_SHA256)
        baseline = host(out / 'baseline', seed, 0, False, args.timeout)
        players = [host(out / f'player-{i}', seed, i, True, args.timeout) for i in (0, 1)]
        result.update(baseline=baseline, players=players)
        for run in [baseline] + players:
            errors.extend(run['errors'])
        before = set(baseline['lists'][0]) if baseline['lists'] else set()
        if not before or not before < expected:
            errors.append('baseline must demonstrate missing Versus kits')
        for run in players:
            if not run['lists'] or any(set(x) != expected for x in run['lists']):
                errors.append(f'player {run["player"]}: actual selector IDs differ from full Versus catalog')
            selected = run['equipped'][-1] if run['equipped'] else None
            if selected not in expected - before:
                errors.append(f'player {run["player"]}: no newly unlocked kit remained equipped')
        if not players[0]['uid'] or players[0]['uid'] == players[1]['uid']:
            errors.append('real hosts did not read distinct UIDs')
        for p in (seed, original):
            if hashlib.sha256(p.read_bytes()).hexdigest() != SAVE_SHA256:
                errors.append(f'reference changed during run: {p}')
        result['weapons_passed'] = not errors
        result['identity_passed'] = not any(r['errors'] for r in players) and players[0]['uid'] != players[1]['uid']
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        errors.append(str(e))
    result['stages_modes'] = dict(passed=False, status='deferred_to_m4', reason=
        'GOAL.md moved stage/mode unlock and settings validation to M4 after LDN room creation.')
    result['passed'] = not errors and result['weapons_passed'] and result.get('identity_passed', False)
    result['scope'] = 'm25_weapons_and_identity'
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('baseline', 'players')}, indent=2), flush=True)
    return int(bool(errors))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--weapons-only', action='store_true', help='compatibility alias: weapons and identities are the full adjusted M2.5 scope')
    p.add_argument('--timeout', type=float, default=120)
    a = p.parse_args()
    if not math.isfinite(a.timeout) or a.timeout <= 0:
        p.error('--timeout must be positive')
    raise SystemExit(main(a))
