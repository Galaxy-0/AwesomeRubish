#!/usr/bin/env python3
"""Fresh A4 and explicitly documented scorecard supplement after queue drain.

Preserve failed/cancelled attempts and their hashes; inherit only completed
version-bound jobs. Run the same complete three-map fixture alone. An explicit
natural-match-exhaustion witness may also require all three full cards to use
independent static repeats, with unchanged trial budgets and scoring rules.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor,as_completed

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from audit_a7 import sha,require,current,reference,read
from arena.runner import write_json_atomic
from rl.native_start import validate_runtime
from arena.proficiency import matching_card
from arena.config import PolicySpec
from test_a6 import audit_cards


def main(args):
    previous=args.previous.resolve();old=previous.parent;original=read(previous);plan=read(old/'plan.json')
    require('a5_historical_audit' in original,'original queue must drain before supplementing')
    failed_names={n for n,j in original['jobs'].items() if not j['passed']}
    cards={'card-reference','card-alpha','card-bravo'} if args.fixture_adjustment else set()
    a5={'a5'} if args.return_failure else set()
    require(failed_names=={'a4'}|cards|a5,'unexpected failed jobs')
    require(set(original['errors'])<=({'three fresh scorecards required'} if cards else set()),'unresolved aggregate errors')
    if cards:
        adjustment=read(args.fixture_adjustment)
        require(adjustment['kind']=='independent_static_repeats' and adjustment['full_card_trials']==13 and adjustment['trial_budget_frames']==240 and not adjustment['changed_scoring'] and not adjustment['changed_match_duration'],'unexpected fixture adjustment')
        for key in ('failed_native_run','old_driver','new_driver','cancellation'):
            require(sha(ROOT/adjustment[key])==adjustment[key+'_sha256'],'fixture adjustment changed '+key)
        require(any('normal match duration exhausted' in e for e in read(ROOT/adjustment['failed_native_run'])['errors']),'normal match exhaustion witness required')
    else:require(original['a6_independent_card_audit'],'missing original card audit')
    failed=read(original['jobs']['a4']['record'])
    logs=[]
    for evidence in failed['evidence']:
        require(sha(evidence['path'])==evidence['sha256'],'failed native evidence changed')
        value=read(evidence['path'])
        for session in value.get('sessions',[]):
            logs.extend(Path(session).glob('player-*/host.log'))
    texts=[p.read_text(errors='replace') for p in set(logs)]
    require(any('FATAL RL_STALL no present progress' in t for t in texts),'native progress watchdog witness required')
    require(not any('A8_CAMERA unsafe' in t or 'A8_HDR unsafe' in t for t in texts),'render safety abort cannot be retried as a watchdog')
    host,modules=validate_runtime(plan['host'],plan['patched'])
    require(sha(host)==original['host_sha256'],'production runtime changed')
    if a5:
        returned=read(args.return_failure)
        require(returned['fixture']=='a5-second-reset' and returned['first_match_valid'] and returned['second_match_input_bytes']==0,'unexpected A5 return failure')
        for row in returned['logs'].values():require(sha(row['path'])==row['sha256'],'old return log changed')
    for name,job in original['jobs'].items():
        if 'record' in job:
            require(sha(job['record'])==job['record_sha256'],'original job changed '+name)
            current(read(job['record'])['runtime_sha256'])
    out=args.out.resolve();require(out.is_relative_to(ROOT/'work'),'raw supplement must remain under work')
    out.mkdir(parents=True,exist_ok=False)
    slots=out/'loader-slots';slots.mkdir()
    for n in (0,1):(slots/f'slot-{n}').touch()
    if not cards:
        for name in ('reference','alpha','bravo'):
            for suffix in ('.json','.md'):
                source=old/('card-'+name+'-scorecard'+suffix)
                require(source.exists(),'missing original scorecard')
                shutil.copyfile(source,out/source.name)
    report=copy.deepcopy(original);report.update(passed=False,supplemented_from=reference(previous),
        superseded_failures={n:original['jobs'][n] for n in failed_names},superseded_aggregate_errors=original['errors'],errors=[],supplement_started_wall=time.time(),
        fixture_adjustment=reference(args.fixture_adjustment) if cards else None,
        return_failure=reference(args.return_failure) if a5 else None,
        supplement_scope='User-authorized fresh-process A5 pair; fresh complete A4 alone, then three full cards with separate static matches. Only source-identical completed original jobs retained')
    updated=copy.deepcopy(plan);updated.update(supplemented_plan=reference(old/'plan.json'),retry_jobs=sorted(failed_names),
        supplement_entry_sha256=sha(__file__),supplement_parallel=3 if cards else 1)
    write_json_atomic(out/'plan.json',updated)
    def save():
        report['wall_seconds']=original['wall_seconds']+time.time()-report['supplement_started_wall']
        write_json_atomic(out/'result.json',report)
    save()
    if a5:
        require(read(ROOT/'arena/default-runtime.json').get('session_lifecycle')=='fresh_per_match','explicit fresh-process fallback configuration required')
        before=set((ROOT/'work/arena').glob('tournament-*'))
        command=[sys.executable,str(ROOT/'tests/test_a5.py'),'--games','2','--parallel','1',
            '--native-host',str(host),'--native-patched',str(modules),'--timeout','2400']
        with (out/'a5.log').open('w') as log:code=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
        value=dict(exit_code=code,passed=False,command=command,log_sha256=sha(out/'a5.log'))
        if code==0:
            made=set((ROOT/'work/arena').glob('tournament-*'))-before
            require(len(made)==1,'fresh A5 evidence ambiguous')
            path=made.pop()/'result.json';native=read(path);valid=[m for m in native['matches'] if m['passed']]
            same=len(valid)==2 and valid[0]['host_pids']==valid[1]['host_pids']
            fresh=(len(valid)==2 and not set(valid[0]['host_pids'])&set(valid[1]['host_pids']))
            value.update(evidence=str(path),evidence_sha256=sha(path),continuous_same_pids=same,fresh_processes=fresh,
                session_lifecycle='fresh_per_match',
                passed=native['phase_passed'] and native['statistics']['valid_games']==2 and fresh and {tuple(m['role_to_policy']) for m in valid}=={(0,1),(1,0)})
        report['jobs']['a5']=value;print('fresh A5',value['passed'],flush=True);save()
        if not value['passed']:return report
    record=out/'a4.json'
    command=[sys.executable,str(ROOT/'tests/run_native_regression.py'),'--host',str(host),'--patched',str(modules),
        '--record',str(record),'--shared-load-slots',str(slots),str(ROOT/'tests/test_a4.py'),
        '--timeout','2400','--existing-maps','--damage-job',str(old/'damage.json')]
    with (out/'a4.log').open('w') as log:code=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
    bound=read(record)
    report['jobs']['a4']=dict(exit_code=code,passed=code==0 and bound['passed'],command=command,
        record=str(record),record_sha256=sha(record),log_sha256=sha(out/'a4.log'))
    print('fresh A4',report['jobs']['a4']['passed'],flush=True);save()
    if cards and report['jobs']['a4']['passed']:
        jobs=[j for j in plan['jobs'] if j['name'] in cards]
        def run_card(job):
            name=job['name'];command=[sys.executable,str(ROOT/'tests/proficiency.py'),'--policy',job['policy'],
                '--out',str(out/(name+'-scorecard.json')),'--repeats','3','--native-host',str(host),
                '--native-patched',str(modules),'--timeout','2400','--shared-load-slots',str(slots)]
            with (out/(name+'.log')).open('w') as log:code=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
            return name,dict(exit_code=code,passed=code==0,command=command,log_sha256=sha(out/(name+'.log')))
        with ThreadPoolExecutor(max_workers=3) as pool:
            for future in as_completed([pool.submit(run_card,j) for j in jobs]):
                name,value=future.result();report['jobs'][name]=value;print(name,value['passed'],flush=True);save()
        if all(report['jobs'][j['name']]['passed'] for j in jobs):
            measured=[];items=[];runtime=dict(host=str(host),patched=str(modules))
            for job in jobs:
                path=out/(job['name']+'-scorecard.json');card=read(path)
                require(card['measured']==card['total']==13,'incomplete fresh card')
                require(matching_card(path,PolicySpec.load(job['policy']),runtime)['status']=='available','fresh evaluator binding failed')
                measured.append(card);items.append(dict(policy_root=job['policy']))
            audit_cards(dict(scorecards=items),measured);report['a6_independent_card_audit']=True
        else:report['errors'].append('fresh scorecard failed')
    report['passed']=all(j['passed'] for j in report['jobs'].values()) and not report['errors'];save()
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--previous',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--fixture-adjustment',type=Path,help='Version-bound natural-match-exhaustion witness; remeasure all three cards')
    p.add_argument('--return-failure',type=Path,help='Preserved A5 second-reset failure; first rerun the complete same-PID swapped pair')
    r=main(p.parse_args());print(json.dumps(r,indent=2));raise SystemExit(0 if r['passed'] else 1)
