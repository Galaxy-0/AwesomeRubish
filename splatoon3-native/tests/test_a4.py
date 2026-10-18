#!/usr/bin/env python3
"""A4 gate: fresh native routes/skills on three maps and A1 damage follow-up."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from test_a3a import native_run


def main(args):
    out=ROOT/'work/tests'/datetime.datetime.now().strftime('a4-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(passed=False,full_a4_passed=False,errors=[],artifacts=str(out),maps=[])
    try:
        with (out/'map-build.log').open('w') as log:
            subprocess.run([sys.executable,str(ROOT/'tools/build_arena_maps.py')],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
        subprocess.run([sys.executable,str(ROOT/'tests/test_a4_process.py')],check=True,timeout=30)
        paths=[ROOT/'upstream/dm/host/dmhost']+list((ROOT/'arena/lib').glob('*.py'))+[ROOT/'tests/probe_a4_skills.py']
        paths+=list((ROOT/'rl').glob('*.py'))+[ROOT/f'arena/{name}.py' for name in ('native_referee','policy','process','referee','referee_api','visibility','geometry')]
        frozen={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        (out/'code-sha256.json').write_text(json.dumps(frozen,indent=2)+'\n')
        for stage in (1,2,3):
            pattern=f'a4-stage{stage}-*';before=set((ROOT/'work/tests').glob(pattern))
            command=[sys.executable,str(ROOT/'tests/probe_a4_skills.py'),'--stage',str(stage),'--timeout',str(args.timeout)]
            if stage==1:command+=['--damage']
            with (out/f'stage-{stage}.log').open('w') as log:rc=native_run(command,log,args.timeout+120)
            made=set((ROOT/'work/tests').glob(pattern))-before
            if len(made)!=1:raise AssertionError('ambiguous native evidence')
            path=made.pop()/'result.json';native=json.loads(path.read_text());result['maps'].append(dict(stage=stage,evidence=str(path),completed=native['probe_completed']))
            if rc or not native.get('geometry_skills_passed') or not native['probe_completed']:raise AssertionError(f'native stage {stage} failed')
            if stage==1 and not native.get('a1_damage_passed'):raise AssertionError('A1 damage follow-up not passed')
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=sha for p,sha in frozen.items()):raise AssertionError('A4 source changed during native acceptance')
        result['a1_damage_passed']=True;result['passed']=result['full_a4_passed']=True
    except BaseException as error:result['errors'].append(repr(error))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--timeout',type=float,default=2400)
    raise SystemExit(main(p.parse_args()))
