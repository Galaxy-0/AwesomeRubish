#!/usr/bin/env python3
"""A4 gate: ten preset routes/map, >=90%, fresh three-map skills and recovery."""
import argparse
import ast
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from test_a3a import native_run


def accepted_damage():
    # Explicitly carry the already accepted partial proof, with unchanged
    # native host/time transport and unchanged aiming/painting implementations.
    proof=ROOT/'work/tests/a4-stage1-20261018-231611-601829/result.json'
    native=json.loads(proof.read_text())
    if not native['a1_damage_passed'] or not native['probe_completed'] or native['errors']:raise AssertionError('accepted A1 damage proof unavailable')
    frozen=json.loads((ROOT/'work/a4/acceptance-runtime-2.json').read_text())
    for path,sha in frozen.items():
        p=Path(path)
        if p==ROOT/'upstream/dm/host/dmhost' or p.parent==ROOT/'rl':
            if hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise AssertionError('native time/transport changed since damage proof')
    baseline=subprocess.check_output(['git','show','7e2ecd7dc86c7c0142ceb75fc83bbad88b19d064:splatoon3-native/arena/lib/skills.py'],cwd=ROOT,text=True)
    def functions(text):
        tree=ast.parse(text);tree.body=[n for n in tree.body if not (isinstance(n,ast.ClassDef) and n.name=='Skills')]
        return ast.dump(tree,include_attributes=False)
    if functions(baseline)!=functions((ROOT/'arena/lib/skills.py').read_text()):raise AssertionError('aim/ink functions changed since damage proof')
    return dict(reused_accepted_partial=True,commit='7e2ecd7dc86c7c0142ceb75fc83bbad88b19d064',path=str(proof),sha256=hashlib.sha256(proof.read_bytes()).hexdigest(),damage=native['damage'])


def main(args):
    out=ROOT/'work/tests'/datetime.datetime.now().strftime('a4-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(passed=False,full_a4_passed=False,errors=[],artifacts=str(out),maps=[])
    try:
        result['a1_damage']=accepted_damage()
        with (out/'map-build.log').open('w') as log:
            subprocess.run([sys.executable,str(ROOT/'tools/build_arena_maps.py'),'--stage',*[str(s) for s in args.stages]],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1200)
        subprocess.run([sys.executable,str(ROOT/'tests/test_a4_process.py')],check=True,timeout=30)
        from probe_a4_routes import preset_goals,MapAtlas
        for stage in args.stages:
            atlas=MapAtlas.load(stage);goals=preset_goals(stage,atlas)
            for start in [s['ground'] for s in atlas.spawns.values()]+list(goals.values()):
                for goal in goals.values():atlas.route(start,goal)
        (out/'preflight.json').write_text(json.dumps(dict(passed=True,goals={s:preset_goals(s,MapAtlas.load(s)) for s in args.stages}),indent=2)+'\n')
        paths=[ROOT/'upstream/dm/host/dmhost',ROOT/'tests/probe_a4_routes.py',ROOT/'tools/build_arena_maps.py']+list((ROOT/'arena/lib').glob('*.py'))
        paths+=list((ROOT/'rl').glob('*.py'))+[ROOT/f'arena/{name}.py' for name in ('native_referee','policy','process','referee','referee_api','visibility','geometry')]
        paths += [ROOT/f'work/arena/maps/{name}/navigation.json' for name in ('Yunohana','District00','Yagara')]
        frozen={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};(out/'code-sha256.json').write_text(json.dumps(frozen,indent=2)+'\n')
        for stage in args.stages:
            pattern=f'a4-routes-stage{stage}-*';before=set((ROOT/'work/tests').glob(pattern))
            command=[sys.executable,str(ROOT/'tests/probe_a4_routes.py'),'--stage',str(stage),'--timeout',str(args.timeout)]
            with (out/f'stage-{stage}.log').open('w') as log:rc=native_run(command,log,3*args.timeout+120)
            made=set((ROOT/'work/tests').glob(pattern))-before
            if len(made)!=1:raise AssertionError('ambiguous native evidence')
            path=made.pop()/'result.json';native=json.loads(path.read_text())
            result['maps'].append(dict(stage=stage,evidence=str(path),completed=native['probe_completed'],route_count=native.get('route_count'),route_rate=native.get('route_rate'),skills_passed=native.get('skills_passed'),passed=native['passed']))
            if rc or not native['passed']:result['errors'].append(f'native stage {stage} failed: {native["errors"]}')
            # Route misses are retained and the other maps still run. A native
            # runtime/setup failure stops immediately rather than retrying it.
            if native['errors']:break
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=sha for p,sha in frozen.items()):raise AssertionError('A4 source/maps changed during acceptance')
        result['phase_passed']=not result['errors'] and len(result['maps'])==len(args.stages)
        result['passed']=result['full_a4_passed']=result['phase_passed'] and set(args.stages)=={1,2,3} and len(args.stages)==3
    except BaseException as error:result['errors'].append(repr(error))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result.get('phase_passed',False) else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--timeout',type=float,default=3000)
    p.add_argument('--stages',type=int,choices=(1,2,3),nargs='+',default=[2,1,3]);raise SystemExit(main(p.parse_args()))
