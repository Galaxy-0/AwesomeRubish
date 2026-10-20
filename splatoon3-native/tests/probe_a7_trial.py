#!/usr/bin/env python3
"""One version-bound frozen-input trial, menu or production native startup."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena import runner
from arena.versions import snapshot_policy
from rl import NativeParallelEnv
from rl.session import Session
from rl.native_start import NativeSession,validate_runtime
import rl.session as session_module


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(args):
    host,modules=validate_runtime(args.host,args.patched)
    out=args.out.resolve()
    if not out.is_relative_to(ROOT/'work'):raise ValueError('raw trials must stay under work/')
    out.mkdir(parents=True,exist_ok=False)
    sources=[ROOT/'arena'/name for name in ('runner.py','scoring.py','process.py','referee_api.py','visibility.py')]
    sources+=list((ROOT/'rl').glob('*.py'))
    frozen={str(p):sha(p) for p in [host,host.with_suffix('.build.json'),*sources,*[p for p in modules.iterdir() if p.is_file()]]}
    specs=[snapshot_policy(args.policies/name,out/'policies'/name) for name in ('rush','high-ground')]
    events=[];sessions=[];captured=[]
    report=dict(schema='arena.a7.repro-trial.v1',passed=False,errors=[],artifacts=str(out),route=args.route,
        stage=2,seed_words=[1,2,3,4],host_sha256=sha(host),runtime_sha256=frozen,
        source_hashes=[s.source_sha256 for s in specs],policy_step_frames=[s.step_frames for s in specs],events=events)
    def save():runner.write_json_atomic(out/'result.json',report)
    def mark(phase):
        if events and events[-1]['phase']==phase:return
        events.append(dict(phase=phase,wall=time.time()));save()
    base=Session if args.route=='menu' else NativeSession
    class TrialSession(base):
        def __init__(self,**kw):
            kw['patched']=modules
            if args.route=='native':kw['host']=host
            super().__init__(**kw);sessions.append(self)
        def host_command(self):return [str(host),str(modules)]
        def host_options(self,player):
            options=super().host_options(player)|dict(DM_RL_WAIT_INGAME='1',DM_SCENE_SEEDS='1,2,3,4',DM_SCENE_TRACE_SEEDS='1',DM_NVN_SHMAP=str(ROOT/'upstream/dm/games/0100C2500FC20000/shader_map.tsv'))
            if args.route=='menu':options|=dict(DM_SCENE_BOOT='trace',DM_SCENE_TRACE_FLOW='1')
            return options
    original_tick=Session.tick;original_prepare=session_module.prepare_match
    original_reset=NativeParallelEnv.reset;original_close=NativeParallelEnv.close
    original_settlement=runner.settlement_steps
    def tick(session,*a,**kw):
        result=original_tick(session,*a,**kw)
        air=session.out/'air.log'
        if events[-1]['phase']=='boot' and air.exists() and 'create player=0 ' in air.read_text():mark('room')
        if args.route=='native' and events[-1]['phase']=='room' and (session.out/'go.command').exists():mark('loading')
        return result
    def prepare(*a,**kw):mark('loading');return original_prepare(*a,**kw)
    def factory(*a,**kw):
        env=NativeParallelEnv(*a,**kw,session_factory=TrialSession);captured.append(env);return env
    def reset(env,*a,**kw):
        result=original_reset(env,*a,**kw);mark('controlled');return result
    def settle(*a,**kw):mark('settlement');yield from original_settlement(*a,**kw)
    def close(env):
        if env.session:mark('cleanup')
        return original_close(env)
    mark('boot');print(out,flush=True)
    try:
        with patch.object(Session,'tick',tick),patch.object(session_module,'prepare_match',prepare),patch.object(NativeParallelEnv,'reset',reset),patch.object(NativeParallelEnv,'close',close),patch.object(runner,'NativeParallelEnv',side_effect=factory),patch.object(runner,'settlement_steps',settle):
            report['match']=runner.run_match(dict(out=str(out/'match'),round=0,stage=2,roles=[0,1],policy_paths=[str(s.root) for s in specs],timeout=args.timeout,shared_load_slots=str(args.shared_load_slots.resolve())))
        mark('finished')
        report['phase_wall_seconds']={a['phase']:b['wall']-a['wall'] for a,b in zip(events,events[1:])}
        report['wall_seconds']=events[-1]['wall']-events[0]['wall']
        report['passed']=report['match']['passed'] and not report['match']['errors']
        if report['passed']:
            report['controlled_fps']=(report['match']['frames']-report['match']['settlement_frames'])/report['phase_wall_seconds']['controlled']
        report['gpu_utilization_percent_by_phase']={}
        for a,b in zip(events,events[1:]):
            values=[row['gpu']['Device Utilization %'] for s in sessions for row in s.monitor.rows if a['wall']<=row['time']<b['wall'] and 'Device Utilization %' in row['gpu']]
            report['gpu_utilization_percent_by_phase'][a['phase']]=dict(samples=len(values),mean=statistics.mean(values) if values else None,maximum=max(values) if values else None)
        if any(sha(p)!=digest for p,digest in frozen.items()):raise AssertionError('trial runtime changed')
    except BaseException as error:report['errors'].append(repr(error))
    finally:
        for env in captured:
            try:original_close(env)
            except BaseException as error:report['errors'].append('cleanup: '+repr(error))
    report['passed']=report['passed'] and not report['errors'];save();print(json.dumps(report,indent=2),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',type=Path,required=True);p.add_argument('--patched',type=Path,required=True)
    p.add_argument('--policies',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--route',choices=('menu','native'),required=True);p.add_argument('--timeout',type=float,default=2400)
    p.add_argument('--shared-load-slots',type=Path,required=True)
    raise SystemExit(main(p.parse_args()))
