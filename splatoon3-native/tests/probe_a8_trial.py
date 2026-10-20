#!/usr/bin/env python3
"""A8 fixed-input native trial with unchanged A7 clock/seed/Winners assertions.

Per-host TSV timing is diagnostic GPU timeline span, not exclusive GPU time.
The optional two-frame attachment/binding dump is excluded from bulk timings.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
from probe_a7_trial import main as run_trial,sha,ROOT
from rl.native_start import NativeSession
from arena.runner import write_json_atomic


def main(args):
    args.route='native';entry=sha(__file__);original=NativeSession.host_options
    from rl import NativeParallelEnv
    init=NativeParallelEnv.__init__
    build=json.loads(args.host.with_suffix('.build.json').read_text())
    def initialize(env,*a,**kw):
        kw.setdefault('pixels',build.get('render_mode')!='camera')
        return init(env,*a,**kw)
    def options(session,player):
        value=original(session,player)|dict(DM_NVN_TSV=str(session.out/f'player-{player}/gpu.tsv'),DM_NVN_TSV_CALLS='0')
        if args.profile and player==0:value|=dict(DM_NVN_PASSDUMP='1800-1801',DM_NVN_PASSDUMP_ALL='1')
        if args.pass_gpu:value|=dict(DM_NVN_PASSGPU4=str(session.out/f'player-{player}/pass-gpu4.tsv'),DM_NVN_PASSGPU4_RANGES=args.pass_gpu_ranges)
        return value
    with patch.object(NativeSession,'host_options',options),patch.object(NativeParallelEnv,'__init__',initialize):code=run_trial(args)
    if sha(__file__)!=entry:raise AssertionError('A8 trial entry changed while running')
    path=args.out.resolve()/'result.json';result=json.loads(path.read_text());session=Path(result['match']['session'])
    timings={str(p.relative_to(ROOT)):sha(p) for p in session.glob('player-*/gpu.tsv')}
    if len(timings)!=2:raise AssertionError('both host timing streams required')
    pass_timings={str(p.relative_to(ROOT)):sha(p) for p in session.glob('player-*/pass-gpu4.tsv')}
    if args.pass_gpu and len(pass_timings)!=2:raise AssertionError('both Metal 4 pass timing streams required')
    write_json_atomic(args.out/'a8-run.json',dict(schema='arena.a8.trial-binding.v1',passed=code==0,
        trial_result=str(path),trial_sha256=sha(path),entry_sha256=entry,timing_sha256=timings,profile=args.profile,
        pass_gpu=args.pass_gpu,pass_gpu_sha256=pass_timings,pass_gpu_ranges=args.pass_gpu_ranges))
    return code


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('host','patched','policies','out','shared-load-slots'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--timeout',type=float,default=2400);p.add_argument('--profile',action='store_true')
    p.add_argument('--pass-gpu',action='store_true',help='Diagnostic counter sampling; not valid as uninstrumented performance evidence')
    p.add_argument('--pass-gpu-ranges',default='600-611,3000-3011,8000-8011')
    raise SystemExit(main(p.parse_args()))
