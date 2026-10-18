#!/usr/bin/env python3
"""Ensure the local rewritten main has M6's build-checked phase gates."""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
BUILD='28c4287aee36f7499da60f3e68b54c70'
EXPECTED={(0x3db55d4,21),(0x3dcc714,22),(0x3dd9374,23),(0x27fca14,24),(0x3ef6934,25),(0x3f6d6a4,26),(0x3f6df34,27),(0x2920760,28),(0x4011c64,29),(0x4011e28,30)}


def ready(directory):
    try:
        obs=(directory/'main.obs.tsv').read_text().splitlines()
        if obs[0]!='# BUILD_ID\t'+BUILD:return False
        have={(int(r[0],0),int(r[1])) for line in obs[1:] if line and not line.startswith('#') for r in [line.split('\t')]}
        gates={(int(r[3],0),int(r[2])) for line in (directory/'main.gates.tsv').read_text().splitlines()
               if line and not line.startswith('#') for r in [line.split('\t')] if r[1]=='obs'}
        if not EXPECTED<=have or not EXPECTED<=gates:return False
        # For this known build PATCH_OFF is positive: text offsets are file offsets.
        with (directory/'main.patched.bin').open('rb') as stream:
            for offset,_ in EXPECTED:
                stream.seek(offset);word=struct.unpack('<I',stream.read(4))[0]
                if word>>26!=0b000101:return False
        return True
    except (OSError,IndexError,ValueError,struct.error):return False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--patched',type=Path,default=ROOT/'work/build/patched_v720896')
    args=parser.parse_args();target=args.patched.resolve()
    if ready(target):print('M6 phase gates ready:',target);return
    source=ROOT/'work/data/v720896/ExeFS/main'
    with source.open('rb') as stream:stream.seek(0x40);build=stream.read(16).hex()
    if build!=BUILD:raise RuntimeError('M6 requires the verified 11.3.0 main')
    target.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='m6-rewrite-',dir=ROOT/'work/build') as tmp:
        stage=Path(tmp);env={k:v for k,v in os.environ.items() if not k.startswith('DM_')};env['DM_RULESET']='native'
        subprocess.run([sys.executable,str(ROOT/'upstream/dm/tools/patch_nso.py'),str(source),str(stage),'main'],env=env,check=True)
        if not ready(stage):raise RuntimeError('rewritten M6 gates did not validate')
        for path in stage.glob('main.*'):os.replace(path,target/path.name)
    print('M6 phase gates installed:',target)


if __name__=='__main__':main()
