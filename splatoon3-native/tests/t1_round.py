#!/usr/bin/env python3
"""Run all three maps of one T1 BO3; a/b always refer to CLI policy order."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.t1 import run_round,DEFAULT_SLOTS
from arena.native_runtime import add_arguments,from_args


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--policy-a',type=Path,required=True);p.add_argument('--policy-b',type=Path,required=True)
    p.add_argument('--round',type=int,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--timeout',type=float,default=7200)
    p.add_argument('--shared-load-slots',type=Path,default=DEFAULT_SLOTS)
    add_arguments(p)
    args=p.parse_args()
    result=run_round(args.policy_a,args.policy_b,args.round,args.out,args.timeout,args.shared_load_slots,from_args(args))
    print(json.dumps(dict(passed=result['passed'],result=str(Path(args.out)/'result.json'),errors=result['errors']),indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
