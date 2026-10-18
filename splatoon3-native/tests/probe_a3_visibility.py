#!/usr/bin/env python3
"""Native geometric-visibility screenshot scenarios; not full A3 acceptance."""
import argparse
import datetime
import importlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import traceback
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rl import NativeParallelEnv
from rl.session import Session
from rl.loadout import uniform_loadout
from arena.native_referee import NativeRefereeAdapter
from arena.geometry import CollisionMesh,GeometricVision
from arena.visibility import PolicyProjector
from arena.policy import encode_policy
from a3_navigation import SetupGrid,movement
from probe_a1_time import neutral,sample_hosts


class ScreenshotSession(Session):
    def host_options(self,player):
        result=super().host_options(player)
        result['DM_PROBE']=('main:3db55d0,main:3dcc710,main:3dd9370,main:3571e24@x21+e8,'
                            'main:27f7f9c@x0+20,main:27f7fa0@x0+58')
        if player==0:
            out=self.out/'player-0/screenshots';out.mkdir(exist_ok=True)
            result['DM_NVN_SHOT']=','.join(str(f) for f in range(14010,26011,30))+':'+str(out/'native-%d.png')
        return result


def main(args):
    importlib.import_module('rl.env').Session=ScreenshotSession
    out=ROOT/'work/tests'/datetime.datetime.now().strftime('a3-visibility-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(probe_completed=False,full_a3_passed=False,errors=[],cases=[],artifacts=str(out))
    mesh=CollisionMesh.load(ROOT/'work/arena/maps/Yunohana/sight.npz');grid=SetupGrid(mesh);vision=GeometricVision(mesh)
    env=NativeParallelEnv(players=2,weapons=[8000]*2,loadouts=[uniform_loadout() for _ in range(2)],state_dump=True,
                          reward_fn=None,timeout=args.timeout,step_timeout=30)
    stream=(out/'steps.jsonl').open('w');number=0;packets={};offsets={};truth=None;adapter=None;projector=None
    def actions():return {a:neutral() for a in env.possible_agents}
    def camera(n):
        log=env.session.out/f'player-{n}/host.log'
        with log.open('rb') as source:source.seek(offsets.get(n,0));data=source.read();offsets[n]=source.tell()
        raw=re.findall(rb'RL_STATE frame=\d+ sequence=\d+ data=([0-9a-f]{992})',data)
        if raw:packets[n]=bytes.fromhex(raw[-1].decode())
        return np.array(struct.unpack_from('<3f',packets[n],0x5c))
    def step(a,label,frames=12):
        nonlocal number,truth
        env.frame_skip=frames;obs,_,_,truncated,infos=env.step(a);number+=1
        if any(truncated.values()):raise TimeoutError('A3 visibility deadline')
        if any(i['phase']!=1 for i in infos.values()):raise AssertionError('match ended during scene setup')
        truth=adapter.snapshot(infos)
        stream.write(json.dumps(dict(step=number,label=label,infos=infos))+'\n');stream.flush()
        return obs,infos
    def navigate(goals,label):
        routes={n:grid.route(env.process_infos[f'player_{n}']['position'],goal) for n,goal in goals.items()};indices={n:0 for n in goals}
        for _ in range(240):
            a=actions();done=True
            for n,goal in goals.items():
                p=env.process_infos[f'player_{n}']['position'];route=routes[n];i=indices[n]
                if math.hypot(p[0]-goal[0],p[2]-goal[2])<.65 and abs(p[1]-goal[1])<.3:continue
                done=False
                while i<len(route)-1 and math.hypot(p[0]-route[i][0],p[2]-route[i][2])<.85:i+=1
                indices[n]=i;target=route[i]
                a[f'player_{n}']['sticks'][:2]=movement(p,target,camera(n))*.9
            if done:
                step(actions(),label+'-settle',60);return
            step(a,label)
        raise AssertionError('bounded setup navigation failed: '+json.dumps(dict(goals=goals,positions={p:i['position'] for p,i in env.process_infos.items()})))
    def face(n,point,label):
        for _ in range(12):
            p=env.process_infos[f'player_{n}']['position'];heading=env.process_infos[f'player_{n}']['heading']
            desired=math.atan2(point[0]-p[0],point[2]-p[2])
            if abs(math.atan2(math.sin(desired-heading),math.cos(desired-heading)))<.08:break
            a=actions();a[f'player_{n}']['sticks'][:2]=movement(p,point,camera(n))*.5
            step(a,label+'-body',12)
        step(actions(),label+'-settle',30)
        a=actions();a[f'player_{n}']['buttons'][5]=1;step(a,label+'-Y',1);step(actions(),label+'-camera-settle',45)
    def capture(label,expected,held=None):
        # Align to a scheduled native 720p capture; keep the requested state.
        frame=env.process_infos['player_0']['frame'];count=30-frame%30
        step(held or actions(),label+'-capture',count)
        witnesses=vision.witnesses(truth,'player_0');obs=projector.observe(truth,'player_0',witnesses)
        image=out/(label+'-player_0.png');Image.fromarray(env.observations['player_0']['pixels']).save(image)
        native=env.session.out/f'player-0/screenshots/native-{env.process_infos["player_0"]["frame"]}.png'
        entry=dict(label=label,expected_geometry=expected,visible=obs.enemies[0].visible,
                   witnesses=[w.__dict__ for w in witnesses],players=[p.__dict__ for p in truth.players],
                   image=str(image),native_image=str(native),host_frame=env.process_infos['player_0']['frame'])
        result['cases'].append(entry);(out/(label+'-policy.json')).write_bytes(encode_policy(obs))
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        if obs.enemies[0].visible!=expected:raise AssertionError('geometry scenario mismatch: '+label)
    try:
        _,initial=env.reset();result['session']=str(env.session.out)
        adapter=NativeRefereeAdapter(out.name,initial,dict.fromkeys(env.possible_agents,8000),dict(zip(env.possible_agents,(0,1))))
        projector=PolicyProjector(out.name)
        for _ in range(30):step(actions(),'warmup',15)
        navigate({0:(8,3,8),1:(14,3,8)},'open-setup')
        target=env.process_infos['player_1']['position'];face(0,target,'face-open');capture('open-facing',True)
        a=actions();a['player_0']['buttons'][1]=1;step(a,'observer-squid',60);capture('squid-observer-open',True,a)
        step(actions(),'observer-human',60)
        p=env.process_infos['player_0']['position'];q=env.process_infos['player_1']['position'];face(0,(2*p[0]-q[0],p[1],2*p[2]-q[2]),'face-away');capture('back-facing',False)
        face(0,env.process_infos['player_1']['position'],'face-return');capture('open-return',True)
        face(0,env.process_infos['player_1']['position'],'face-ink')
        p=env.process_infos['player_1']['position'];face(1,(p[0]+10,p[1],p[2]),'paint-away')
        a=actions();a['player_1']['gyro'][0]=.08;step(a,'look-down',45)
        a=actions();a['player_1']['buttons'][0]=1;step(a,'paint-strip',180)
        a=actions();a['player_1']['sticks'][1]=1;step(a,'enter-ink',30);step(actions(),'land-ink',30)
        a=actions();a['player_1']['buttons'][1]=1;step(a,'submerge',120);capture('submerged-still',False,a)
        a['player_1']['buttons'][4]=1;step(a,'jump-press',1);a['player_1']['buttons'][4]=0;step(a,'jump-air',8)
        # Do not align away from a short airborne interval.
        witnesses=vision.witnesses(truth,'player_0');obs=projector.observe(truth,'player_0',witnesses)
        Image.fromarray(env.observations['player_0']['pixels']).save(out/'squid-airborne-player_0.png')
        result['airborne']=dict(visible=obs.enemies[0].visible,players=[p.__dict__ for p in truth.players])
        step(a,'land',90);a['player_1']['sticks'][1]=1
        for _ in range(6):
            step(a,'swim-splash',6)
            if truth.players[1].motion_visible is True:break
        witnesses=vision.witnesses(truth,'player_0');obs=projector.observe(truth,'player_0',witnesses)
        result['splash']=dict(visible=obs.enemies[0].visible,players=[p.__dict__ for p in truth.players])
        Image.fromarray(env.observations['player_0']['pixels']).save(out/'moving-splash-player_0.png')
        if not result['airborne']['visible'] or not result['splash']['visible']:raise AssertionError('jump/splash exception not visible')
        step(actions(),'stand-after-ink',60)
        navigate({1:(-8,3,-8)},'wall-setup');face(0,env.process_infos['player_1']['position'],'face-wall');capture('wall',False)
        navigate({1:(14,3,8)},'combat-setup');face(0,env.process_infos['player_1']['position'],'face-combat')
        before=env.process_infos['player_1'];result['combat_before']=before
        for _ in range(8):
            a=actions();a['player_0']['buttons'][0]=1;step(a,'native-death-event-shot',30)
            if not env.process_infos['player_1']['alive']:break
        result['combat_after']=env.process_infos['player_1']
        result['combat_down']=bool(env.process_infos['player_1']['hud_downs'][before['self_slot']]>before['hud_downs'][before['self_slot']])
        # Scene order keeps the irreversible three-unit ledge drop last.
        for _ in range(30):
            if all(i['alive'] for i in env.process_infos.values()):break
            step(actions(),'respawn-after-combat',30)
        navigate({0:(12,3,8),1:(17,0,17)},'ledge-setup');face(0,env.process_infos['player_1']['position'],'face-ledge');capture('high-platform',False)
        result['probe_completed']=True
    except BaseException as error:
        result['errors'].append(repr(error));result['traceback']=traceback.format_exc()
        if env.session:
            for p,o in env.observations.items():Image.fromarray(o['pixels']).save(out/(p+'-failure.png'))
            sample_hosts(env.session,out)
    finally:
        try:env.close()
        except BaseException as error:result['errors'].append('cleanup: '+repr(error))
        stream.close()
    result['probe_completed']=result['probe_completed'] and not result['errors']
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result['probe_completed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--timeout',type=float,default=1800)
    raise SystemExit(main(p.parse_args()))
