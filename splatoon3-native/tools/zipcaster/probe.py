#!/usr/bin/env python3
"""D2 coordinator-owned native Zipcaster measurement; never a tournament policy."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from a6_lab import Lab,neutral
from rl.native_start import NativeSession,validate_runtime


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def open_lab(args):
    if __import__('os').environ.get('DM_TEST_SPECIAL'):
        raise ValueError('do not export DM_TEST_SPECIAL globally; this fixture scopes it to its own hosts')
    host,patched=validate_runtime(args.host,args.patched)
    build=json.loads(host.with_suffix('.build.json').read_text())
    if not build.get('test_only') or build.get('test_feature')!='special_meter':
        raise ValueError('explicit version-bound special-meter test derivative required')
    lab=Lab('d2-'+args.suite,args.timeout,stage=args.stage,native_runtime=dict(host=str(host),patched=str(patched)))
    lab.env.config['pixels']=True  # Complete rendering for this measurement session.
    lab.result.update(schema='inklab.d2.native.v1',suite=args.suite,stage=args.stage,
        test_only=True,test_special_mode='infinite',host_build=build,
        driver_sha256=sha(__file__),raw_steps=str(lab.out/'steps.jsonl'))
    (ROOT/'work/d2'/f'{args.suite}-latest.json').write_text(json.dumps(dict(artifacts=str(lab.out),driver_pid=__import__('os').getpid()),indent=2)+'\n')
    return lab


def wait_idle(lab,label='idle'):
    seen=False
    for _ in range(150):
        info=lab.info(0)
        if not info.get('alive'):raise RuntimeError('fixture actor down during special lifecycle')
        seen|=info.get('special',1)<.98
        if seen and info['special']>=.999:
            lab.step(lab.actions(),label+'-return-settle',120);return
        lab.step(lab.actions(),label,6)
    raise RuntimeError('special lifecycle did not return within 900 presents')


def discovery(lab):
    lab.navigate({0:(0.,3.,8.),1:(18.,3.,8.)})
    for name,hold,release_observe in [('R-tap',1,150),('R-hold30',30,150),('R-hold60',60,150)]:
        lab.navigate({0:(0.,3.,8.)});lab.align(0,(0.,6.,4.),precise=True)
        before=lab.info(0);own=lab.obs(0)['own'];start=before['frame']
        action=neutral();action['buttons'][3]=1
        lab.act(0,action,name+'-RS',1)
        for _ in range(30):lab.step(lab.actions(),name+'-activate',1)
        lab.capture(name+'-activated');pre_hook=lab.info(0)
        action=neutral();action['buttons'][2]=1
        for _ in range(hold):lab.act(0,action,name+'-R-hold',1)
        held=lab.info(0);lab.capture(name+'-held')
        for _ in range(release_observe):lab.step(lab.actions(),name+'-R-released',1)
        after=lab.info(0);lab.capture(name+'-observed')
        lab.add(dict(kind=name,start_frame=start,before=before,aim=own,pre_hook=pre_hook,held=held,after=after,
            displacement_during_hold=math.dist(pre_hook['position'],held['position']),
            displacement_after_release=math.dist(held['position'],after['position']),
            hold_frames=hold,release_observe=release_observe,target=[0.,6.,4.]))
        wait_idle(lab,name+'-finish')
    lab.result['probe_completed']=True;lab.result['passed']=True


def main(args):
    lab=open_lab(args);original=NativeSession.host_options
    def options(self,player):
        # Only the measured actor gets a replenished meter, never the target.
        return original(self,player)|({'DM_TEST_SPECIAL':'infinite'} if player==0 else {})
    try:
        with patch.object(NativeSession,'host_options',options):
            lab.start();discovery(lab)
    except BaseException as error:
        lab.result['errors'].append(repr(error));lab.result['traceback']=traceback.format_exc()
    finally:lab.close()
    for n in (0,1):
        p=Path(lab.result.get('session',''))/f'player-{n}/host.log'
        if p.is_file():lab.result.setdefault('raw_sha256',{})[str(p)]=sha(p)
    lab.result.setdefault('raw_sha256',{})[str(lab.out/'steps.jsonl')]=sha(lab.out/'steps.jsonl');lab.save()
    print(lab.out,flush=True);return 0 if lab.result['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',choices=('discovery',),default='discovery')
    parser.add_argument('--stage',type=int,choices=(1,2,3),default=1)
    parser.add_argument('--host',type=Path,default=ROOT/'work/a8/dmhost-arena-special-v15')
    parser.add_argument('--patched',type=Path,default=ROOT/'work/a7/patched-seeds-v16')
    parser.add_argument('--timeout',type=float,default=3600)
    raise SystemExit(main(parser.parse_args()))
