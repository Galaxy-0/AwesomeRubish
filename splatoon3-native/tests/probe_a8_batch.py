#!/usr/bin/env python3
"""Fresh, version-bound A8 trials at a fixed room concurrency."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import time
from probe_a7_trial import ROOT,sha
from arena.runner import write_json_atomic


def main(args):
    out=args.out.resolve()
    if not out.is_relative_to(ROOT/'work'):raise ValueError('raw trials must stay under work/')
    out.mkdir(parents=True,exist_ok=False);slots=out/'loader-slots';slots.mkdir()
    for n in range(2):(slots/f'slot-{n}').touch()
    plan=dict(schema='arena.a8.batch.v1',host=str(args.host.resolve()),patched=str(args.patched.resolve()),
        policies=str(args.policies.resolve()),repeats=args.repeats,parallel=args.parallel,
        entry_sha256=sha(__file__),trial_entry_sha256=sha(ROOT/'tests/probe_a8_trial.py'),
        seed_words=[1,2,3,4],stage=2,started_wall=time.time())
    write_json_atomic(out/'plan.json',plan)
    def run(n):
        command=[sys.executable,str(ROOT/'tests/probe_a8_trial.py'),'--host',plan['host'],'--patched',plan['patched'],
            '--policies',plan['policies'],'--out',str(out/f'trial-{n}'),'--shared-load-slots',str(slots)]
        with (out/f'trial-{n}.log').open('w') as log:code=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
        print(n,code,flush=True);return code
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:codes=list(pool.map(run,range(args.repeats)))
    result=dict(schema=plan['schema'],passed=not any(codes),exit_codes=codes,plan_sha256=sha(out/'plan.json'),
        wall_seconds=time.time()-plan['started_wall'])
    write_json_atomic(out/'completed.json',result)
    return int(any(codes))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('host','patched','policies','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--repeats',type=int,choices=range(1,7),default=3)
    p.add_argument('--parallel',type=int,choices=range(1,7),default=3)
    raise SystemExit(main(p.parse_args()))
