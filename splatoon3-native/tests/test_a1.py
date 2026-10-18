#!/usr/bin/env python3
"""A1: exact native 60 Hz time and continuous/paused movement agreement."""
import argparse
import datetime
import json
from pathlib import Path
import sys
import time
import traceback

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rl import NativeParallelEnv
from probe_a1_time import neutral, sample_hosts


def main(args):
    out=ROOT/'work/tests'/datetime.datetime.now().strftime('a1-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(passed=False,full_a1_passed=False,errors=[],artifacts=str(out),
                reference='fixed60 clock with prequeued inputs and no policy pauses',
                controlled='same fixed60 clock with per-step policy pauses',legacy_realtime_is_60hz=False,
                damage_status='deferred_to_a4_aim_at',damage_passed=None)
    env=NativeParallelEnv(players=2,weapons=[8000,8000],state_dump=False,
                          frame_skip=15,timeout=args.timeout,step_timeout=30,reward_fn=None)
    log=(out/'steps.jsonl').open('w');origins={};number=0
    def actions():return {a:neutral() for a in env.possible_agents}
    def record(observations,infos,label):
        nonlocal number
        number+=1
        for agent,info in infos.items():
            origin=origins[agent];frames=info['frame']-origin['frame']
            if info['guest_time_ns']-origin['guest_time_ns']!=frames*1000000000//60:
                raise AssertionError(f'{agent}: guest time does not match exact 60 Hz frame budget')
            if info['phase']!=1:raise AssertionError('match ended before A1 measurements finished')
        log.write(json.dumps(dict(step=number,label=label,wall=time.monotonic(),infos=infos))+'\n');log.flush()
        env.observations=observations;env.process_infos=infos
        return infos
    def step(a,label,frames=15):
        env.frame_skip=frames
        observations,_,_,truncated,infos=env.step(a)
        if any(truncated.values()):raise TimeoutError('A1 deadline')
        return record(observations,infos,label)
    def script(segments,label,paused):
        before=env.process_infos;history=[]
        if paused:
            for k,a in segments:
                time.sleep(.2);history.append(step(a,label,k))
        else:
            # Every command is queued before consuming ACKs. No coordinator
            # policy pause occurs at intermediate native frame boundaries.
            env.session.clock.resume()
            for k,a in segments:
                for agent,client in env.clients.items():client.send_step(a[agent],k)
            for _ in segments:
                observations={};infos={}
                for agent,client in env.clients.items():observations[agent],infos[agent]=client.receive()
                env._decorate(observations,infos);history.append(record(observations,infos,label))
                env.session.tick(sleep=False)
            env.session.clock.pause()
        frames=sum(k for k,_ in segments)
        for agent,last in history[-1].items():
            first=before[agent]
            if not first['time_valid'] or not last['time_valid']:raise AssertionError('native timer unavailable')
            elapsed=first['remaining_time']-last['remaining_time']
            sampled=(last['time_sample_frame']-first['time_sample_frame'])/60
            if abs(elapsed-sampled)>.04:raise AssertionError('native HUD time differs from 60 Hz')
        return dict(frames=frames,before=before,after=history[-1],history=history)
    try:
        if env.config['clock_mode']!='fixed60':raise AssertionError('controlled default must be fixed60')
        _,origins=env.reset();result['session']=str(env.session.out)
        if env.session.clock_mode!='fixed60':raise AssertionError('native session default must be fixed60')
        for _ in range(30):step(actions(),'warmup')
        movement=[]
        for paused in (False,True):
            a=actions();a['player_0']['sticks'][0]=.5
            clip=script([(k,a) for k in (1,7,31,21)]+[(30,actions())],'walk-paused' if paused else 'walk-continuous',paused)
            displacement=float(np.linalg.norm(np.array(clip['after']['player_0']['position'])-clip['before']['player_0']['position']))
            peer=float(np.linalg.norm(np.array(clip['after']['player_1']['position'])-clip['before']['player_1']['position']))
            movement.append(dict(paused=paused,displacement=displacement,neutral_peer_displacement=peer,
                                 hud_seconds=clip['before']['player_0']['remaining_time']-clip['after']['player_0']['remaining_time']))
            back=actions();back['player_0']['sticks'][0]=-.5
            step(back,'return-from-walk',60)
            for _ in range(4):step(actions(),'return-settle')
        result['movement']=movement
        if min(r['displacement'] for r in movement)<.3 or max(r['neutral_peer_displacement'] for r in movement)>.05:
            raise AssertionError('walk did not follow the owning controller')
        if abs(movement[0]['displacement']-movement[1]['displacement'])>max(.15,.05*movement[0]['displacement']):
            raise AssertionError('policy pauses changed native displacement')
        if abs(movement[0]['hud_seconds']-movement[1]['hud_seconds'])>.04:raise AssertionError('policy pauses changed native script duration')
        result['clock_passed']=result['movement_passed']=True
    except BaseException as error:
        result['errors'].append(repr(error));result['traceback']=traceback.format_exc()
        if env.session:sample_hosts(env.session,out)
    finally:
        try:env.close()
        except BaseException as error:result['errors'].append('cleanup: '+repr(error))
        log.close();result['steps']=number
    result['passed']=result['full_a1_passed']=bool(result.get('clock_passed') and result.get('movement_passed')) and not result['errors']
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--timeout',type=float,default=2400)
    raise SystemExit(main(parser.parse_args()))
