#!/usr/bin/env python3
"""A3 field diagnosis only: ZL outside ink, in own ink and while airborne."""
import argparse
import datetime
import json
from pathlib import Path
import sys
import traceback
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rl import NativeParallelEnv
from rl.loadout import uniform_loadout
from probe_a1_time import neutral,sample_hosts


def main(args):
    out=ROOT/'work/tests'/datetime.datetime.now().strftime('a3-fields-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(probe_completed=False,full_a3_passed=False,errors=[],artifacts=str(out),samples=[])
    env=NativeParallelEnv(players=2,weapons=[8000]*2,loadouts=[uniform_loadout() for _ in range(2)],
                          state_dump=True,reward_fn=None,timeout=args.timeout,step_timeout=30)
    stream=(out/'steps.jsonl').open('w');number=0
    def actions():return {a:neutral() for a in env.possible_agents}
    def step(a,label,frames=15,snapshot=False):
        nonlocal number
        env.frame_skip=frames;obs,_,_,truncated,infos=env.step(a);number+=1
        if any(truncated.values()):raise TimeoutError('A3 field deadline')
        stream.write(json.dumps(dict(step=number,label=label,infos=infos))+'\n');stream.flush()
        if snapshot:
            result['samples'].append(dict(label=label,infos=infos))
            for agent,o in obs.items():Image.fromarray(o['pixels']).save(out/f'{number:03d}-{label}-{agent}.png')
    try:
        env.reset();result['session']=str(env.session.out)
        for _ in range(30):step(actions(),'warmup')
        for owner in args.owners:
            def mark(label):return owner+'-'+label
            a=actions();a[owner]['sticks'][1]=1;step(a,mark('leave-spawn'),90);step(actions(),mark('land'),60)
            a=actions();a[owner]['gyro'][0]=.08;step(a,mark('look-down'),45);step(actions(),mark('standing-before-paint'),60,True)
            a=actions();a[owner]['buttons'][1]=1;step(a,mark('zl-before-paint'),60,True)
            step(actions(),mark('stand-again'),60,True)
            a=actions();a[owner]['buttons'][0]=1;step(a,mark('paint-floor'),180,True)
            a=actions();a[owner]['sticks'][1]=1;step(a,mark('enter-painted-strip'),30,True)
            step(actions(),mark('settle-on-painted-strip'),30,True)
            a=actions();a[owner]['buttons'][1]=1;step(a,mark('zl-after-paint'),120,True)
            a[owner]['buttons'][4]=1;step(a,mark('zl-jump-press'),1)
            a[owner]['buttons'][4]=0;step(a,mark('zl-airborne'),15,True)
            step(a,mark('zl-landing'),90,True);step(actions(),mark('stand-after-paint'),60,True)
        result['probe_completed']=True
    except BaseException as error:
        result['errors'].append(repr(error));result['traceback']=traceback.format_exc()
        if env.session:sample_hosts(env.session,out)
    finally:
        try:env.close()
        except BaseException as error:result['errors'].append('cleanup: '+repr(error))
        stream.close()
    result['probe_completed']=result['probe_completed'] and not result['errors']
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result['probe_completed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--timeout',type=float,default=1400)
    p.add_argument('--owners',nargs='+',choices=['player_0','player_1'],default=['player_0','player_1'])
    raise SystemExit(main(p.parse_args()))
