#!/usr/bin/env python3
"""A7 checkpoint: two no-menu native matches, same PIDs, changed map.

This checks process reuse and paired native Winners. It does not certify
old-route score equivalence or the full A1-A6 regression suite.
"""
import argparse
import datetime
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
from rl.native_start import NativeSessionPool,NativeSession


def main(args):
    out=Path(args.out).resolve() if args.out else ROOT/'work/a7'/datetime.datetime.now().strftime('native-pool-%Y%m%d-%H%M%S-%f')
    if not out.is_relative_to(ROOT/'work'):raise ValueError('raw evidence must stay under work/')
    pool=NativeSessionPool(args.host,args.patched)
    out.mkdir(parents=True,exist_ok=False)
    specs=[snapshot_policy(ROOT/'arena/policies'/name,out/name) for name in ('rush','high-ground')]
    report=dict(schema='arena.a7.continuous.v1',passed=False,full_a7_passed=False,
        artifacts=str(out),matches=[],errors=[],events=[],stages=[2,3],
        policy_source_sha256=[s.source_sha256 for s in specs],
        clock_mode='fixed60',pregame_controller_inputs=[],ocr_used=False,
        host_sha256=hashlib.sha256(pool.host.read_bytes()).hexdigest())
    index=0;start_native=NativeSession.start
    def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    def start(session):
        report['events'].append(dict(round=index,phase='startup',wall=time.time(),generation=session.generation));save()
        start_native(session)
        report['events'].append(dict(round=index,phase='ingame',wall=time.time(),generation=session.generation,status=session.status()));save()
    def factory(*a,**kw):
        build=json.loads(pool.host.with_suffix('.build.json').read_text())
        kw.setdefault('pixels',build.get('render_mode')!='camera')
        return NativeParallelEnv(*a,**kw,session_factory=pool.acquire,session_releaser=pool.release)
    print(out,flush=True);save()
    try:
        with patch.object(runner,'NativeParallelEnv',side_effect=factory),patch.object(NativeSession,'start',start):
            for index,stage in enumerate(report['stages']):
                match=runner.run_match(dict(out=str(out/f'match-{index}'),round=index,stage=stage,roles=[0,1],
                    policy_paths=[str(s.root) for s in specs],timeout=args.timeout))
                report['matches'].append(match);save()
                if not match['passed']:raise RuntimeError('match failed; see retained match result')
        report['passed']=(len(report['matches'])==2 and
            report['matches'][0]['host_pids']==report['matches'][1]['host_pids'] and pool.reuses==1)
    except BaseException as error:report['errors'].append(repr(error))
    finally:
        try:pool.close()
        except BaseException as error:report['errors'].append('cleanup: '+repr(error))
        report['pool']=dict(starts=pool.starts,reuses=pool.reuses)
        if report['errors']:report['passed']=False
        save();print(json.dumps(report,indent=2),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',type=Path,required=True);parser.add_argument('--patched',type=Path,required=True)
    parser.add_argument('--out',type=Path);parser.add_argument('--timeout',type=float,default=1500)
    raise SystemExit(main(parser.parse_args()))
