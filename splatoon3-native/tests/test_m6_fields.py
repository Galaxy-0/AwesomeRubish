#!/usr/bin/env python3
"""Short real two-peer field correlations; optional unmapped native survey."""
import argparse
import datetime
import json
from pathlib import Path
import sys
import time
import traceback

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rl import NativeParallelEnv


def neutral():return dict(sticks=np.zeros(4,np.float32),gyro=np.zeros(3,np.float32),buttons=np.zeros(6,np.int8))


def main(args, survey_callback=None):
    out=ROOT/'work/tests'/datetime.datetime.now().strftime('m6-fields-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(passed=False,heading_passed=False,errors=[],epochs=[],artifacts=str(out))
    env=NativeParallelEnv(players=2,frame_skip=15,state_dump=args.survey,timeout=args.timeout)
    log=(out/'steps.jsonl').open('w');step_number=0;last_print=time.monotonic()
    def step(actions,label):
        nonlocal step_number,last_print
        observations,rewards,_,truncated,infos=env.step(actions);step_number+=1
        if any(truncated.values()):raise TimeoutError('field match timeout')
        totals=result.setdefault('reward_totals',{a:0.0 for a in env.possible_agents})
        for a,value in rewards.items():
            if not np.isfinite(value):raise AssertionError('non-finite example reward')
            totals[a]+=value
        for a,o in observations.items():
            if not env.observation_space(a).contains(o):raise AssertionError(f'{a}: out-of-space observation')
        log.write(json.dumps(dict(step=step_number,label=label,rewards=rewards,infos=env.process_infos,
                                 actions={a:{k:v.tolist() for k,v in d.items()} for a,d in actions.items()}))+'\n');log.flush()
        if time.monotonic()-last_print>30:
            print(f'M6 fields step={step_number} epoch={label}',flush=True);last_print=time.monotonic()
        return observations
    try:
        observations,_=env.reset(seed=173);result['session']=str(env.session.out)
        for _ in range(30):observations=step({a:neutral() for a in env.agents},'warmup')
        if any(not o['alive_valid'] or o['alive']!=1 or not o['self_slot_valid'] for o in observations.values()):raise AssertionError('own native HUD status unavailable after warmup')
        slots={i['self_slot'] for i in env.process_infos.values()}
        if len(slots)!=len(env.possible_agents) or any(not all(o['hud_valid'][s] for s in slots) for o in observations.values()):raise AssertionError('public player HUD slots unavailable')
        result['public_hud_passed']=True
        if any(not o['time_valid'] for o in observations.values()):raise AssertionError('countdown unavailable in InGame')
        initial_times={a:float(o['remaining_time'][0]) for a,o in observations.items()}
        effects=[]
        for owner in env.possible_agents:
            # Let the previous owner's final movement/packet sample settle.
            for _ in range(6):observations=step({a:neutral() for a in env.agents},'neutral-before-'+owner)
            if any(not o['heading_valid'] for o in observations.values()):raise AssertionError('heading unavailable after warmup')
            before={a:float(o['heading'][0]) for a,o in observations.items()};samples=[]
            for _ in range(6):
                actions={a:neutral() for a in env.agents};actions[owner]['sticks']=np.array([0,1,.8,0],np.float32)
                observations=step(actions,'heading-'+owner)
                if any(not o['heading_valid'] for o in observations.values()):raise AssertionError('heading became invalid during own turn')
                samples.append({a:abs(float(np.angle(np.exp(1j*(float(o['heading'][0])-before[a]))))) for a,o in observations.items()})
            peer=next(a for a in env.possible_agents if a!=owner)
            own=max(r[owner] for r in samples);remote=max(r[peer] for r in samples)
            effect=dict(owner=owner,own_turn_radians=own,neutral_peer_turn_radians=remote,passed=own>.2 and remote<.01)
            effects.append(effect)
            if not effect['passed']:raise AssertionError(f'{owner}: heading did not follow its owning controller')
        result['heading_effects']=effects;result['heading_passed']=True
        final_times={a:float(o['remaining_time'][0]) for a,o in observations.items()}
        result['time_effect']=dict(before=initial_times,after=final_times,passed=all(0<final_times[a]<initial_times[a]-1 for a in final_times) and max(final_times.values())-min(final_times.values())<.25)
        if not result['time_effect']['passed']:raise AssertionError('countdown did not decrease consistently across peers')
        result['time_passed']=True
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        # Unnamed bytes are only development evidence, never training fields.
        if args.survey and survey_callback:
            survey_callback(env,out,result,step,observations)
        elif args.survey:
            epochs=[('look-down-0',0,'down',4),('paint-move-0',0,'paint',48),('recover-0',0,'swim',16),
                    ('special-0',0,'special',1),('after-special',0,'idle',12),('fall-left-0',0,'left',48),
                    ('recover-after-fall',0,'idle',16),('look-down-1',1,'down',4),('paint-move-1',1,'paint',48)]
            for label,player,kind,count in epochs:
                owner=f'player_{player}'
                if owner not in env.agents:break
                starts={str(n):(d/'host.log').stat().st_size for n,_,d in env.session.hosts};before=env.process_infos
                for i in range(count):
                    if owner not in env.agents:break
                    actions={a:neutral() for a in env.agents};action=actions[owner]
                    if kind=='down':action['sticks'][3]=-.7
                    if kind=='paint':
                        action['sticks'][1]=1;action['buttons'][0]=1;action['buttons'][4]=int(i%8==0)
                    if kind=='left':action['sticks'][0]=-1
                    if kind=='swim':action['buttons'][1]=1
                    if kind=='special':action['buttons'][3]=1
                    observations=step(actions,label)
                ends={str(n):(d/'host.log').stat().st_size for n,_,d in env.session.hosts}
                result['epochs'].append(dict(label=label,log_starts=starts,log_ends=ends,before=before,after=env.process_infos))
                for a,o in env.observations.items():Image.fromarray(o['pixels']).save(out/f'{label}-{a}.png')
                (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    except BaseException as error:
        result['errors'].append(repr(error));(out/'exception.txt').write_text(traceback.format_exc())
    finally:
        try:env.close()
        except BaseException as error:result['errors'].append('cleanup: '+repr(error))
        log.close()
    result['passed']=result['heading_passed'] and not result['errors'];result['steps']=step_number
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='epochs'},indent=2),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--survey',action='store_true',help='record unnamed candidate fields in ignored logs')
    parser.add_argument('--timeout',type=float,default=1800)
    raise SystemExit(main(parser.parse_args()))
