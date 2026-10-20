#!/usr/bin/env python3
"""Build A7's experimental host to work/, preserving the default executable."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT=Path(__file__).resolve().parents[1]
HOST=ROOT/'upstream/dm/host'
DEFAULT=HOST/'dmhost'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def build_inputs(command):
    paths={HOST/'Makefile',ROOT/'upstream/dm/tools/patch_nso.py'}
    for value in command:
        path=Path(value)
        if not path.is_absolute():path=HOST/path
        if path.is_file() and path.suffix in ('.c','.m','.S','.a'):paths.add(path.resolve())
    for base in (HOST,ROOT/'upstream/dm/gfx',ROOT/'upstream/dm/ios/Sources'):
        paths.update(p.resolve() for p in base.rglob('*') if p.is_file() and p.suffix in ('.h','.inc') and 'tests' not in p.parts)
    paths.update((ROOT/'upstream/dm/games/0100C2500FC20000'/name) for name in ('game.tsv','dmsh_chain.h'))
    return sorted(paths)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=ROOT/'work/a7/dmhost-scene')
    p.add_argument('--a8-render',choices=('none','camera'),default='none',help='Experimental A8 renderer build, default unchanged')
    p.add_argument('--a8-hdr',action='store_true',help='UNSUPPORTED diagnostic candidate: guarded HDR bloom elision; native smoke aborts')
    p.add_argument('--a8-copy',choices=('none','coalesce','scatter'),default='none',help='Experimental uniform updates: adjacent copies or byte-masked batched compute')
    p.add_argument('--test-special-of',type=Path,help='Build an explicit test-only derivative of this production A7 host')
    args=p.parse_args();out=args.out.resolve();parent=None
    if args.a8_hdr and (args.a8_render!='camera' or args.test_special_of):p.error('--a8-hdr requires --a8-render camera and no production parent')
    if args.test_special_of and args.a8_copy!='none':p.error('test derivative inherits copy mode from its parent')
    if args.test_special_of:
        source=args.test_special_of.resolve();parent=json.loads(source.with_suffix('.build.json').read_text())
        if source==out or parent.get('test_only') or sha(source)!=parent['output_sha256']:p.error('invalid production parent')
        if args.a8_render!='none':p.error('test derivative inherits rendering from its production parent')
        if not parent.get('complete_build_inputs'):p.error('legacy parent lacks complete renderer inputs; build a fresh production parent first')
        for name,digest in parent['source_sha256'].items():
            if sha(ROOT/name)!=digest:p.error('production parent source changed: '+name)
    if ROOT/'work' not in out.parents or out==DEFAULT.resolve() or out.exists() and out.samefile(DEFAULT):
        p.error('output must be under work/ and cannot alias default dmhost')
    rows=subprocess.check_output(['ps','-axo','command='],text=True).splitlines()
    if any(line==str(out) or line.startswith(str(out)+' ') for line in rows):p.error('output is running')
    before=sha(DEFAULT);out.parent.mkdir(parents=True,exist_ok=True)
    if parent:command=list(parent['command'])
    else:
        dry=subprocess.check_output(['make','-n','GAME=0100C2500FC20000','dmhost'],cwd=HOST,text=True)
        lines=[line for line in dry.splitlines() if line.startswith('clang ') and ' -o dmhost ' in line]
        if len(lines)!=1:raise RuntimeError('expected one explicit host clang recipe')
        command=shlex.split(lines[0])
    command[command.index('-o')+1]=str(out)
    if parent:command.insert(1,'-DSPL3_A6_TEST_SPECIAL=1')
    elif args.a8_render=='camera':command.insert(1,'-DSPL3_A8_CAMERA=1')
    if args.a8_hdr:command.insert(1,'-DSPL3_A8_HDR=1')
    if args.a8_copy=='coalesce':command.insert(1,'-DSPL3_A8_COPY=1')
    if args.a8_copy=='scatter':command.insert(1,'-DSPL3_A8_COPY=2')
    sources=build_inputs(command)
    frozen={str(path.relative_to(ROOT)):sha(path) for path in sources}
    if parent and any(frozen.get(name)!=digest for name,digest in parent['source_sha256'].items()):p.error('production compile inputs changed')
    try:
        with out.with_suffix('.build.log').open('w') as log:
            subprocess.run(command,cwd=HOST,stdout=log,stderr=subprocess.STDOUT,check=True)
    finally:
        if sha(DEFAULT)!=before:raise AssertionError('default dmhost changed')
    if any(sha(ROOT/name)!=digest for name,digest in frozen.items()):raise AssertionError('build input changed during compilation')
    record=dict(schema='arena.a7.host-build.v1',output=str(out.relative_to(ROOT)),output_sha256=sha(out),
                default_sha256=before,default_unchanged=True,command=command,
                source_sha256=frozen,complete_build_inputs=True,
                render_mode=parent.get('render_mode','none') if parent else args.a8_render,entry_sha256=sha(Path(__file__)))
    record['experimental_hdr']=parent.get('experimental_hdr',False) if parent else args.a8_hdr
    record['copy_mode']=parent.get('copy_mode','none') if parent else args.a8_copy
    if parent:
        if any(record['source_sha256'].get(name)!=digest for name,digest in parent['source_sha256'].items()):raise AssertionError('derivative changed production sources')
        record.update(test_only=True,test_feature='special_meter',production_parent=dict(path=str(source.relative_to(ROOT)),sha256=parent['output_sha256']))
    path=out.with_suffix('.build.json');path.write_text(json.dumps(record,indent=2)+'\n');print(path)


if __name__=='__main__':main()
