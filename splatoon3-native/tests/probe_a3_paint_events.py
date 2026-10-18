#!/usr/bin/env python3
"""Native ink-target / replay-event diagnosis; never accepts A3."""
import argparse
import datetime
import importlib
import json
from pathlib import Path
import re
import sys
import traceback
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rl import NativeParallelEnv
from rl.session import Session
from rl.loadout import uniform_loadout
from probe_a1_time import neutral,sample_hosts


class CandidateSession(Session):
    def host_options(self,player):
        opts=super().host_options(player)
        opts['DM_PROBE']=('main:3db55d0,main:3dcc710,main:3dd9370,main:3571e24@x21+e8,'
                          'main:3539f6c@x0+20,main:3539f70@x0+50,'
                          'main:3539e80@x1+20,main:3539e84@x1+50')
        if player==0:
            out=self.out/'player-0/paint-targets';out.mkdir(exist_ok=True)
            opts['DM_NVN_TEXDUMP']='17000:'+str(out/'target-%d.png')
        return opts


def main(args):
    # All four probe sites are non-PC-relative prologue instructions. Refuse
    # an unexpected rewritten image rather than trap a changed instruction.
    with (ROOT/'work/build/patched_v720896/main.patched.bin').open('rb') as f:
        for off,expected in [(0x3539f6c,'ffc300d1fd7b01a9'),(0x3539e80,'fd7bbca9f70b00f9')]:
            f.seek(off)
            if f.read(8).hex()!=expected:raise RuntimeError('replay probe signature mismatch at '+hex(off))
    importlib.import_module('rl.env').Session=CandidateSession
    out=ROOT/'work/tests'/datetime.datetime.now().strftime('a3-paint-events-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(probe_completed=False,full_a3_passed=False,errors=[],samples=[],artifacts=str(out))
    env=NativeParallelEnv(players=2,weapons=[8000]*2,loadouts=[uniform_loadout() for _ in range(2)],state_dump=True,
                          reward_fn=None,timeout=args.timeout,step_timeout=30)
    log=(out/'steps.jsonl').open('w');number=0
    def actions():return {a:neutral() for a in env.possible_agents}
    def step(a,label,frames=30,snapshot=False):
        nonlocal number
        env.frame_skip=frames;obs,_,_,truncated,infos=env.step(a);number+=1
        if any(truncated.values()):raise TimeoutError('paint diagnostic deadline')
        log.write(json.dumps(dict(step=number,label=label,infos=infos))+'\n');log.flush()
        if snapshot:
            result['samples'].append(dict(label=label,infos=infos))
            for agent,o in obs.items():Image.fromarray(o['pixels']).save(out/(label+'-'+agent+'.png'))
        return infos
    try:
        env.reset();result['session']=str(env.session.out)
        for _ in range(15):step(actions(),'warmup')
        a=actions();a['player_0']['sticks'][1]=1;step(a,'leave-spawn',90);step(actions(),'land',60)
        a=actions();a['player_0']['gyro'][0]=.08;step(a,'look-down',45)
        step(actions(),'before-paint',30,True)
        a=actions();a['player_0']['buttons'][0]=1;step(a,'paint-native',180,True)
        a=actions();a['player_0']['sticks'][1]=1;step(a,'enter-ink',30)
        a=actions();a['player_0']['buttons'][1]=1;step(a,'own-ink-contact',120,True)
        while env.process_infos['player_0']['frame']<17005:step(actions(),'await-target-dump')
        result['texture_dump_reached']=True
        before=env.process_infos['player_0']['hud_downs']
        result['death_observed']=False
        for i in range(60):
            a=actions();a['player_0']['sticks'][0]=1;a['player_0']['buttons'][4]=int(i%4==0)
            info=step(a,'fall-for-event')['player_0']
            if info['hud_downs']!=before:
                result['death_observed']=True;result['down_info']=info;break
        step(actions(),'after-event',300,True)
        result['probe_completed']=True
    except BaseException as error:
        result['errors'].append(repr(error));result['traceback']=traceback.format_exc()
        if env.session:sample_hosts(env.session,out)
    finally:
        try:env.close()
        except BaseException as error:result['errors'].append('cleanup: '+repr(error))
        log.close()
    if 'session' in result:
        result['event_probe_counts']={}
        for n in range(2):
            txt=(Path(result['session'])/f'player-{n}/host.log').read_text(errors='replace')
            result['event_probe_counts'][n]={off:len(re.findall('PROBE main\\+0x'+off+' #',txt)) for off in ['3539f6c','3539f70','3539e80','3539e84']}
    result['probe_completed']=result['probe_completed'] and not result['errors']
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result['probe_completed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--timeout',type=float,default=1800)
    raise SystemExit(main(p.parse_args()))
