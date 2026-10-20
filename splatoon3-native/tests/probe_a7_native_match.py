#!/usr/bin/env python3
"""A7 checkpoint: one native no-menu Turf match on District00 through Winners.

This does not accept continuous games, the old-route comparison, or full A7.
"""
import argparse
import datetime
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
import rl.session as session_module


def main(args):
    if os.environ.get('DM_TEST_SPECIAL'):
        raise ValueError('A7 baseline rejects DM_TEST_SPECIAL')
    args.host=args.host.resolve();args.patched=args.patched.resolve()
    out=ROOT/'work/a7'/datetime.datetime.now().strftime('baseline-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    build=json.loads(args.host.with_suffix('.build.json').read_text())
    if sha(args.host)!=build['output_sha256']:raise AssertionError('host build identity mismatch')
    if any(sha(ROOT/name)!=digest for name,digest in build['source_sha256'].items()):raise AssertionError('host source identity mismatch')
    specs=[snapshot_policy(ROOT/'arena/policies'/name,out/'policies'/name) for name in ('rush','high-ground')]
    events=[];sessions=[];captured=[]
    report=dict(schema='arena.a7.direct-match.v1',passed=False,full_a7_passed=False,errors=[],artifacts=str(out),
                stage=args.stage,events=events,host_sha256=sha(args.host),source_hashes=[s.source_sha256 for s in specs],
                policy_step_frames=[s.step_frames for s in specs],rooms=1,
                route='native game controller create/search/join/start; native private settings; zero pregame HID',
                clock_mode='fixed60',pregame_controller_inputs=[],ocr_used=False,
                phase_definitions=dict(boot='launch until first native LDN create',
                    room='first create through peer boot/join, native room configuration and readiness',
                    loading='prepare_match begins through first paired InGame ACK',
                    controlled='paired InGame ACK through both agents terminate',
                    settlement='neutral progression after both terminate through Winners',cleanup='owned shutdown'))

    def mark(name):
        if events and events[-1]['phase']==name:return
        events.append(dict(phase=name,wall=time.time()));save()
    def save(): (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    original_start=Session.start;original_tick=Session.tick;original_options=Session.host_options
    original_prepare=session_module.prepare_match;original_reset=NativeParallelEnv.reset
    original_close=NativeParallelEnv.close;original_settlement=runner.settlement_steps
    import subprocess
    original_popen=subprocess.Popen
    def popen(command,*a,**kw):
        if str(command[0])==str(ROOT/'upstream/dm/host/dmhost'):command=[str(args.host),*command[1:]]
        return original_popen(command,*a,**kw)
    def options(session,player):
        return dict(original_options(session,player),DM_KEYS='',DM_SCENE_BOOT='LobbyLocal',DM_SCENE_TRACE_FLOW='1',DM_SCENE_TRACE_NETWORK='1',
            DM_PROBE='main:14f44cc@x1,main:3db55d0,main:3dcc710,main:3dd9370,main:3571e24@x21+e8',DM_SCENE_UPPER='1',DM_SCENE_DIRECT='create' if player==0 else 'join',DM_SCENE_MATCH=str(session.out/'go'),
            DM_NVN_SHMAP=str(ROOT/'upstream/dm/games/0100C2500FC20000/shader_map.tsv'))
    def start(session):
        import re,subprocess
        sessions.append(session)
        log=(session.out/'air.log').open('wb');session.streams.append(log)
        session.air=subprocess.Popen([sys.executable,str(ROOT/'tools/ldn/air.py'),'--socket',str(session.air_socket)],stdout=log,stderr=subprocess.STDOUT)
        session.until(session.air_socket.exists);session.spawn(0)
        session.until(lambda:'create player=0 ' in (session.out/'air.log').read_text());mark('room');session.spawn(1)
        session.until(lambda:'join player=1 ' in (session.out/'air.log').read_text())
        def joined():
            states=[]
            for n in (0,1):
                rows=re.findall(r'LDN state=(\d+) node=(-?\d+) nodes=(\d+) session=(\w+)',session.text(n));states.append(rows[-1] if rows else None)
            roots=re.findall(r'A7_NET_ROOT .*? state=(\d+)',session.text(1))
            return (states[0] and states[1] and states[0][:3]==('3','0','2') and states[1][:3]==('5','1','2') and states[0][3]==states[1][3] and roots and roots[-1]=='34')
        session.until(joined);(session.out/'go').touch()
        session.until(lambda:all('A7_MATCH configured ' in session.text(n) for n in (0,1)))
        (session.out/'go.fix').touch();session.until(lambda:'A7_MATCH native_fix_complete ' in session.text(0))
        (session.out/'load-slots/active').touch();mark('loading');(session.out/'go.command').touch()
        session.until(lambda:all('PROBE main+0x3db55d0' in session.text(n) for n in (0,1)))
    def tick(session,*a,**kw):
        answer=original_tick(session,*a,**kw)
        for n,_,_ in session.hosts:
            text=session.text(n)
            if 'A7_MATCH command=' in text and 'PROBE main+0x14f44cc' in text:raise RuntimeError(f'player-{n}: native start error')
        if events[-1]['phase']=='boot' and 'create player=0 ' in (session.out/'air.log').read_text():mark('room')
        return answer
    def prepare(*a,**kw):mark('loading');return original_prepare(*a,**kw)
    def factory(*a,**kw):
        env=NativeParallelEnv(*a,**kw,patched=args.patched);captured.append(env);return env
    def reset(env,*a,**kw):
        result=original_reset(env,*a,**kw);mark('controlled');return result
    def settle(*a,**kw):
        mark('settlement');yield from original_settlement(*a,**kw)
    def close(env):
        if env.session:mark('cleanup')
        return original_close(env)
    print(out,flush=True);mark('boot')
    try:
        with patch('subprocess.Popen',side_effect=popen),patch.object(Session,'host_options',options),\
             patch.object(Session,'start',start),patch.object(Session,'tick',tick),\
             patch.object(session_module,'prepare_match',prepare),patch.object(NativeParallelEnv,'reset',reset),\
             patch.object(NativeParallelEnv,'close',close),patch.object(runner,'NativeParallelEnv',side_effect=factory),\
             patch.object(runner,'settlement_steps',settle):
            report['match']=runner.run_match(dict(out=str(out/'match'),round=0,stage=args.stage,roles=[0,1],
                policy_paths=[str(s.root) for s in specs],timeout=args.timeout))
        mark('finished')
        report['phase_wall_seconds']={a['phase']:b['wall']-a['wall'] for a,b in zip(events,events[1:])}
        report['wall_seconds']=events[-1]['wall']-events[0]['wall']
        match=report['match'];report['passed']=match['passed'] and not match['errors']
        if report['passed']:
            frames=match['frames']-match['settlement_frames']
            report['controlled_frames']=frames
            report['controlled_fps']=frames/report['phase_wall_seconds']['controlled']
            report['games_per_hour_single_room']=3600/report['wall_seconds']
        samples=[row for session in sessions for row in session.monitor.rows]
        gpu={}
        for a,b in zip(events,events[1:]):
            values=[r['gpu']['Device Utilization %'] for r in samples if a['wall']<=r['time']<b['wall'] and 'Device Utilization %' in r['gpu']]
            gpu[a['phase']]=dict(samples=len(values),mean=statistics.mean(values) if values else None,
                median=statistics.median(values) if values else None,maximum=max(values) if values else None)
        report['gpu_utilization_percent_by_phase']=gpu
        report['sessions']=[str(s.out) for s in sessions]
    except BaseException as error:report['errors'].append(repr(error))
    finally:
        for env in captured:
            try:original_close(env)
            except BaseException as error:report['errors'].append('cleanup: '+repr(error))
    if report['errors']:report['passed']=False
    save();print(json.dumps(report,indent=2),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',type=Path,default=ROOT/'work/a7/dmhost-release-v28')
    p.add_argument('--patched',type=Path,default=ROOT/'work/a7/patched-setting-v12')
    p.add_argument('--stage',type=int,choices=(2,),default=2,help='this checkpoint supports District00 only')
    p.add_argument('--timeout',type=float,default=3600)
    raise SystemExit(main(p.parse_args()))
