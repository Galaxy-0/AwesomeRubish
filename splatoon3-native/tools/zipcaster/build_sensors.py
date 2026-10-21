#!/usr/bin/env python3
"""Build isolated D2B read-only diagnostic host/modules; never edit upstream."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2];HOST=ROOT/'upstream/dm/host'
sys.path.insert(0,str(ROOT))
from tools.build_a7_host import build_inputs


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(args):
    out=args.out.resolve();parent=args.parent.resolve();original_modules=args.modules.resolve()
    if ROOT/'work' not in out.parents or out.exists():raise ValueError('fresh output directory under work required')
    record=json.loads(parent.with_suffix('.build.json').read_text())
    assert record['test_only'] and record['test_feature']=='special_meter'
    assert sha(parent)==record['output_sha256']
    for name,digest in record['source_sha256'].items():assert sha(ROOT/name)==digest,name
    protected={p:sha(p)for p in [HOST/'dmhost',ROOT/'work/a8/dmhost-arena-v15',parent]}
    module_before={p:sha(p)for p in original_modules.iterdir()if p.is_file()}
    out.mkdir(parents=True)
    # Expand only this derivative's observation dispatch table. Existing IDs and
    # register-preserving gate ABI remain identical; normal host is unchanged.
    dispatch=out/'hle.c';dispatch.write_text((HOST/'hle.c').read_text().replace('#include "dm.h"','#include "dm.h"\n#define OBS_MAX 48',1))
    observer_source=Path(__file__).with_name('sensor.h');observer=out/'sensor.h';shutil.copyfile(observer_source,observer)
    shutil.copyfile(__file__,out/'tested-build_sensors.py');rl=out/'hle_rl.c'
    text=(HOST/'hle_rl.c').read_text()
    text=text.replace('static void own_player(const uint64_t *r) {',f'#include "{observer}"\nstatic void own_player(const uint64_t *r) {{',1)
    text=text.replace('    if(first)LOG("RL_SELF_SLOT', '    d2b_damage((uintptr_t)r[0],slot);\n    if(first)LOG("RL_SELF_SLOT',1)
    text=text.replace('    gate_obs_set(OBS_SPL3_OWN_PLAYER,own_player);', '    d2b_init();\n    gate_obs_set(OBS_SPL3_OWN_PLAYER,own_player);',1)
    rl.write_text(text)
    command=list(record['command']);host=out/'dmhost-sensors';command[command.index('-o')+1]=str(host)
    for old,new in [('hle.c',dispatch),('hle_rl.c',rl)]:
        assert old in command,old;command[command.index(old)]=str(new)
    command.insert(1,'-I'+str(HOST))
    inputs=set(build_inputs(command))|{HOST/'hle.c',HOST/'hle_rl.c',observer,Path(__file__).resolve()}
    frozen={str(p.relative_to(ROOT)):sha(p)for p in sorted(inputs)}
    with (out/'build.log').open('w')as log:subprocess.run(command,cwd=HOST,stdout=log,stderr=subprocess.STDOUT,check=True)
    manifest=record|dict(output=str(host.relative_to(ROOT)),output_sha256=sha(host),source_sha256=frozen,
        command=command,entry_sha256=sha(__file__),diagnostic='d2b_readonly_superhook',
        diagnostic_parent=dict(path=str(parent.relative_to(ROOT)),sha256=sha(parent)))
    host.with_suffix('.build.json').write_text(json.dumps(manifest,indent=2)+'\n')
    modules=out/'modules';shutil.copytree(args.reuse_modules.resolve()if args.reuse_modules else original_modules,modules)
    script=ROOT/'upstream/dm/tools/patch_nso.py';rewrite=out/'rewrite.py';text=script.read_text()
    needle="'28c4287aee36f7499da60f3e68b54c70': [\n    # Keep the first instruction"
    assert text.count(needle)==1
    text=text.replace(needle,"'28c4287aee36f7499da60f3e68b54c70': [\n    (0x2ae101c,46,'d10403ff','D2B SuperHook live calc entry; read-only'),\n    (0x3192a20,47,'a9bc7bfd','D2B SuperHook weapon update entry; read-only'),\n    # Keep the first instruction",1)
    # Only the optional bootlist resource path depends on script location.
    text=text.replace("os.path.dirname(os.path.abspath(__file__)), '..', 'data'",repr(str(script.parent))+", '..', 'data'")
    rewrite.write_text(text)
    env={k:v for k,v in os.environ.items()if not k.startswith('DM_')};env['DM_RULESET']='native'
    if args.reuse_modules:
        rows=[line.split('\t')for line in (modules/'main.obs.tsv').read_text().splitlines()if line and not line.startswith('#')]
        assert any(int(r[0],0)==0x2ae101c and int(r[1])==46 for r in rows)
        assert any(int(r[0],0)==0x3192a20 and int(r[1])==47 for r in rows)
        for p in modules.iterdir():
            if p.is_file():assert sha(p)==sha(args.reuse_modules/p.name),p
    else:
        with (out/'rewrite.log').open('w')as log:
            subprocess.run([sys.executable,str(rewrite),str(ROOT/'work/data/v720896/ExeFS/main'),str(modules),'main'],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    for p,h in protected.items():assert sha(p)==h,p
    for p,h in module_before.items():assert sha(p)==h,p
    (out/'provenance.json').write_text(json.dumps(dict(host=str(host),modules=str(modules),
        protected={str(p.relative_to(ROOT)):h for p,h in protected.items()},
        original_module_sha256={str(p.relative_to(ROOT)):h for p,h in module_before.items()},
        original_rewriter_sha256=sha(script),diagnostic_rewriter_sha256=sha(rewrite),observer_source_sha256=sha(observer_source),
        reused_modules=None if not args.reuse_modules else str(args.reuse_modules),
        rewritten_sha256={p.name:sha(p)for p in modules.iterdir()if p.is_file()}),indent=2)+'\n')
    print(host,modules)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--parent',type=Path,default=ROOT/'work/a8/dmhost-arena-special-v15')
    p.add_argument('--reuse-modules',type=Path,help='Reuse the already generated identical D2B46/47 module set')
    p.add_argument('--modules',type=Path,default=ROOT/'work/a7/patched-seeds-v16');main(p.parse_args())
