#!/usr/bin/env python3
"""Read-only return-branch experiment; stop after 31 -> 34/33 on both peers.

Runs one full fixed60 match. Post-Winners delay, calendar time, and independent
pipeline cache are explicit diagnostic variables, never success substitutes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena import runner
from arena.versions import snapshot_policy
from rl import NativeParallelEnv
from rl.native_start import NativeSession,NativeSessionPool
import re


def branch(text):
    marker=text.rfind('A7_REPEAT request=')
    if marker<0:return None
    states=[int(n) for n in re.findall(r'A7_NET_ROOT[^\n]*\bstate=(\d+)',text[marker:])]
    if 31 not in states:return None
    return next((n for n in states[states.index(31)+1:] if n in (33,34)),None)


def main(args):
    out=args.out.resolve()
    if not out.is_relative_to(ROOT/'work'):raise ValueError('raw evidence must stay under work/')
    out.mkdir(parents=True,exist_ok=False)
    pool=NativeSessionPool(args.host,args.patched);options=NativeSession.host_options
    result=dict(schema='arena.a7.return-branch.v1',completed=False,full_a7_passed=False,
        delay_native_presents=args.delay_frames,fixed_calendar_seconds=args.fixed_time,
        pipeline_cache=str(args.pipeline_cache.resolve()) if args.pipeline_cache else None,
        host_sha256=hashlib.sha256(pool.host.read_bytes()).hexdigest(),errors=[],started_wall=time.time())
    def save():(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    def host_options(session,player):
        value=options(session,player)
        # Instructions are non-PC-relative; these paths do not use x16.
        # x20 is NetRoot; dump 130..13f includes 134 and 13c before clear.
        # x19 is the upper-controller update object; record 20c..21b as raw.
        value['DM_PROBE']+=',main:38a10fc@x20+130?x22=1f,main:38a1144@x19+20c?x22=1f,main:38a1170@x20+130?x22=1f'
        if args.fixed_time is not None:value['DM_FIXED_TIME']=str(args.fixed_time)
        if args.pipeline_cache:value['DM_PIPELINE_CACHE']=str(args.pipeline_cache.resolve())
        return value
    def factory(*a,**kw):
        build=json.loads(pool.host.with_suffix('.build.json').read_text())
        kw.setdefault('pixels',build.get('render_mode')!='camera')
        return NativeParallelEnv(*a,**kw,session_factory=pool.acquire,session_releaser=pool.release)
    save()
    try:
        specs=[snapshot_policy(ROOT/'arena/policies'/name,out/name) for name in ('rush','high-ground')]
        with patch.object(runner,'NativeParallelEnv',side_effect=factory),patch.object(NativeSession,'host_options',host_options):
            match=runner.run_match(dict(out=str(out/'match'),round=0,stage=2,roles=[0,1],policy_paths=[str(s.root) for s in specs],timeout=args.timeout))
            result['match']=match;save()
            if not match['passed'] or pool.held is None:raise RuntimeError('first paired Winners required')
            session=pool.held;result['session']=str(session.out);result['released_clients_wall']=time.time()
            start={n:session.frame(n) for n in (0,1)};targets={n:f+args.delay_frames for n,f in start.items()}
            session.until(lambda:all(session.frame(n)>=target for n,target in targets.items()))
            result['window']=dict(start_frames=start,target_frames=targets,request_frames={n:session.frame(n) for n in (0,1)})
            result['request_wall']=time.time();(session.out/'go.return').touch();save()
            session.until(lambda:all(branch(session.text(n)) is not None for n in (0,1)))
            result['branches']={str(n):branch(session.text(n)) for n in (0,1)}
            result['decision_wall']=time.time();result['completed']=True
            result['returned_markers_at_stop']={str(n):'A7_REPEAT returned generation=1' in session.text(n) for n in (0,1)}
    except BaseException as error:result['errors'].append(repr(error))
    finally:
        try:pool.close()
        except BaseException as error:result['errors'].append('cleanup: '+repr(error))
        result['wall_seconds']=time.time()-result['started_wall'];save();print(json.dumps(result,indent=2),flush=True)
    return 0 if result['completed'] and not result['errors'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',type=Path,required=True);p.add_argument('--patched',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--delay-frames',type=int,choices=(0,120),default=0);p.add_argument('--fixed-time',type=int);p.add_argument('--pipeline-cache',type=Path);p.add_argument('--timeout',type=float,default=1200)
    raise SystemExit(main(p.parse_args()))
