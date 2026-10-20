#!/usr/bin/env python3
"""Report measured batch throughput and unchanged memory guard outcomes."""
import argparse
import json
from pathlib import Path
import statistics
from probe_a7_trial import ROOT,sha
from arena.runner import write_json_atomic
from arena.schedule import overlap_windows


def batch(out):
    plan=json.loads((out/'plan.json').read_text());done=json.loads((out/'completed.json').read_text())
    if plan.get('pass_gpu'):raise ValueError('instrumented diagnostic batch cannot certify capacity')
    if done['plan_sha256']!=sha(out/'plan.json'):raise ValueError('capacity plan changed')
    trials=[];resources=[];matches=[]
    for n in range(plan['repeats']):
        path=out/f'trial-{n}/result.json';r=json.loads(path.read_text());match=r.get('match',{})
        if r['host_sha256']!=sha(Path(plan['host'])):raise ValueError('capacity host mismatch')
        passed=bool(r['passed'] and match.get('native_winners') and not match.get('void') and not match.get('errors'))
        if passed:matches.append(match)
        source=Path(match['session'])/'resources-summary.json' if match.get('session') else None
        if source and source.exists():resources.append(json.loads(source.read_text()))
        trials.append(dict(path=str(path),sha256=sha(path),passed=passed,errors=r['errors']+match.get('errors',[]),
            controlled_fps=r.get('controlled_fps'),wall_seconds=r.get('wall_seconds')))
    valid=sum(t['passed'] for t in trials)
    windows=overlap_windows(matches,plan['parallel'])
    stable=bool(done['passed'] and valid==plan['repeats'] and len(resources)==len(trials) and windows)
    return dict(path=str(out),plan_sha256=sha(out/'plan.json'),completed_sha256=sha(out/'completed.json'),
        host_sha256=sha(Path(plan['host'])),rooms=plan['parallel'],attempted=len(trials),valid=valid,stable=stable,
        batch_wall_seconds=done['wall_seconds'],games_per_hour=3600*valid/done['wall_seconds'],
        controlled_fps_mean=statistics.mean(t['controlled_fps'] for t in trials if t['passed']) if valid else None,
        concurrency_windows=windows,actual_overlap_seconds=sum(w['overlap_seconds'] for w in windows),
        max_new_swapout_bytes=max((r['max_new_swapout_bytes'] for r in resources),default=None),
        max_pressure=max((r['max_pressure'] for r in resources),default=None),trials=trials)


def analyze(before,after,points):
    baseline=batch(before);optimized=[batch(p) for p in [after,*points]]
    if not baseline['stable'] or baseline['rooms']!=3:raise ValueError('stable three-room baseline required')
    if optimized[0]['rooms']!=3 or not optimized[0]['stable']:raise ValueError('stable three-room optimized batch required')
    if any(p['host_sha256']!=optimized[0]['host_sha256'] for p in optimized):raise ValueError('capacity renderer changed')
    for p in [baseline,*optimized]:
        if p['stable'] and (p['max_new_swapout_bytes']>2*2**30 or p['max_pressure']>=4):raise ValueError('stable claim exceeds resource guard')
    stable=[p for p in optimized if p['stable']]
    return dict(schema='arena.a8.capacity.v1',passed=True,before=baseline,after=optimized,
        maximum_completed_rooms=max(p['rooms'] for p in stable),
        recommended_rooms=max(stable,key=lambda p:p['games_per_hour'])['rooms'],
        recommendation_scope='Measured frozen-input workload; choose the best completed batch throughput. No claim for untested heavier policy workloads.',
        guards=dict(max_new_swapout_bytes=2*2**30,critical_pressure=4),
        interpretation='Failed/guarded attempts remain in the report. Do not extrapolate single-room FPS to aggregate throughput.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True)
    p.add_argument('--points',type=Path,nargs='*',default=[]);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=analyze(a.before,a.after,a.points);write_json_atomic(a.out,r);print(a.out)
