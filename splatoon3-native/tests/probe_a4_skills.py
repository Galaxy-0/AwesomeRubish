#!/usr/bin/env python3
"""Bounded native map/skills scenes and A1 deferred damage comparison."""
import argparse
import datetime
import json
import math
from pathlib import Path
import sys
import time
import traceback
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'arena/lib'))
from rl import NativeParallelEnv
from rl.loadout import uniform_loadout
from arena.referee_api import RefereeAPI
from arena.policy import encode_policy
from arena.geometry import CollisionMesh
from atlas import MapAtlas
from skills import Skills,aim_at,ink_at,neutral
from probe_a1_time import sample_hosts


def main(args):
    out=ROOT/'work/tests'/datetime.datetime.now().strftime(f'a4-stage{args.stage}-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(probe_completed=False,full_a4_passed=False,stage=args.stage,errors=[],artifacts=str(out))
    atlas=MapAtlas.load(args.stage);mesh=CollisionMesh.load(ROOT/f"work/arena/maps/{atlas.data['name']}/human.npz")
    env=NativeParallelEnv(players=2,stage_id=args.stage,weapons=[8000]*2,loadouts=[uniform_loadout() for _ in range(2)],
                          frame_skip=6,reward_fn=None,timeout=args.timeout,step_timeout=150)
    stream=(out/'steps.jsonl').open('w');api=None;origins={};number=0
    def actions():return {a:neutral() for a in env.possible_agents}
    def record(infos,label):
        nonlocal number
        number+=1
        for a,i in infos.items():
            count=i['frame']-origins[a]['frame']
            if i['phase']!=1:raise AssertionError('match ended during A4 scenes')
            if i['guest_time_ns']-origins[a]['guest_time_ns']!=count*1000000000//60:raise AssertionError('fixed60 time drift')
        api.update(infos)
        stream.write(json.dumps(dict(step=number,label=label,infos=infos))+'\n');stream.flush()
    def step(a,label,frames=6):
        a={p:{k:np.asarray(v,dtype=np.int8 if k=='buttons' else np.float32) for k,v in action.items()} for p,action in a.items()}
        env.frame_skip=frames;_,_,_,truncated,infos=env.step(a)
        if any(truncated.values()):raise TimeoutError('A4 native deadline')
        record(infos,label);return infos
    def obs(n):return json.loads(encode_policy(api.policy_observation(f'player_{n}')))
    def position(n):return env.process_infos[f'player_{n}']['position']
    def capture(label):
        for a,o in env.observations.items():Image.fromarray(o['pixels']).save(out/f'{label}-{a}.png')
    def navigate(goals,label,swim=False):
        controllers={n:Skills(atlas) for n in goals};first={n:position(n) for n in goals};submerged=0
        for _ in range(500):
            a=actions();done=True
            for n,target in goals.items():
                r=controllers[n].swim_to(obs(n),target) if swim else controllers[n].move_to(obs(n),target)
                if r.status=='blocked':raise AssertionError(f'{label} blocked at {position(n)}, target {target}')
                if not r.done:done=False;a[f'player_{n}']=r.action
                submerged+=int(bool(obs(n)['own'].get('submerged')))
            if done:
                step(actions(),label+'-settle',30);capture(label)
                return dict(before=first,after={n:position(n) for n in goals},submerged_samples=submerged,steps=_)
            step(a,label)
        raise AssertionError(f'{label}: navigation step cap, positions {[position(n) for n in goals]}')
    def align(n,target,label):
        stable=0
        for _ in range(180):
            r=aim_at(obs(n),target)
            stable=stable+1 if r.done else 0
            if stable>=3:return dict(steps=_,own=obs(n)['own'],target=target)
            # Own view arrives in the ~10 Hz packet. A short correction then
            # neutral sampling avoids repeatedly applying stale feedback.
            a=actions();a[f'player_{n}']=r.action;step(a,label,1)
            step(actions(),label+'-sample',10)
        capture(label+'-failure');raise AssertionError('aim_at failed to converge: '+json.dumps(dict(own=obs(n)['own'],target=target)))
    def paint(n,target,label,frames=120):
        align(n,target,label+'-aim');before=env.process_infos[f'player_{n}']['ink']
        for _ in range(frames//6):
            a=actions();a[f'player_{n}']=ink_at(obs(n),target).action;step(a,label)
        after=env.process_infos[f'player_{n}']['ink'];capture(label)
        if not before-after>.03:raise AssertionError('ink_at did not spend native ink')
        return dict(before=before,after=after)
    def restore_pose(n,goal,label):
        # Referee setup uses short ordinary inputs and fresh own feedback. Keep
        # both damage trials at the same pose despite native hit knockback.
        for _ in range(60):
            own=obs(n)['own'];p=own['position'];dx=goal[0]-p[0];dz=goal[2]-p[2]
            if math.dist(p,goal)<.12:return
            yaw=own['view_yaw'];x=-dx*math.cos(yaw)+dz*math.sin(yaw);y=dx*math.sin(yaw)+dz*math.cos(yaw)
            length=max(.001,math.hypot(x,y));a=actions();a[f'player_{n}']['sticks'][:2]=[.85*x/length,.85*y/length]
            step(a,label,1);step(actions(),label+'-sample',10)
        raise AssertionError('could not restore identical damage pose')
    def clip(segments,label,paused):
        before=env.process_infos;history=[]
        if paused:
            for k,a in segments:
                time.sleep(.2);history.append(step(a,label,k))
        else:
            env.session.clock.resume()
            for k,a in segments:
                for agent,client in env.clients.items():client.send_step(a[agent],k)
            for _ in segments:
                observations={};infos={}
                for agent,client in env.clients.items():observations[agent],infos[agent]=client.receive()
                env._decorate(observations,infos);env.observations=observations;env.process_infos=infos
                record(infos,label);history.append(infos);env.session.tick(sleep=False)
            env.session.clock.pause()
        return dict(before=before,after=history[-1],history=history)
    try:
        _,origins=env.reset();result['session']=str(env.session.out)
        api=RefereeAPI(out.name,origins,dict.fromkeys(env.possible_agents,8000),dict(zip(env.possible_agents,(0,1))),
                       ROOT/f"work/arena/maps/{atlas.data['name']}/sight.npz",stage_id=args.stage)
        for _ in range(30):step(actions(),'warmup',15)
        result['native_landing']={a:i['position'] for a,i in env.process_infos.items()}
        # Select a nearby flat, open pair; all setup is referee-controlled.
        if args.stage==1:p,q=(8.,3.,8.),(11.5,3.,8.)
        else:
            c=atlas.objective();options=[]
            for i,p0 in enumerate(atlas.points):
                if math.dist(p0,c)>15 or not atlas.edges[i]:continue
                for dx,dz in ((4,0),(-4,0),(0,4),(0,-4)):
                    q0=(p0[0]+dx,p0[1],p0[2]+dz);j=atlas.nearest(q0)
                    if math.dist(q0,atlas.points[j])<.1 and mesh.clear(np.array(p0)+[0,.7,0],np.array(q0)+[0,.7,0]):
                        try:atlas.route(atlas.spawns['alpha']['ground'],p0);atlas.route(atlas.spawns['bravo']['ground'],q0)
                        except ValueError:continue
                        options.append((math.dist(p0,c),p0,q0));break
            if not options:raise AssertionError('no flat native test candidate')
            _,p,q=min(options)
        result['duel_goals']=[p,q]
        result['high_route']=navigate({0:atlas.region('central_high'),1:q},'move-to-high')
        result['flat_route']=navigate({0:p},'move-to-flat')
        target=list(q);target[1]+=.7;result['aim']=align(0,target,'aim-at-peer');capture('aim-at-peer')
        # Paint a traversable corridor pointing away from the stationary peer.
        candidates=[]
        for point in atlas.points:
            if abs(point[1]-p[1])<.1 and 4<math.dist(point,p)<6 and math.dist(point,q)>4 and mesh.clear(np.array(p)+[0,.35,0],np.array(point)+[0,.35,0]):
                try:atlas.route(p,point,True)
                except ValueError:continue
                candidates.append(point)
        if not candidates:raise AssertionError('no flat potential-swim test corridor')
        swim_goal=min(candidates,key=lambda x:math.dist(x,p));result['swim_goal']=swim_goal
        result['ink']=paint(0,swim_goal,'ink-at-corridor',180)
        result['swim']=navigate({0:swim_goal},'swim-to',True)
        if result['swim']['submerged_samples']<3:raise AssertionError('swim_to lacked actual native own-ink samples')
        result['return']=navigate({0:p},'return-to-flat')
        result['geometry_skills_passed']=True
        if args.damage:
            damage=[];poses=None
            for paused in (False,True):
                q=position(1);p=position(0)
                # Target paints nearby floor then heals; no enemy-ink damage is
                # counted as a projectile hit. Both poses remain on the flat.
                if poses is None:paint(0,(p[0]-1.5,p[1],p[2]),'attacker-own-floor',90)
                else:
                    for n,goal in enumerate(poses):restore_pose(n,goal,'restore-damage-pose')
                    p,q=position(0),position(1)
                floor=(q[0]+1.5,q[1],q[2]);paint(1,floor,'target-own-floor',90)
                step(actions(),'heal',240)
                if not all(i['hp_valid'] and i['hp']>.999 and i['alive'] for i in env.process_infos.values()):raise AssertionError('duel not fully healed')
                p,q=position(0),position(1)
                if abs(p[1]-q[1])>.1 or not 2.5<math.dist(p,q)<4.5:raise AssertionError('damage poses not flat/close')
                if poses is None:poses=[tuple(p),tuple(q)]
                elif any(math.dist(actual,expected)>.15 for actual,expected in zip((p,q),poses)):raise AssertionError('damage poses changed between trials')
                align(0,(q[0],q[1]+.7,q[2]),'damage-aim')
                fire=actions();fire['player_0']['buttons'][0]=1
                trial=clip([(1,fire)]+[(k,actions()) for k in (7,7,15,15,15)],'damage-paused' if paused else 'damage-continuous',paused)
                health=[r['player_1']['hp'] for r in trial['history'] if r['player_1']['hp_valid']]
                loss=trial['before']['player_1']['hp']-min(health)
                entry=dict(paused=paused,loss=loss,health=health,positions=[p,q],
                           hud_seconds=trial['before']['player_1']['remaining_time']-trial['after']['player_1']['remaining_time'])
                damage.append(entry);result['damage']=damage;capture('damage-'+str(paused))
                if not .05<loss<.999:raise AssertionError('aim_at pulse did not cause partial opponent damage')
            if abs(damage[0]['loss']-damage[1]['loss'])>.02 or abs(damage[0]['hud_seconds']-damage[1]['hud_seconds'])>.04:
                raise AssertionError('policy pauses changed damage or HUD time')
            result['a1_damage_passed']=True
        result['probe_completed']=True
    except BaseException as error:
        result['errors'].append(repr(error));result['traceback']=traceback.format_exc()
        if env.session:capture('failure');sample_hosts(env.session,out)
    finally:
        try:env.close()
        except BaseException as error:result['errors'].append('cleanup: '+repr(error))
        stream.close();result['steps']=number
    result['probe_completed']=result['probe_completed'] and not result['errors']
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result['probe_completed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',type=int,choices=(1,2,3),default=1)
    parser.add_argument('--damage',action='store_true');parser.add_argument('--timeout',type=float,default=2400)
    raise SystemExit(main(parser.parse_args()))
