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
    result=dict(milestone='M6-B-position-ink',players=args.players,passed=False,full_m6_passed=False,errors=[],episodes=[],
                internal_state='local_packet_position_ink',unavailable_fields=['last_hit_kills'],artifacts=str(out))
    env=NativeParallelEnv(players=args.players,frame_skip=args.frame_skip,mode=args.mode,stage_id=args.stage_id,
                         weapons=args.weapons or [0]*args.players,timeout=args.timeout,patched=args.patched,state_dump=args.state_dump)
    rng=np.random.default_rng(args.seed);last_print=time.monotonic();step_number=0
    log=(out/'steps.jsonl').open('w')
    def step(actions):
        nonlocal step_number,last_print
        if actions is None:
            observations,infos=env.advance_settlement();truncated={a:env.timed_out for a in env.possible_agents}
        else:observations,rewards,terminated,truncated,infos=env.step(actions)
        infos=env.process_infos;step_number+=1
        if any(truncated.values()):raise AssertionError('unexpected truncated match')
        for agent,observation in observations.items():
            if not env.observation_space(agent).contains(observation):raise AssertionError(f'{agent}: out-of-space observation')
        log.write(json.dumps(dict(step=step_number,episode=env.episode,infos=infos))+'\n');log.flush()
        if time.monotonic()-last_print>30:
            print(f'M6 episode={env.episode} step={step_number} phase='+str({a:i['phase'] for a,i in infos.items()}),flush=True);last_print=time.monotonic()
        return observations,not env.agents,infos
    try:
        previous_pids=set()
        for episode in range(2 if args.players==2 else 1):
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
            if any(not o['position_valid'] or not o['ink_valid'] for o in observations.values()):raise AssertionError('local native position is unavailable after warmup')
            if any(float(o['pixels'].var())<25 for o in observations.values()):raise AssertionError('black/flat in-game pixel observation')
            for a,o in observations.items():Image.fromarray(o['pixels']).save(out/f'{a}-initial.png')
            slots={i['self_slot'] for i in infos.values() if i['self_slot_valid']}
            if len(slots)!=args.players or any(not o['alive_valid'] or not all(o['hud_valid'][s] for s in slots) for o in observations.values()):raise AssertionError('native public HUD player state unavailable after warmup')
            if any(not o['special_valid'] for o in observations.values()):raise AssertionError('own special gauge unavailable after warmup')
            if any(not o['hp_valid'] for o in observations.values()):raise AssertionError('own HP unavailable after warmup')
            if any(not o['time_valid'] or not 0<float(o['remaining_time'][0])<=300 for o in observations.values()):raise AssertionError('invalid native in-game countdown')
            initial_times={a:float(o['remaining_time'][0]) for a,o in observations.items()}
            idle=[];moving=[];last=observations['player_0']['pixels']
            for _ in range(6):
                observations,_,_=step(actions);current=observations['player_0']['pixels'];idle.append(difference(last,current));last=current
            initial_positions={a:o['position'].copy() for a,o in observations.items()};position_samples=[]
            initial_headings={a:float(o['heading'][0]) for a,o in observations.items()};heading_samples=[]
            move=neutral();move['sticks']=np.array([0,1,.8,0],np.float32)
            actions['player_0']=move
            for _ in range(6):
                observations,_,_=step(actions);current=observations['player_0']['pixels'];moving.append(difference(last,current));last=current
                if any(not o['position_valid'] or not o['ink_valid'] for o in observations.values()):raise AssertionError('position became invalid during movement')
                if any(not o['heading_valid'] for o in observations.values()):raise AssertionError('heading unavailable during movement')
                heading_samples.append({a:abs(float(np.angle(np.exp(1j*(float(o['heading'][0])-initial_headings[a]))))) for a,o in observations.items()})
                position_samples.append({a:float(np.linalg.norm(o['position']-initial_positions[a])) for a,o in observations.items()})
            Image.fromarray(last).save(out/'player_0-moving.png')
            threshold=max(3.0,float(np.mean(idle))*1.5)
            record['action_effect']=dict(idle_mad=idle,moving_mad=moving,threshold=threshold,passed=float(np.mean(moving))>threshold)
            if not record['action_effect']['passed']:raise AssertionError('moving/camera image change not greater than idle baseline')
            own=max(row['player_0'] for row in position_samples)
            remote=max(row['player_1'] for row in position_samples)
            record['position_effect']=dict(own_displacement=own,neutral_peer_drift=remote,passed=own>.1 and remote<.05)
            if not record['position_effect']['passed']:raise AssertionError('local position did not follow the owning controller')
            own_turn=max(r['player_0'] for r in heading_samples);peer_turn=max(r['player_1'] for r in heading_samples)
            record['heading_effect']=dict(own_turn=own_turn,neutral_peer_turn=peer_turn,passed=own_turn>.2 and peer_turn<.01)
            if not record['heading_effect']['passed']:raise AssertionError('heading failed own vs peer movement correlation')
            record['time_effect']={a:dict(before=initial_times[a],after=float(o['remaining_time'][0])) for a,o in observations.items()}
            if any(not o['time_valid'] or float(o['remaining_time'][0])>=initial_times[a]-1 for a,o in observations.items()):raise AssertionError('countdown did not decrease with native frames')
            # Clean counter-survey windows. Logs retain exact byte ranges, so
            # additional native fields can be studied without guessing labels.
            record['field_epochs']=[];record['ink_effect']=[]
            for label,player,kind,count in [('idle',0,'idle',6),('fire-0',0,'fire',12),('recover-0',0,'swim',16),('fire-1',1,'fire',12),('look-0',0,'look',12)]:
                actions={a:neutral() for a in env.agents};action=actions[f'player_{player}']
                if kind=='fire':action['buttons'][0]=1
                if kind=='swim':action['buttons'][1]=1
                if kind=='look':action['sticks'][2]=.8
                starts={str(n):(d/'host.log').stat().st_size for n,_,d in env.session.hosts}
                before={a:float(o['ink'][0]) for a,o in observations.items()};samples=[]
                for _ in range(count):
                    observations,_,infos=step(actions)
                    if any(not o['ink_valid'] for o in observations.values()):raise AssertionError('ink unavailable in controlled window')
                    samples.append({a:float(o['ink'][0]) for a,o in observations.items()})
                if kind in ('fire','swim'):
                    owner=f'player_{player}';other='player_1' if player==0 else 'player_0'
                    delta=samples[-1][owner]-before[owner]
                    peer_drift=max(abs(row[other]-before[other]) for row in samples)
                    passed=(delta<-.05 if kind=='fire' else delta>.05) and (peer_drift<.02 if label!='fire-1' else True)
                    record['ink_effect'].append(dict(label=label,before=before,after=samples[-1],delta=delta,peer_drift=peer_drift,passed=passed))
                    if not passed:raise AssertionError(f'{label}: ink failed own fire/recovery correlation')
                ends={str(n):(d/'host.log').stat().st_size for n,_,d in env.session.hosts}
                record['field_epochs'].append(dict(label=label,log_starts=starts,log_ends=ends,infos=infos))
                Image.fromarray(observations[f'player_{player}']['pixels']).save(out/f'{label}.png')
            done=False
            while not done:
                actions={}
                for agent in env.agents:
                    buttons=(rng.random(6)<np.array([.55,.20,.05,.05,.12,0])).astype(np.int8)
                    actions[agent]=dict(sticks=rng.uniform(-1,1,4).astype(np.float32),gyro=np.zeros(3,np.float32),buttons=buttons)
                observations,done,infos=step(actions)
            record['individual_termination_complete']=True;record['judge_infos']=env.process_infos.copy()
            while not all(i['phase']==3 for i in env.process_infos.values()):observations,_,infos=step(None)
            if not all(i['score_valid'] for i in env.process_infos.values()):raise AssertionError('native result score unavailable')
            record['score_infos']={a:{k:i[k] for k in ('score','score_units','turf_ratio','turf_valid')} for a,i in env.process_infos.items()}
            record['random_match_complete']=True;record['terminal_infos']=env.process_infos
            for n,_,_ in env.session.hosts:
                text=env.session.text(n)
                if any(f'PROBE main+0x{a}' not in text for a in ('3db55d0','3dcc710','3dd9370')):raise AssertionError('native result sequence missing')
                if 'screen_submits=0 composite=0' not in text or FAILURE.search(text):raise AssertionError('headless/runtime evidence failed')
        result['pixel_control_layer_passed']=True
        result['position_layer_passed']=True
        result['ink_layer_passed']=True
        result['heading_layer_passed']=True
        result['time_layer_passed']=True
    except BaseException as error:
        result['errors'].append(f'{type(error).__name__}: {error}')
        (out/'exception.txt').write_text(traceback.format_exc())
    finally:
        for agent,observation in env.observations.items():
            Image.fromarray(observation['pixels']).save(out/f'{agent}-last.png')
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
    parser.add_argument('--state-dump',action='store_true',help='local development-only raw state survey in work logs')
    raise SystemExit(main(parser.parse_args()))
