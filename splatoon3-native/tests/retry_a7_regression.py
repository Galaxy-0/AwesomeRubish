#!/usr/bin/env python3
"""Supplement completed A7 regression evidence without erasing failed attempts.

Only the known A2 collector, closed-log roll audit, and test-build special jobs
may be rerun here. Game runtime/source hashes of every inherited job must still
match. The original run and all failed artifacts remain untouched.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from arena.runner import write_json_atomic
from rl.native_start import validate_runtime
from audit_a7 import sha,require,current,reference


def main(args):
    previous=args.previous.resolve();original=json.loads(previous.read_text());old=previous.parent
    plan=json.loads((old/'plan.json').read_text())
    require('a5_historical_audit' in original,'original queue must finish before supplementing')
    require(not original['errors'],'unresolved aggregate errors require investigation')
    failed={name for name,job in original['jobs'].items() if not job['passed']}
    require(failed and failed<={'a2','a6-roll','a6-special'},'unexpected failed jobs: '+repr(failed))
    host,modules=validate_runtime(plan['host'],plan['patched']);require(sha(host)==original['host_sha256'],'production runtime changed')
    special,_=validate_runtime(args.special_host,modules)
    for name,job in original['jobs'].items():
        if 'record' in job:
            require(sha(job['record'])==job['record_sha256'],'original job changed '+name)
            current(json.loads(Path(job['record']).read_text())['runtime_sha256'])
    out=args.out.resolve();require(out.is_relative_to(ROOT/'work'),'raw supplement must stay under work')
    out.mkdir(parents=True,exist_ok=False);slots=out/'loader-slots';slots.mkdir()
    for n in (0,1):(slots/f'slot-{n}').touch()
    report=copy.deepcopy(original);report.update(passed=False,supplement_started_wall=time.time(),
        supplemented_from=reference(previous),superseded_failures={name:original['jobs'][name] for name in failed})
    updated_plan=copy.deepcopy(plan);updated_plan.update(supplemented_plan=reference(old/'plan.json'),
        retry_jobs=sorted(failed),supplement_entry_sha256=sha(__file__),special_host=str(special))
    write_json_atomic(out/'plan.json',updated_plan)
    for name in ('reference','alpha','bravo'):
        for suffix in ('.json','.md'):
            source=old/('card-'+name+'-scorecard'+suffix)
            if source.exists():shutil.copyfile(source,out/source.name)
    jobs=[j for j in plan['jobs'] if j['name'] in failed]
    def save():
        report['wall_seconds']=original['wall_seconds']+time.time()-report['supplement_started_wall'];write_json_atomic(out/'result.json',report)
    def run(job):
        name=job['name'];record=out/(name+'.json');chosen=special if name=='a6-special' else host
        command=[sys.executable,str(ROOT/'tests/run_native_regression.py'),'--host',str(chosen),'--patched',str(modules),'--record',str(record),'--shared-load-slots',str(slots),str(ROOT/'tests'/job['script']),*job['args']]
        with (out/(name+'.log')).open('w') as log:code=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
        bound=json.loads(record.read_text())
        return name,dict(exit_code=code,passed=code==0 and bound['passed'],command=command,record=str(record),record_sha256=sha(record),log_sha256=sha(out/(name+'.log')))
    save()
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        for future in as_completed([pool.submit(run,j) for j in jobs]):
            name,value=future.result();report['jobs'][name]=value;print(name,value['passed'],flush=True);save()
    report['passed']=all(j['passed'] for j in report['jobs'].values()) and not report['errors'];save();return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--previous',type=Path,required=True);p.add_argument('--special-host',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--parallel',type=int,choices=(1,2,3),default=3)
    result=main(p.parse_args());print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
