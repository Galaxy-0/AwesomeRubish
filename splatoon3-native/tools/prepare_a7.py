#!/usr/bin/env python3
"""Rewrite A7 scene gates in a separate module directory; keep A1-A6 intact."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=ROOT/'work/a7/patched_v720896')
    out=p.parse_args().out.resolve();original=ROOT/'work/build/patched_v720896'
    if ROOT/'work/a7' not in out.parents:p.error('output must be under work/a7/')
    if out.exists():p.error('output already exists; choose a new directory')
    source=ROOT/'work/data/v720896/ExeFS/main'
    if source.read_bytes()[0x40:0x50].hex()!='28c4287aee36f7499da60f3e68b54c70':raise ValueError('unsupported main build')
    frozen={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in original.iterdir() if path.is_file()}
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rewrite-',dir=out.parent) as temporary:
        stage=Path(temporary)
        for path in original.iterdir():
            if path.is_file():shutil.copyfile(path,stage/path.name)
        env={k:v for k,v in os.environ.items() if not k.startswith('DM_')};env['DM_RULESET']='native'
        subprocess.run([sys.executable,str(ROOT/'upstream/dm/tools/patch_nso.py'),str(source),str(stage),'main'],env=env,check=True)
        text=(stage/'main.obs.tsv').read_text()
        for address,number in ((0x3b071d0,33),(0x3d2fd80,34),(0x9546f0,35),(0x954de4,36),(0x3955ca0,37),(0x391e480,38),(0x3916f90,39),(0x38f8930,40),(0x1506cd4,41),(0x14d184c,42)):
            if not any(int(r[0],0)==address and int(r[1])==number for line in text.splitlines() if line and not line.startswith('#') for r in [line.split('\t')]):
                raise AssertionError('missing A7 gate')
        shutil.copytree(stage,out)
    if any(hashlib.sha256(path.read_bytes()).hexdigest()!=digest for path,digest in frozen.items()):
        raise AssertionError('original rewritten modules changed')
    print(out)


if __name__=='__main__':main()
