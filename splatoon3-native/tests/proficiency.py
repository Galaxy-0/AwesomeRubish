#!/usr/bin/env python3
"""Run a version-bound A6 card in one room at a time, alongside a T1 BO3."""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.proficiency import merge_cards,write_card,table
from arena.runner import link_load_slots,write_json_atomic
from arena.t1 import DEFAULT_SLOTS
from arena.versions import snapshot_policy,loader_slots
from rl.session import Session
from rl.native_start import NativeSession
from arena.native_runtime import add_arguments,from_args,close_pools
from a6_lab import Lab
import benchmark_a6


def episodes(repeats):
    if repeats not in (1,2,3):raise ValueError('repeats must be 1..3')
    # A kill can require almost a minute of ordinary game time to respawn and
    # reposition the target. Static repeats need separate matches; otherwise
    # a capable policy can exhaust 180 seconds before the third scored window.
    # Keep the same trial count, inputs, per-trial budget and scoring rules.
    lateral=[[6.,12.,18.]] if repeats==1 else [[6.],[12.],[18.]]
    return [('stationary',None)]*repeats+[('lateral',d) for d in lateral]+[('approach',None)]


def episode_repeats(scenario,repeats):
    return 1 if scenario in ('stationary','approach') else repeats


def run(policy,out,repeats=3,timeout=3600,shared_slots=DEFAULT_SLOTS,native_runtime=None):
    if os.environ.get('DM_TEST_SPECIAL'):
        raise ValueError('main-weapon proficiency uses natural meter; unset DM_TEST_SPECIAL (special tests use probe_a6_test_special.py)')
    if not math.isfinite(timeout) or timeout<=0:raise ValueError('timeout must be positive and finite')
    jobs=episodes(repeats);out=Path(out).resolve()
    if out.suffix!='.json':out=out/'scorecard.json'
    if out.exists() or out.with_suffix('.md').exists():raise FileExistsError(out)
    artifacts=ROOT/'work/arena'/datetime.datetime.now().strftime('proficiency-%Y%m%d-%H%M%S-%f')
    artifacts.mkdir(parents=True)
    spec=snapshot_policy(policy,artifacts/'policy');shared=loader_slots(shared_slots)
    report=dict(schema='arena.proficiency.run.v1',passed=False,errors=[],artifacts=str(artifacts),
        policy=spec.name,source_sha256=spec.source_sha256,source_policy=str(Path(policy).resolve()),
        policy_snapshot=str(spec.root),repeats=repeats,shared_load_slots=str(shared),
        scorecard=str(out),cards=[],native_windows=[],started_wall=time.time(),
        entry_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),native_runtime=native_runtime)
    windows={};last_save=0

    def save():
        report['elapsed_wall_seconds']=time.time()-report['started_wall']
        write_json_atomic(artifacts/'result.json',report)

    original_start=Session.start;original_native_start=NativeSession.start;original_step=Lab.step

    def start(session):
        link_load_slots(session,shared)
        return original_start(session)

    def native_start(session):
        link_load_slots(session,shared)
        return original_native_start(session)

    def step(lab,*args,**kwargs):
        nonlocal last_save
        result=original_step(lab,*args,**kwargs);now=time.time()
        identity=str(lab.out)
        if identity not in windows:
            window=dict(artifacts=str(lab.out),controlled_start_wall=now,last_progress_wall=now,
                        host_pids=[p.pid for _,p,_ in lab.env.session.hosts])
            windows[identity]=window;report['native_windows'].append(window)
        windows[identity]['last_progress_wall']=now
        if now-last_save>10:save();last_save=now
        return result

    save()
    try:
        with patch.object(Session,'start',start),patch.object(NativeSession,'start',native_start),patch.object(Lab,'step',step):
            for n,(scenario,distances) in enumerate(jobs):
                path=artifacts/f'card-{n}-{scenario}.json'
                args=argparse.Namespace(policy=spec.root,scenario=scenario,
                    repeats=episode_repeats(scenario,repeats),distances=distances,
                    out=path,timeout=timeout,roll_calibration=ROOT/'work/a6/roll-calibration.json',
                    verify_emerge=False,emerge_frames=26,native_runtime=native_runtime)
                if benchmark_a6.main(args)!=0:raise RuntimeError('native proficiency episode failed: '+scenario+'; see retained raw result')
                card=json.loads(path.read_text())
                if card['source_sha256']!=spec.source_sha256:raise AssertionError('benchmark source differs from captured version')
                report['cards'].append(str(path));save()
        card=merge_cards(report['cards'])
        card['policy_version']=dict(source_policy=report['source_policy'],snapshot=str(spec.root),
                                   run_artifacts=str(artifacts),source_sha256=spec.source_sha256)
        write_card(out,card);out.with_suffix('.md').write_text(table(card))
        report['passed']=True
    except BaseException as error:report['errors'].append(repr(error))
    finally:
        if native_runtime:
            try:close_pools()
            except BaseException as error:report['errors'].append('native cleanup: '+repr(error));report['passed']=False
    save()
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--policy',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--repeats',type=int,choices=(1,2,3),default=3,help='1 gives a five-trial smoke; default gives 13 trials')
    p.add_argument('--timeout',type=float,default=3600,help='per-room deadline')
    p.add_argument('--shared-load-slots',type=Path,default=DEFAULT_SLOTS)
    add_arguments(p)
    args=p.parse_args();result=run(args.policy,args.out,args.repeats,args.timeout,args.shared_load_slots,from_args(args))
    print(json.dumps(result,indent=2),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
