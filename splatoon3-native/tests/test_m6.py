#!/usr/bin/env python3
"""M6 pixel/control layer: real random match, action effect, exact steps, reset."""
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
from rl.session import FAILURE


def neutral():return dict(sticks=np.zeros(4,np.float32),gyro=np.zeros(3,np.float32),buttons=np.zeros(6,np.int8))


def difference(a,b):
    return float(np.abs(a[12:58,4:124].astype(float)-b[12:58,4:124].astype(float)).mean())


def main(args):
    out=ROOT/'work/tests'/datetime.datetime.now().strftime(f'm6-check-{args.players}p-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(milestone='M6-A' if args.players==2 else 'M6-C',passed=False,errors=[],episodes=[],internal_state='not_implemented',artifacts=str(out))
    env=NativeParallelEnv(players=args.players,frame_skip=args.frame_skip,mode=args.mode,stage_id=args.stage_id,
                         weapons=args.weapons or [0]*args.players,timeout=args.timeout,patched=args.patched)
    rng=np.random.default_rng(args.seed);last_print=time.monotonic();step_number=0
    log=(out/'steps.jsonl').open('w')
    def step(actions):
        nonlocal step_number,last_print
        observations,rewards,terminated,truncated,infos=env.step(actions);step_number+=1
        if any(truncated.values()):raise AssertionError('unexpected truncated match')
        for agent,observation in observations.items():
            if not env.observation_space(agent).contains(observation):raise AssertionError(f'{agent}: out-of-space observation')
        log.write(json.dumps(dict(step=step_number,episode=env.episode,infos=infos))+'\n');log.flush()
        if time.monotonic()-last_print>30:
            print(f'M6 episode={env.episode} step={step_number} phase='+str({a:i['phase'] for a,i in infos.items()}),flush=True);last_print=time.monotonic()
        return observations,all(terminated.values()),infos
    try:
        previous_pids=set()
        for episode in range(2):
            observations,infos=env.reset(seed=args.seed+episode)
            pids={p.pid for _,p,_ in env.session.hosts}
            if pids & previous_pids:raise AssertionError('reset reused an old live process')
            previous_pids=pids
            record=dict(session=str(env.session.out),reset_ingame=True,pids=sorted(pids));result['episodes'].append(record)
            actions={a:neutral() for a in env.agents}
            if episode==1:
                for _ in range(10):observations,done,infos=step(actions)
                record['reset_steps']=10;record['still_ingame']=all(i['phase']==1 for i in infos.values())
                if not record['still_ingame']:raise AssertionError('reset did not start a second running match')
                break
            # Deliberately vary policy wall time and k: completed frame deltas
            # still have to be exactly k for every process, checked by Client.
            for k in (1,7,31):
                env.frame_skip=k;time.sleep(.2);observations,_,_=step(actions)
            env.frame_skip=args.frame_skip
            for _ in range(max(1,360//args.frame_skip)):observations,_,_=step(actions)
            if any(float(o['pixels'].var())<25 for o in observations.values()):raise AssertionError('black/flat in-game pixel observation')
            for a,o in observations.items():Image.fromarray(o['pixels']).save(out/f'{a}-initial.png')
            idle=[];moving=[];last=observations['player_0']['pixels']
            for _ in range(6):
                observations,_,_=step(actions);current=observations['player_0']['pixels'];idle.append(difference(last,current));last=current
            move=neutral();move['sticks']=np.array([0,1,.8,0],np.float32)
            actions['player_0']=move
            for _ in range(6):
                observations,_,_=step(actions);current=observations['player_0']['pixels'];moving.append(difference(last,current));last=current
            Image.fromarray(last).save(out/'player_0-moving.png')
            threshold=max(3.0,float(np.mean(idle))*1.5)
            record['action_effect']=dict(idle_mad=idle,moving_mad=moving,threshold=threshold,passed=float(np.mean(moving))>threshold)
            if not record['action_effect']['passed']:raise AssertionError('moving/camera image change not greater than idle baseline')
            done=False
            while not done:
                actions={}
                for agent in env.agents:
                    buttons=(rng.random(6)<np.array([.55,.20,.05,.05,.12,0])).astype(np.int8)
                    actions[agent]=dict(sticks=rng.uniform(-1,1,4).astype(np.float32),gyro=np.zeros(3,np.float32),buttons=buttons)
                observations,done,infos=step(actions)
            record['random_match_complete']=True;record['terminal_infos']=infos
            for n,_,_ in env.session.hosts:
                text=env.session.text(n)
                if any(f'PROBE main+0x{a}' not in text for a in ('3db55d0','3dcc710','3dd9370')):raise AssertionError('native result sequence missing')
                if 'screen_submits=0 composite=0' not in text or FAILURE.search(text):raise AssertionError('headless/runtime evidence failed')
        result['pixel_control_layer_passed']=True
    except BaseException as error:
        result['errors'].append(f'{type(error).__name__}: {error}')
        (out/'exception.txt').write_text(traceback.format_exc())
    finally:
        try:env.close()
        except BaseException as error:result['errors'].append(f'cleanup: {type(error).__name__}: {error}')
        log.close()
    result['passed']=bool(result.get('pixel_control_layer_passed')) and not result['errors']
    result['sessions']=list(map(str,env.artifacts));result['steps']=step_number
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--players',type=int,choices=(2,8),default=2)
    parser.add_argument('--frame-skip',type=int,default=15)
    parser.add_argument('--mode',type=int,choices=range(5),default=0)
    parser.add_argument('--stage-id',type=int,default=1)
    parser.add_argument('--weapons',type=lambda s:list(map(int,s.split(','))))
    parser.add_argument('--seed',type=int,default=137)
    parser.add_argument('--timeout',type=float,default=2400)
    parser.add_argument('--patched',type=Path)
    raise SystemExit(main(parser.parse_args()))
