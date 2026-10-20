"""Print/write a native calibration plan; actual execution is explicit/future-only."""
import argparse
import json
from pathlib import Path

from .plan import suite

ROOT=Path(__file__).resolve().parents[2]


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=ROOT/'work/sim/native-calibration')
    p.add_argument('--write-plan',action='store_true')
    p.add_argument('--execute-native',action='store_true')
    p.add_argument('--window',choices=['A7_A8_IDLE'])
    p.add_argument('--only',nargs='+',help='Exact case IDs, optionally select a subset of the same plan')
    p.add_argument('--timeout',type=float,default=3600.)
    a=p.parse_args(argv)
    plan=suite();out=a.out.resolve()
    if ROOT/'work' not in out.parents:
        p.error('calibration artifacts must stay under ignored work/')
    if a.execute_native:
        if a.window!='A7_A8_IDLE':
            p.error('native execution requires the explicitly scheduled A7/A8 idle window')
        from .native import execute  # deferred: never imported by plan/dry-run
        return execute(plan,out,a.only,a.timeout)
    if a.write_plan:
        out.mkdir(parents=True,exist_ok=True)
        (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(dict(native_started=False,cases=len(plan['cases']),
                         priority_followups=[dict(id=c['id'],priority=c['priority'],status=c['status']) for c in plan['priority_followups']],
                         measurement_repeats=sum(c['repeats'] for c in plan['cases']),
                         kinds=sorted({c['kind'] for c in plan['cases']}),
                         output=str(out),surface_truth=plan['surface_truth']),indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
