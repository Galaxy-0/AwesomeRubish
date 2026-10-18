#!/usr/bin/env python3
"""Pending A4 aiming diagnostic; not an A1 acceptance test."""
import argparse
import datetime
import json
import math
from pathlib import Path
import re
import struct
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
                controlled='same fixed60 clock with per-step policy pauses',legacy_realtime_is_60hz=False)
    env=NativeParallelEnv(players=2,weapons=[8000,8000],clock_mode='fixed60',state_dump=True,
                          frame_skip=15,timeout=args.timeout,step_timeout=30,reward_fn=None)
    log=(out/'steps.jsonl').open('w');origins={};offsets={};packets={};number=0
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
    def camera(n):
        path=env.session.out/f'player-{n}/host.log'
        with path.open('rb') as stream:
            stream.seek(offsets.get(n,0));data=stream.read();offsets[n]=stream.tell()
        matches=list(re.finditer(rb'RL_STATE frame=(\d+) sequence=\d+ data=([0-9a-f]{992})',data))
        if matches:packets[n]=bytes.fromhex(matches[-1][2].decode())
        if n not in packets:raise AssertionError('missing own camera packet for referee calibration')
        p=packets[n]
        return np.array([*struct.unpack_from('<ff',p,0x5c),struct.unpack_from('<f',p,0x64)[0]],float),struct.unpack_from('<f',p,0x68)[0]
    down=1;attacker='player_0';target_agent='player_1'
    def drive(n,target,move=True,paint=False):
        own=env.process_infos[f'player_{n}']['position'];dx=target[0]-own[0];dz=target[2]-own[2]
        distance=math.hypot(dx,dz);cam,pitch=camera(n)
        error=math.atan2(math.sin(math.atan2(dx,dz)-math.atan2(cam[0],cam[2])),math.cos(math.atan2(dx,dz)-math.atan2(cam[0],cam[2])))
        a=neutral();a['sticks'][2]=-np.clip(error*.8,-.8,.8)
        if move and distance>8:a['sticks'][1]=1
        desired=-.35 if paint else np.clip((target[1]-own[1]-.5)/max(distance,1),-.6,.6)
        a['gyro'][0]=down*np.clip((pitch-desired)*.15,-.12,.12)
        a['buttons'][0]=int(paint)
        return a
    def prepare_duel():
        # Bounded referee calibration, not a tactical arena policy. Public
        # policies will not receive merged positions/camera packet diagnostics.
        for i in range(240):
            p,q=[env.process_infos[f'player_{n}']['position'] for n in range(2)]
            distance=math.hypot(p[0]-q[0],p[2]-q[2])
            if 6<math.dist(p,q)<12 and abs(p[1]-q[1])<6:
                for _ in range(12):step(actions(),'duel-land')
                landed=[env.process_infos[f'player_{n}']['position'] for n in range(2)]
                if not 5<math.dist(*landed)<14:raise AssertionError('duel poses left the Stamper range while settling')
                result['duel_positions']=landed;return
            a=actions();target=(-12,0,35) if p[2]>45 else (20,0,10)
            a['player_0']=drive(0,target,paint=True)
            a['player_1']=drive(1,p)
            if i%12==0:
                a['player_0']['buttons'][4]=1;a['player_1']['buttons'][4]=1
            step(a,'referee-navigation')
        raise AssertionError('referee could not establish a 6..12 unit 3D Stamper duel within 60 game seconds')
    def aim_and_heal(label):
        for i in range(24):
            a=actions();p=env.process_infos[target_agent]['position']
            owner=env.possible_agents.index(attacker);target_n=env.possible_agents.index(target_agent)
            a[attacker]=drive(owner,p,move=False)
            # The target paints its own floor so enemy ink is not mistaken for
            # projectile damage and does not prevent ordinary health recovery.
            _,pitch=camera(target_n);a[target_agent]['gyro'][0]=down*np.clip((pitch+.85)*.15,-.12,.12)
            a[target_agent]['buttons'][0]=int(i%4<2)
            step(a,label)
        for _ in range(8):step(actions(),label+'-settle')
        # Single-frame correction avoids a camera-stick dead zone being
        # mistaken for an aligned shot. Calibration is outside the replay.
        for _ in range(180):
            own=env.process_infos[attacker]['position'];p=env.process_infos[target_agent]['position']
            cam,pitch=camera(owner);dx=p[0]-own[0];dz=p[2]-own[2]
            error=math.atan2(math.sin(math.atan2(dx,dz)-math.atan2(cam[0],cam[2])),math.cos(math.atan2(dx,dz)-math.atan2(cam[0],cam[2])))
            desired=np.clip((p[1]-own[1]-.5)/max(math.hypot(dx,dz),1),-.6,.6)
            if abs(error)<.04 and abs(pitch-desired)<.04:break
            a=actions();a[attacker]=drive(owner,p,move=False)
            a[attacker]['sticks'][2]=-.25*np.sign(error) if abs(error)>=.04 else 0
            step(a,label+'-fine-aim',1)
        else:raise AssertionError('referee camera could not align within 0.04 radians / pitch units')
        result.setdefault('aim',[]).append(dict(label=label,yaw_error=error,pitch_error=pitch-desired))
        for info in env.process_infos.values():
            if not info['hp_valid'] or info['hp']<.999 or not info['alive_valid'] or not info['alive']:
                raise AssertionError('duel preparation did not restore full living HP')
    try:
        _,origins=env.reset();result['session']=str(env.session.out)
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
        # Establish the native gyro sign before bounded referee navigation.
        _,before=camera(0);a=actions();a['player_0']['gyro'][0]=.08
        for _ in range(3):step(a,'gyro-calibration')
        _,after=camera(0)
        if abs(after-before)<.05:raise AssertionError('gyro calibration produced no pitch change')
        down=1 if after<before else -1
        prepare_duel();damage=[]
        attacker=max(env.possible_agents,key=lambda a:env.process_infos[a]['position'][1])
        target_agent=next(a for a in env.possible_agents if a!=attacker)
        result['attacker']=attacker;result['target']=target_agent
        for paused in (False,True):
            aim_and_heal('duel-prepare-paused' if paused else 'duel-prepare-continuous')
            fire=actions();fire[attacker]['buttons'][0]=1
            clip=script([(1,fire)]+[(k,actions()) for k in (7,7,15,15,15)],'hit-paused' if paused else 'hit-continuous',paused)
            health=[r[target_agent]['hp'] for r in clip['history'] if r[target_agent]['hp_valid']]
            loss=clip['before'][target_agent]['hp']-min(health)
            damage.append(dict(paused=paused,health=health,loss=loss,
                               hud_seconds=clip['before'][target_agent]['remaining_time']-clip['after'][target_agent]['remaining_time']))
            if not .05<loss<.999:raise AssertionError('Stamper pulse did not produce measurable partial opponent damage')
        result['damage']=damage
        if abs(damage[0]['loss']-damage[1]['loss'])>.02:raise AssertionError('policy pauses changed measured Stamper damage')
        if abs(damage[0]['hud_seconds']-damage[1]['hud_seconds'])>.04:raise AssertionError('policy pauses changed combat script duration')
        result['clock_passed']=result['movement_passed']=result['damage_passed']=True
    except BaseException as error:
        result['errors'].append(repr(error));result['traceback']=traceback.format_exc()
        if env.session:sample_hosts(env.session,out)
    finally:
        try:env.close()
        except BaseException as error:result['errors'].append('cleanup: '+repr(error))
        log.close();result['steps']=number
    result['passed']=result['full_a1_passed']=bool(result.get('damage_passed')) and not result['errors']
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--timeout',type=float,default=2400)
    raise SystemExit(main(parser.parse_args()))
