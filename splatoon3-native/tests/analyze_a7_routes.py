#!/usr/bin/env python3
"""Audit frozen-input menu/native runs, retaining failed comparisons.

Cross-run Turf scores allow one native formatter quantum (0.1 percentage
point). Winner, source/runtime identity, fixed60 and recorded input must agree.
This does not change A5's per-game referee or its peer-score treatment.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.scoring import compare_scores


def verdict(menu,native,inputs_equal,identities_equal,tolerance=.1):
    if not 0<=tolerance<=.1:raise ValueError('score tolerance must be within one 0.1 pp formatter quantum')
    scores=[m.get('score_by_role') or [] for m in (menu,native)]
    valid_scores=all(len(s)==2 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in s) for s in scores)
    difference=[abs(a-b) for a,b in zip(*scores)] if valid_scores else []
    checks=dict(completed=all(m.get('passed') and m.get('native_winners') and not m.get('void') and not m.get('errors') for m in (menu,native)),
        same_winner=menu.get('outcome') in ('a','b','draw') and menu.get('outcome')==native.get('outcome'),
        score_within_one_quantum=len(difference)==2 and max(difference)<=tolerance+1e-6,
        same_inputs=inputs_equal,same_runtime_and_parameters=identities_equal)
    return dict(passed=all(checks.values()),checks=checks,score_difference_pp=difference,
                score_tolerance_pp=tolerance,score_tolerance_basis='one native PaintPercent/10 display quantum')


def analyze(menu_path,native_path,tolerance=.1):
    paths=[Path(menu_path).resolve(),Path(native_path).resolve()]
    reports=[json.loads(path.read_text()) for path in paths];matches=[r.get('match',{}) for r in reports]
    evidence=[]
    def read(path):
        data=path.read_bytes();evidence.append(dict(path=str(path),sha256=hashlib.sha256(data).hexdigest()));return data
    for path in paths:read(path)
    inputs=[read(path.parent/'match/inputs-per-present.jsonl').splitlines() for path in paths]
    input_equal=len(inputs[0])==len(inputs[1]) and all(json.loads(a)==json.loads(b) for a,b in zip(*inputs))
    first_difference=next((n for n,(a,b) in enumerate(zip(*inputs)) if json.loads(a)!=json.loads(b)),None)
    identities=(reports[0].get('host_sha256')==reports[1].get('host_sha256') and
                reports[0].get('source_hashes')==reports[1].get('source_hashes') and
                reports[0].get('stage')==reports[1].get('stage') and
                reports[0].get('policy_step_frames')==reports[1].get('policy_step_frames') and
                matches[0].get('role_to_policy')==matches[1].get('role_to_policy'))
    actual=[]
    for report,match in zip(reports,matches):
        valid=bool(match.get('passed'))
        if valid:
            rebuilt=compare_scores(*match['score_peers_native_order'],match['role_to_policy'])
            valid=all(match.get(k)==v for k,v in rebuilt.items())
        session=Path(match['session']);settings=[]
        for n in (0,1):
            options=json.loads(read(session/f'player-{n}/input.json'))
            valid=valid and options.get('DM_RL_CLOCK_MODE')=='fixed60' and options.get('DM_RL_WAIT_INGAME')=='1' and not options.get('DM_TEST_SPECIAL')
            settings.append({k:options.get(k) for k in ('DM_WEAPON','DM_GEAR','DM_PLAYER','DM_SCENE_SEEDS')})
        actual.append(settings);identities=identities and valid
    identities=identities and actual[0]==actual[1]
    result=verdict(*matches,input_equal,identities,tolerance)
    return dict(schema='arena.a7.frozen-input-comparison.v1',full_a7_passed=False,
        **result,evidence=evidence,menu=str(paths[0]),native=str(paths[1]),
        identity_scope='Recorded host SHA, policy sources/step, map, role mapping, fixed60, early InGame barrier, equipment, seed parameters. Rewritten-module identity is archived separately; old baseline reports do not embed module hashes.',
        input_present_counts=[len(x) for x in inputs],first_input_difference=first_difference,
        scores=[m.get('score_by_role') for m in matches],outcomes=[m.get('outcome') for m in matches])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--menu',type=Path,required=True)
    p.add_argument('--native',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--score-tolerance-pp',type=float,default=.1)
    args=p.parse_args();result=analyze(args.menu,args.native,args.score_tolerance_pp)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
