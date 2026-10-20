#!/usr/bin/env python3
"""At least 3 fresh seeded trials per route; predeclared empirical-noise gate.

For each role, compare the route means against max(within-menu range,
within-native range). Report every within/cross pair as well. This is an
empirical acceptance rule, not a confidence interval or determinism proof.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import itertools
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.runner import write_json_atomic
from probe_a7_trial import sha


def distribution(rows):
    if len(rows)<3 or any(len(r)!=2 or any(not math.isfinite(v) for v in r) for r in rows):raise ValueError('at least three finite score pairs per route')
    pairs=[dict(indices=[i,j],difference_pp=[abs(a-b) for a,b in zip(rows[i],rows[j])]) for i,j in itertools.combinations(range(len(rows)),2)]
    return dict(scores=rows,mean=[statistics.mean(c) for c in zip(*rows)],
        range_pp=[max(c)-min(c) for c in zip(*rows)],pairwise=pairs)


def compare(menu,native):
    groups=[distribution(rows) for rows in (menu,native)]
    upper=[max(a,b) for a,b in zip(*(g['range_pp'] for g in groups))]
    delta=[abs(a-b) for a,b in zip(*(g['mean'] for g in groups))]
    cross=[dict(menu=i,native=j,difference_pp=[abs(a-b) for a,b in zip(m,n)]) for i,m in enumerate(menu) for j,n in enumerate(native)]
    return dict(passed=all(d<=b+1e-6 for d,b in zip(delta,upper)),
        criterion='per-role absolute difference of route means <= max of the two within-route ranges; no confidence/determinism claim',
        within=dict(menu=groups[0],native=groups[1]),noise_upper_pp=upper,mean_difference_pp=delta,cross_pairs=cross,
        maximum_cross_difference_pp=[max(r['difference_pp'][n] for r in cross) for n in (0,1)])


def spawn_identity(infos):
    """Freeze actual starting state, not just requested seat/team parameters."""
    result={}
    for agent in ('player_0','player_1'):
        row=infos[agent]
        if not row.get('position_valid') or not row.get('heading_valid'):
            raise ValueError('missing initial position/heading '+agent)
        result[agent]=dict(position=[round(v,3) for v in row['position']],
            heading=round(row['heading'],3),self_slot=row.get('self_slot'))
    return result


def analyze(out):
    plan=json.loads((out/'plan.json').read_text());trials=[];errors=[];reference=None;identity=None;spawn=None
    neutral=dict(sticks=[0.,0.,0.,0.],gyro=[0.,0.,0.],buttons=[0]*6)
    default={f'player_{n}':neutral for n in (0,1)}
    for job in plan['jobs']:
        path=out/job['name']/'result.json';r=json.loads(path.read_text());m=r.get('match',{})
        if not r.get('passed') or not m.get('native_winners') or m.get('void') or m.get('errors'):errors.append('incomplete/invalid trial '+job['name'])
        ident={k:r.get(k) for k in ('host_sha256','runtime_sha256','source_hashes','policy_step_frames','stage','seed_words')}
        if identity is None:identity=ident
        elif identity!=ident:errors.append('runtime/parameter mismatch '+job['name'])
        inputs=[json.loads(line)['actions'] for line in (out/job['name']/'match/inputs-per-present.jsonl').read_text().splitlines()]
        if reference is None:reference=inputs
        bad=next((i for i in range(max(len(inputs),len(reference))) if (inputs[i] if i<len(inputs) else default)!=(reference[i] if i<len(reference) else default)),None)
        if len(inputs)<10920 or bad is not None:errors.append('executed input mismatch '+job['name']+' frame='+str(bad))
        first=json.loads((out/job['name']/'match/native-barriers.jsonl').read_text().splitlines()[0])
        actual_spawn=spawn_identity(first['infos'])
        if spawn is None:spawn=actual_spawn
        elif spawn!=actual_spawn:errors.append('actual spawn/heading mismatch '+job['name'])
        logs=[]
        for n in (0,1):
            player=Path(m['session'])/f'player-{n}';options=json.loads((player/'input.json').read_text())
            if options.get('DM_SCENE_SEEDS')!='1,2,3,4' or options.get('DM_RL_CLOCK_MODE')!='fixed60' or options.get('DM_RL_WAIT_INGAME')!='1' or options.get('DM_TEST_SPECIAL'):errors.append('native input settings mismatch '+job['name'])
            lines=[line for line in (player/'host.log').read_text(errors='replace').splitlines() if 'A7_SEEDS origin=consumed ' in line and 'requested_match=1' in line]
            if not lines:errors.append('seed consumption missing '+job['name']+'/'+str(n))
            logs.append(lines)
        trials.append(dict(name=job['name'],route=job['route'],result=str(path),sha256=sha(path),actual_spawn=actual_spawn,scores=m.get('score_by_role'),outcome=m.get('outcome'),frames=m.get('frames'),input_rows=len(inputs),first_input_difference=bad,seed_consumption=logs,phase_wall_seconds=r.get('phase_wall_seconds'),controlled_fps=r.get('controlled_fps')))
    metrics=compare(*[[t['scores'] for t in trials if t['route']==route] for route in ('menu','native')])
    result=dict(schema='arena.a7.repeatability.v1',**metrics,errors=errors,trials=trials,runtime_identity=identity,
        input_comparison='All executed actions equal over their union after neutral padding of post-Winners tails; settlement labels are not input. Every trial executed the full 10920-frame non-neutral frozen plan.',
        plan_sha256=sha(out/'plan.json'),full_a7_passed=False)
    result['passed']=metrics['passed'] and not errors
    result['outcomes']={route:{win:sum(t['outcome']==win for t in trials if t['route']==route) for win in ('a','b','draw')} for route in ('menu','native')}
    write_json_atomic(out/'result.json',result);return result


def main(args):
    out=args.out.resolve()
    if args.analyze_only:return analyze(out)
    if not out.is_relative_to(ROOT/'work'):raise ValueError('raw evidence must stay under work/')
    out.mkdir(parents=True,exist_ok=False);slots=out/'loader-slots';slots.mkdir()
    for n in (0,1):(slots/f'slot-{n}').touch()
    jobs=[dict(name=f'{route}-{n}',route=route) for n in range(args.repeats) for route in ('menu','native')]
    plan=dict(schema='arena.a7.repeatability-plan.v1',jobs=jobs,parallel=args.parallel,
        criterion='per-role absolute difference of route means <= max(menu range, native range)',
        exploratory_cross_pairs='All nine or more cross-pairs are reported without selecting favorable pairs.',
        seed_words=[1,2,3,4],stage=2,host=str(args.host.resolve()),patched=str(args.patched.resolve()),policies=str(args.policies.resolve()),entry_sha256=sha(__file__),trial_entry_sha256=sha(ROOT/'tests/probe_a7_trial.py'))
    write_json_atomic(out/'plan.json',plan)
    def run(job):
        command=[sys.executable,str(ROOT/'tests/probe_a7_trial.py'),'--host',plan['host'],'--patched',plan['patched'],'--policies',plan['policies'],'--route',job['route'],'--out',str(out/job['name']),'--shared-load-slots',str(slots)]
        with (out/(job['name']+'.log')).open('w') as log:code=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
        print(job['name'],'exit',code,flush=True);return code
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:codes=list(pool.map(run,jobs))
    if any(codes):raise RuntimeError('trial failed; preserve logs and inspect before any rerun')
    return analyze(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--host',type=Path);p.add_argument('--patched',type=Path);p.add_argument('--policies',type=Path)
    p.add_argument('--repeats',type=int,choices=(3,4,5),default=3);p.add_argument('--parallel',type=int,choices=(1,2,3),default=3)
    p.add_argument('--analyze-only',action='store_true')
    args=p.parse_args();r=main(args);print(json.dumps(r,indent=2));raise SystemExit(0 if r['passed'] else 1)
