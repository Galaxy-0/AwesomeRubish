#!/usr/bin/env python3
"""Native public minimap readback alternative to unmapped ink atlases; diagnostic."""
import argparse
import datetime
import importlib
import json
from pathlib import Path
import sys
import traceback
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rl import NativeParallelEnv
from rl.loadout import uniform_loadout
from probe_a1_time import neutral,sample_hosts
from probe_a3_visibility import ScreenshotSession


def main(args):
    importlib.import_module('rl.env').Session=ScreenshotSession
    out=ROOT/'work/tests'/datetime.datetime.now().strftime('a3-minimap-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(probe_completed=False,full_a3_passed=False,errors=[],samples=[],artifacts=str(out))
    env=NativeParallelEnv(players=2,weapons=[8000]*2,loadouts=[uniform_loadout() for _ in range(2)],state_dump=True,
                          reward_fn=None,timeout=args.timeout,step_timeout=30)
    log=(out/'steps.jsonl').open('w');number=0
    def actions():return {a:neutral() for a in env.possible_agents}
    def record(obs,infos,label):
        nonlocal number
        number+=1;log.write(json.dumps(dict(step=number,label=label,infos=infos))+'\n');log.flush()
        env.observations=obs;env.process_infos=infos
    def step(a,label,frames=30):
        env.frame_skip=frames;obs,_,_,truncated,infos=env.step(a)
        if any(truncated.values()):raise TimeoutError('minimap diagnostic deadline')
        record(obs,infos,label)
    def pulse():
        env.session.clock.resume()
        env.clients['player_0'].send_referee_map_pulse()
        env.clients['player_1'].send_step(neutral(),1)
        obs={};infos={}
        for p,c in env.clients.items():obs[p],infos[p]=c.receive()
        env.session.clock.pause();env._decorate(obs,infos);env.session.tick(sleep=False);record(obs,infos,'native-X')
    def capture(label):
        step(actions(),label+'-align',30-env.process_infos['player_0']['frame']%30)
        Image.fromarray(env.observations['player_0']['pixels']).save(out/(label+'.png'))
        frame=env.process_infos['player_0']['frame']
        result['samples'].append(dict(label=label,infos=env.process_infos,
            native_image=str(env.session.out/f'player-0/screenshots/native-{frame}.png')))
    try:
        env.reset();result['session']=str(env.session.out)
        for _ in range(15):step(actions(),'warmup')
        pulse();step(actions(),'map-open-before',60);capture('before-paint-map')
        pulse();step(actions(),'close-map',30)
        a=actions();a['player_0']['sticks'][1]=1;step(a,'leave-spawn',90);step(actions(),'land',60)
        a=actions();a['player_0']['gyro'][0]=.08;step(a,'look-down',45)
        a=actions();a['player_0']['buttons'][0]=1;step(a,'paint-known-world',180)
        pulse();step(actions(),'map-open-after',60);capture('after-paint-map')
        pulse();step(actions(),'close-map-after',30)
        result['probe_completed']=True
    except BaseException as e:
        result['errors'].append(repr(e));result['traceback']=traceback.format_exc()
        if env.session:sample_hosts(env.session,out)
    finally:
        try:env.close()
        except BaseException as e:result['errors'].append('cleanup: '+repr(e))
        log.close()
    result['probe_completed']=result['probe_completed'] and not result['errors']
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result['probe_completed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--timeout',type=float,default=1800)
    raise SystemExit(main(p.parse_args()))
