#!/usr/bin/env python3
"""A5: at least 70 native swapped games, four concurrent 1v1 matches."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.runner import tournament


def main(args):
    report=tournament(args.policy_a,args.policy_b,args.games,args.parallel,args.timeout,early_rate_check=args.fallback_three and args.parallel==4,resume=args.resume)
    if args.fallback_three and args.parallel==4 and report.get('stop_reason') in ('void_budget_exceeded','four_room_void_rate_above_10_percent'):
        comparison=dict(artifacts=report['artifacts'],statistics=report['statistics'],stop_reason=report['stop_reason'])
        report=tournament(args.policy_a,args.policy_b,args.games,3,args.timeout,resume=Path(report['artifacts'])/'result.json')
        report['four_room_comparison']=comparison
    report['diagnostic_only']=args.games<70 or args.parallel not in (3,4)
    # A smoke phase may finish normally without signing A5.
    phase_passed=report['passed'];report['phase_passed']=phase_passed
    report['passed']=report['full_a5_passed']
    Path(report['artifacts'],'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='matches'},indent=2),flush=True)
    return 0 if (phase_passed if report['diagnostic_only'] else report['full_a5_passed']) else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--policy-a',type=Path,default=ROOT/'arena/policies/rush')
    p.add_argument('--policy-b',type=Path,default=ROOT/'arena/policies/high-ground');p.add_argument('--games',type=int,default=70)
    p.add_argument('--parallel',type=int,choices=(1,2,3,4),default=4);p.add_argument('--timeout',type=float,default=7200)
    p.add_argument('--fallback-three',action='store_true',help='Drain excessive four-room voids and resume remaining fixtures in three rooms')
    p.add_argument('--resume',type=Path,help='Preserve completed fixtures from an audited checkpoint')
    raise SystemExit(main(p.parse_args()))
