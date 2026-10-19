#!/usr/bin/env python3
"""Build the opt-in special-meter test host without rebuilding default dmhost."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT=Path(__file__).resolve().parents[1]
HOST=ROOT/'upstream/dm/host'
DEFAULT=HOST/'dmhost'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'work/a6/dmhost-test-special')
    args=parser.parse_args();out=args.out.resolve()
    if out==DEFAULT.resolve() or out.exists() and out.samefile(DEFAULT) or ROOT/'work' not in out.parents:
        parser.error('test host output must be under ignored work/ and cannot be default dmhost')
    if out.exists():
        commands=subprocess.run(['ps','-axo','command='],capture_output=True,text=True,check=True).stdout.splitlines()
        if any(line==str(out) or line.startswith(str(out)+' ') for line in commands):
            parser.error('refusing to replace a running test host')
    before=sha(DEFAULT);out.parent.mkdir(parents=True,exist_ok=True)
    # Dry-run ONLY: never execute the default host target or preceding recipes.
    dry=subprocess.run(['make','-n','GAME=0100C2500FC20000','dmhost'],cwd=HOST,capture_output=True,text=True,check=True).stdout
    lines=[line for line in dry.splitlines() if line.startswith('clang ') and ' -o dmhost ' in line]
    if len(lines)!=1:raise RuntimeError('expected exactly one explicit clang host recipe')
    command=shlex.split(lines[0]);command[command.index('-o')+1]=str(out)
    command.insert(1,'-DSPL3_A6_TEST_SPECIAL=1')
    log=out.with_suffix('.build.log')
    try:
        with log.open('w') as stream:
            subprocess.run(command,cwd=HOST,stdout=stream,stderr=subprocess.STDOUT,check=True)
    finally:
        if sha(DEFAULT)!=before:raise AssertionError('default dmhost changed')
    record=dict(schema='arena.a6.test-host-build.v1',test_only=True,
        output=str(out.relative_to(ROOT)),output_sha256=sha(out),default_sha256=before,
        default_unchanged=True,command=command,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in
            (HOST/'hle_rl.c',HOST/'dm_spl3_test_special.h')})
    path=out.with_suffix('.build.json');path.write_text(json.dumps(record,indent=2)+'\n')
    print(path)


if __name__=='__main__':main()
