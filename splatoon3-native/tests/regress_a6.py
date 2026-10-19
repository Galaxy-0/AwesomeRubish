#!/usr/bin/env python3
"""After T1 exits: sequential A1–A5 regression without rebuilding dmhost.

A1/A2/A3a/A4 run their full fresh native gates. A5 reaudits the accepted 70
native games with its unchanged strict hash checks, plus two fresh swapped
games through the new coordinator/control wire, parallel=1. This does not
pretend that two new games constitute a new 70-game acceptance.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from a6_lab import ROOT,t1_running
from test_a3a import native_run


def main(args):
    if t1_running():raise SystemExit('T1 coordinator still running: regression not started')
    out=ROOT/'work/a6'/datetime.datetime.now().strftime('regression-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(passed=False,errors=[],milestones={},artifacts=str(out),rooms_parallel=1)
    host=ROOT/'upstream/dm/host/dmhost';host_hash=hashlib.sha256(host.read_bytes()).hexdigest()
    def save():
        if hashlib.sha256(host.read_bytes()).hexdigest()!=host_hash:raise AssertionError('default dmhost changed')
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    def run(command,name,timeout=120):
        with (out/(name+'.log')).open('w') as log:
            code=native_run(command,log,timeout)
        if code:raise AssertionError(name+' failed, inspect '+str(out/(name+'.log')))
    def milestone(name,extra=()):
        pattern=name+'-[0-9]*'  # gate directories, excluding a4-routes-* children
        before=set((ROOT/'work/tests').glob(pattern))
        run([sys.executable,str(ROOT/'tests'/('test_'+name+'.py')),'--timeout',str(args.timeout),*extra],name,4*args.timeout+120)
        made=set((ROOT/'work/tests').glob(pattern))-before
        paths=[p/'result.json' for p in made if (p/'result.json').is_file()]
        if len(paths)!=1:raise AssertionError('ambiguous regression evidence: '+name)
        native=json.loads(paths[0].read_text())
        if not native['passed']:raise AssertionError('native milestone failed: '+name)
        result['milestones'][name]=dict(passed=True,evidence=str(paths[0]),sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest())
        save();print(name+' passed',flush=True)
    try:
        # Separate test outputs; no make target ever names default dmhost.
        targets=['t_rl','t_hid_rl','t_rl_clock','t_rl_sleep','t_rl_idle','t_condvar','t_rl_watchdog','t_rl_long_wait','t_spl3_gear']
        run(['make','-C',str(ROOT/'upstream/dm/host/tests'),'GAME=0100C2500FC20000',*['build/'+t for t in targets]],'component-build',600)
        for binary,arguments in [('t_hid_rl',[]),('t_rl_clock',[]),('t_rl_clock',['manual']),('t_rl_clock',['fixed60']),('t_rl_sleep',[]),('t_rl_idle',[]),('t_condvar',[]),('t_rl_watchdog',[]),('t_rl_long_wait',[])]:
            run([str(ROOT/'upstream/dm/host/tests/build'/binary),*arguments],binary,180)
        for test in ('test_m6_transport','test_rl_watchdog','test_a2_components','test_a3_components','test_a3_geometry','test_a3_process','test_a4_components','test_a4_process','test_a5_components','test_a5_process','test_a6_process'):
            run([sys.executable,str(ROOT/'tests'/(test+'.py'))],test,180)
        for name in ('a1','a2','a3a','a4'):milestone(name)
        archive=ROOT/'arena/results/a5-paused-70-20261019.json'
        audit=out/'a5-accepted70-audit.json'
        run([sys.executable,'-m','arena.a5_audit',str(archive),'--out',str(audit)],'a5-accepted70-audit',600)
        before=set((ROOT/'work/arena').glob('tournament-*'))
        run([sys.executable,str(ROOT/'tests/test_a5.py'),'--games','2','--parallel','1','--timeout',str(args.timeout)],'a5-fresh-swapped',4*args.timeout+120)
        made=set((ROOT/'work/arena').glob('tournament-*'))-before
        if len(made)!=1:raise AssertionError('ambiguous A5 smoke evidence')
        fresh=made.pop()/'result.json';value=json.loads(fresh.read_text())
        accepted=json.loads(audit.read_text())
        if not accepted['accepted'] or not value['phase_passed'] or value['statistics']['valid_games']!=2:
            raise AssertionError('A5 archive or new control-wire smoke failed')
        result['milestones']['a5']=dict(passed=True,accepted_native70_inherited=True,archive_audit=str(audit),
                                        archive_audit_sha256=hashlib.sha256(audit.read_bytes()).hexdigest(),
                                        fresh_swapped_games=2,fresh_rooms_parallel=1,evidence=str(fresh),
                                        evidence_sha256=hashlib.sha256(fresh.read_bytes()).hexdigest(),
                                        fresh_full_a5_passed=value['full_a5_passed'])
        result['passed']=True
    except BaseException as e:result['errors'].append(repr(e))
    finally:save()
    print(out,flush=True);return 0 if result['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--timeout',type=float,default=3600)
    raise SystemExit(main(parser.parse_args()))
