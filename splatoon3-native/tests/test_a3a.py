#!/usr/bin/env python3
"""A3a gate: native geometry + allowlisted subprocess + explicit unknowns.

Saved evidence diagnoses/rechecks partial results; it never signs a fresh
milestone. Paint/events remain unknown until the deferred A3b implementation.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.native_referee import NativeRefereeAdapter


def native_run(command,log,timeout):
    child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:return child.wait(timeout)
    except BaseException:
        if child.poll() is None:
            child.send_signal(signal.SIGINT)  # Let the driver sample/close native hosts.
            try:child.wait(60)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(5)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(5)
        raise


def main(args):
    out=ROOT/'work/tests'/datetime.datetime.now().strftime('a3a-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(passed=False,full_a3a_passed=False,errors=[],artifacts=str(out),replay_only=args.native_evidence is not None)
    evidence=args.native_evidence
    try:
        if evidence is None:
            before=set((ROOT/'work/tests').glob('a3-visibility-*'))
            with (out/'native.log').open('w') as log:
                returncode=native_run([sys.executable,str(ROOT/'tests/probe_a3_visibility.py'),'--timeout',str(args.timeout)],
                                      log,args.timeout+120)
            made=set((ROOT/'work/tests').glob('a3-visibility-*'))-before
            if len(made)!=1:raise AssertionError('native A3 evidence directory ambiguous')
            evidence=made.pop()/'result.json'
            if returncode:result['errors'].append('native scenario driver failed')
        evidence=Path(evidence).resolve()
        if not evidence.is_relative_to(ROOT/'work'):raise ValueError('native evidence must remain under work/')
        native=json.loads(evidence.read_text());result['native_evidence']=str(evidence)
        expected={'open-facing':True,'squid-observer-open':True,'back-facing':False,
                  'open-return':True,'wall':False,'high-platform':False,'submerged-still':False}
        cases={c['label']:c for c in native['cases']}
        result['geometry_cases']={name:bool(name in cases and cases[name]['visible']==value and
            Path(cases[name]['native_image']).is_file()) for name,value in expected.items()}
        if not all(result['geometry_cases'].values()):result['errors'].append('native screenshot scenario coverage incomplete')
        if not native.get('probe_completed'):result['errors'].append('native diagnostic did not complete')
        rows=[json.loads(s) for s in evidence.with_name('steps.jsonl').read_text().splitlines()]
        agents=list(rows[0]['infos']);adapter=NativeRefereeAdapter(out.name,rows[0]['infos'],dict.fromkeys(agents,8000),dict(zip(agents,(0,1))))
        paint_samples=0;knockdown_samples=0;attributed=0
        for row in rows:
            truth=adapter.snapshot(row['infos']);paint_samples+=truth.paint is not None;knockdown_samples+=truth.knockdowns is not None
            if truth.knockdowns is not None:attributed+=sum(e.attacker is not None and e.weapon==8000 for e in truth.knockdowns)
        result.update(native_paint_samples=paint_samples,native_knockdown_samples=knockdown_samples,native_attributed_events=attributed)
        result['deferred_fields_unknown'] = paint_samples == 0 and knockdown_samples == 0
        if not result['deferred_fields_unknown']:result['errors'].append('A3b fields must remain explicitly unknown')
        result['motion_exceptions_passed'] = all(native.get(k, {}).get('visible') is True for k in ('airborne', 'splash'))
        if not result['motion_exceptions_passed']:result['errors'].append('native jump/splash exceptions incomplete')
        run=subprocess.run([sys.executable,str(ROOT/'tests/probe_a3_policy_replay.py'),str(evidence)],capture_output=True,text=True,timeout=30)
        (out/'policy-process.log').write_text(run.stdout+run.stderr);result['policy_process_passed']=run.returncode==0
        if run.returncode:result['errors'].append('native-state policy process replay failed')
        if args.native_evidence is not None:result['errors'].append('saved-evidence replay is not fresh native acceptance')
        result['passed']=result['full_a3a_passed']=not result['errors']
    except BaseException as e:result['errors'].append(repr(e))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--timeout',type=float,default=2400)
    p.add_argument('--native-evidence',type=Path,help='diagnostic replay only; never signs the milestone')
    raise SystemExit(main(p.parse_args()))
