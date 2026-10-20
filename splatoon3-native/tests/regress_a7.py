#!/usr/bin/env python3
"""Version-bound A1-A6 regression on an alternate native host, max 3 rooms.

A5 retains the exact historical accepted70 audit and adds two fresh swapped
single-room games. A6 reruns supported operations/controls, range brackets,
charge thresholds, full/infinite lifecycles, and all three frozen five-trial
scorecards. Unsupported weapon/fixture claims remain inherited explicitly.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from arena.runner import write_json_atomic
from arena.proficiency import matching_card
from arena.config import PolicySpec
from rl.native_start import validate_runtime
from probe_a7_trial import sha


def main(args):
    host,modules=validate_runtime(args.host,args.patched);out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    slots=out/'loader-slots';slots.mkdir()
    for n in (0,1):(slots/f'slot-{n}').touch()
    jobs=[]
    def fixture(name,script,*extra):jobs.append(dict(name=name,kind='fixture',script=script,args=list(extra)))
    for name in ('a1','a2','a3a'):fixture(name,'test_'+name+'.py','--timeout','2400')
    fixture('damage','probe_a4_skills.py','--stage','1','--damage','--timeout','2400')
    fixture('a6-timing','probe_a6_refine.py','--timeout','2400')
    for suite in ('combat','combo_bomb','roll','aim_surge','special'):fixture('a6-'+suite,'probe_a6_regression.py','--suite',suite,'--timeout','2400')
    for kind,distances in [('light',['18','20']),('full',['22','23'])]:fixture('a6-range-'+kind,'probe_a6_combat.py','--phase','range','--kind',kind,'--range-distances',*distances,'--precise-poses','--charge','21','--timeout','2400')
    fixture('a6-moving-emerge','benchmark_a6.py','--policy',str(ROOT/'work/a6/frozen-policies-20261019-150539/arena/proficiency-reference'),'--scenario','approach','--repeats','1','--verify-emerge','--emerge-frames','26','--out',str(out/'moving-emerge-card.json'),'--timeout','2400')
    for name,path in [('reference','arena/proficiency-reference'),('alpha','arena/policies/alpha'),('bravo','arena/policies/bravo')]:jobs.append(dict(name='card-'+name,kind='card',policy=str(ROOT/'work/a6/frozen-policies-20261019-150539'/path)))
    jobs.append(dict(name='a5',kind='a5'))
    write_json_atomic(out/'plan.json',dict(schema='arena.a7.regression-plan.v1',jobs=jobs,parallel=args.parallel,host=str(host),patched=str(modules),host_sha256=sha(host),entry_sha256=sha(__file__)))
    report=dict(schema='arena.a7.regression.v1',passed=False,jobs={},errors=[],started_wall=time.time(),parallel=args.parallel,host_sha256=sha(host))
    def save():report['wall_seconds']=time.time()-report['started_wall'];write_json_atomic(out/'result.json',report)
    def run(job):
        name=job['name'];record=out/(name+'.json')
        before=set((ROOT/'work/arena').glob('tournament-*')) if job['kind']=='a5' else set()
        if job['kind']=='fixture':command=[sys.executable,str(ROOT/'tests/run_native_regression.py'),'--host',str(host),'--patched',str(modules),'--record',str(record),'--shared-load-slots',str(slots),str(ROOT/'tests'/job['script']),*job['args']]
        elif job['kind']=='card':command=[sys.executable,str(ROOT/'tests/proficiency.py'),'--policy',job['policy'],'--out',str(out/(name+'-scorecard.json')),'--repeats','1','--native-host',str(host),'--native-patched',str(modules),'--timeout','2400','--shared-load-slots',str(slots)]
        else:command=[sys.executable,str(ROOT/'tests/test_a5.py'),'--games','2','--parallel','1','--native-host',str(host),'--native-patched',str(modules),'--timeout','2400']
        with (out/(name+'.log')).open('w') as log:code=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
        result=dict(exit_code=code,passed=code==0,command=command,log_sha256=sha(out/(name+'.log')))
        if job['kind']=='a5' and code==0:
            made=set((ROOT/'work/arena').glob('tournament-*'))-before
            if len(made)!=1:raise AssertionError('fresh A5 evidence ambiguous')
            path=made.pop()/'result.json';value=json.loads(path.read_text())
            result.update(evidence=str(path),evidence_sha256=sha(path),passed=bool(value['phase_passed'] and value['statistics']['valid_games']==2 and {tuple(m['role_to_policy']) for m in value['matches'] if m['passed']}=={(0,1),(1,0)}))
        if record.exists():result['record']=str(record);result['record_sha256']=sha(record)
        print(name,'exit',code,flush=True)
        return name,result
    save()
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        for future in as_completed([pool.submit(run,job) for job in jobs]):
            name,result=future.result();report['jobs'][name]=result;save()
    if report['jobs']['damage']['passed']:
        job=dict(name='a4',kind='fixture',script='test_a4.py',args=['--timeout','2400','--existing-maps','--damage-job',str(out/'damage.json')])
        name,value=run(job);report['jobs'][name]=value;save()
    else:report['errors'].append('fresh A4 damage failed; full routes not signed')
    runtime=dict(host=str(host),patched=str(modules))
    for job in jobs:
        if job['kind']=='card' and report['jobs'][job['name']]['passed']:
            value=matching_card(out/(job['name']+'-scorecard.json'),PolicySpec.load(job['policy']),runtime)
            if value['status']!='available':report['errors'].append('fresh scorecard binding failed '+job['name'])
            card=json.loads((out/(job['name']+'-scorecard.json')).read_text())
            if card['measured']!=card['total'] or card['total']!=5:report['errors'].append('fresh five-trial card incomplete '+job['name'])
    report['passed']=all(x['passed'] for x in report['jobs'].values()) and not report['errors'];save();return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',type=Path,required=True);p.add_argument('--patched',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--parallel',type=int,choices=(1,2,3),default=3)
    r=main(p.parse_args());print(json.dumps(r,indent=2));raise SystemExit(0 if r['passed'] else 1)
