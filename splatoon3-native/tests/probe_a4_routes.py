#!/usr/bin/env python3
"""Ten predetermined native routes per map; retain misses, require >=90%."""
import argparse
import datetime
import json
import math
from pathlib import Path
import sys
import traceback
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'arena/lib'))
from atlas import MapAtlas
from skills import Skills,aim_at,ink_at,neutral
from rl import NativeParallelEnv
from rl.loadout import uniform_loadout
from arena.referee_api import RefereeAPI
from arena.policy import encode_policy
from arena.geometry import CollisionMesh
from probe_a1_time import sample_hosts

# Fixed before running. Two fresh games keep setup/ten routes inside the native
# 180s match budget. Every goal, including the previously blocked high, stays.
REGRESSION_HIGH={1:(-5,6.0015,-3),2:(-15,9,-14),3:(11,6.0437,-7)}

def preset_goals(stage,atlas):
    goals={name:atlas.region(name) for name in ('center','west_lane','east_lane','central_high')}
    if math.dist(goals['central_high'],REGRESSION_HIGH[stage])>.15:raise ValueError('original high regression target changed')
    goals['central_high']=REGRESSION_HIGH[stage]
    return goals

GROUPS=[[("center","east_lane"),("west_lane","central_high"),("central_high","west_lane")],
        [("east_lane","center"),("center","east_lane")]]


def main(args):
    out=ROOT/'work/tests'/datetime.datetime.now().strftime(f'a4-routes-stage{args.stage}-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(passed=False,probe_completed=False,stage=args.stage,errors=[],routes=[],sessions=[],artifacts=str(out))
    atlas=MapAtlas.load(args.stage);goals=preset_goals(args.stage,atlas)
    for goal in goals.values():
        if math.dist(atlas.points[atlas.nearest(goal)],goal)>.15:raise ValueError('fixed route goal missing from new graph')
    (out/'preset-routes.json').write_text(json.dumps(dict(goals=goals,groups=GROUPS),indent=2)+'\n')
    env=NativeParallelEnv(players=2,stage_id=args.stage,weapons=[8000]*2,loadouts=[uniform_loadout() for _ in range(2)],
                          frame_skip=6,reward_fn=None,timeout=args.timeout)
    trace=(out/'steps.jsonl').open('w');api=None;origins={};steps=0;session_index=-1
    def actions():return {a:neutral() for a in env.possible_agents}
    def obs(n):return json.loads(encode_policy(api.policy_observation(f'player_{n}')))
    def position(n):return env.process_infos[f'player_{n}']['position']
    def capture(label):
        for a,o in env.observations.items():Image.fromarray(o['pixels']).save(out/f'{label}-{a}.png')
    def step(a,label,frames=6):
        nonlocal steps
        native={p:{k:np.asarray(v,dtype=np.int8 if k=='buttons' else np.float32) for k,v in value.items()} for p,value in a.items()}
        env.frame_skip=frames;_,_,_,truncated,infos=env.step(native);steps+=1
        if any(truncated.values()):raise TimeoutError('route probe session deadline')
        for agent,i in infos.items():
            origin=origins[agent];delta=i['frame']-origin['frame']
            if i['guest_time_ns']-origin['guest_time_ns']!=delta*1000000000//60:raise AssertionError('fixed60 drift')
            if i['phase']!=1:raise AssertionError('native match ended before preset routes/scenes finished')
        api.update(infos);trace.write(json.dumps(dict(step=steps,session=session_index,label=label,infos=infos))+'\n');trace.flush()
    def boot():
        nonlocal api,origins,session_index
        env.close();_,origins=env.reset();session_index+=1;result['sessions'].append(str(env.session.out))
        api=RefereeAPI(f'{out.name}-{session_index}',origins,dict.fromkeys(env.possible_agents,8000),
                       dict(zip(env.possible_agents,(0,1))),ROOT/f"work/arena/maps/{atlas.data['name']}/sight.npz",stage_id=args.stage)
        api.update(origins)
        for _ in range(30):step(actions(),'warmup',15)
    def local_move(n,goal,swim=False):
        controller=Skills(atlas);submerged=0
        for _ in range(1000):
            state=obs(n);submerged+=int(state['own'].get('submerged') is True)
            r=controller.swim_to(state,goal) if swim else controller.move_to(state,goal)
            if r.done:step(actions(),'local-settle',15);return dict(steps=_,position=position(n),submerged_samples=submerged,events=controller.events)
            if r.status=='blocked':raise AssertionError('local skill move blocked: '+json.dumps(dict(position=position(n),goal=goal,events=controller.events)))
            a=actions();a[f'player_{n}']=r.action;step(a,'local-swim' if swim else 'local-move')
        raise AssertionError('local skill move cap')
    def align(target):
        stable=0
        for _ in range(180):
            r=aim_at(obs(0),target);stable=stable+1 if r.done else 0
            if stable>=3:return _
            a=actions();a['player_0']=r.action;step(a,'local-aim',1);step(actions(),'local-aim-sample',10)
        raise AssertionError('local aim did not converge')
    try:
        for group,rounds in enumerate(GROUPS):
            boot();controllers={n:Skills(atlas) for n in (0,1)}
            for pair,names in enumerate(rounds):
                cases={}
                for n,name in enumerate(names):
                    case=dict(case=len(result['routes']),group=group,round=pair,agent=n,goal_name=name,target=goals[name],before=position(n),arrived=False,
                              start_frame=obs(n)['frame'],event_start=len(controllers[n].events))
                    result['routes'].append(case);cases[n]=case
                active={0,1}
                for _ in range(900):
                    a=actions()
                    for n in list(active):
                        case=cases[n];r=controllers[n].move_to(obs(n),case['target'])
                        if r.done or r.status=='blocked':
                            case.update(arrived=r.done,status=r.status,after=position(n),end_frame=obs(n)['frame'],events=controllers[n].events[case.pop('event_start'):])
                            active.remove(n);capture(f"route-{case['case']}-{r.status}")
                        else:a[f'player_{n}']=r.action
                    if not active:break
                    step(a,f'route-{group}-{pair}')
                for n in active:
                    case=cases[n];case.update(status='frame_cap',after=position(n),end_frame=obs(n)['frame'],events=controllers[n].events[case.pop('event_start'):])
                    capture(f"route-{case['case']}-frame-cap")
                step(actions(),'route-settle',12)
        result['routes_arrived']=sum(r['arrived'] for r in result['routes']);result['route_count']=len(result['routes'])
        result['route_rate']=result['routes_arrived']/result['route_count'];result['route_failures']=[r for r in result['routes'] if not r['arrived']]
        # A fresh ordinary game is allowed for skill setup if needed. Never
        # extend/reset an in-game timer to make the benchmark fit.
        if min(i['remaining_time'] for i in env.process_infos.values())<70:
            boot();result['skills_setup']=local_move(0,goals['center'])
        mesh=CollisionMesh.load(ROOT/f"work/arena/maps/{atlas.data['name']}/human.npz")
        p=position(0);yaw=obs(0)['own']['view_yaw'];options=[]
        for q in atlas.points:
            if abs(q[1]-p[1])>.15 or not 4<math.dist(p,q)<6:continue
            if not mesh.clear(np.array(p)+[0,.35,0],np.array(q)+[0,.35,0]):continue
            try:atlas.route(p,q,True)
            except ValueError:continue
            angle=math.atan2(q[0]-p[0],q[2]-p[2])-yaw
            options.append((abs(math.atan2(math.sin(angle),math.cos(angle))),q))
        if not options:raise AssertionError('no local flat paint/swim corridor')
        target=min(options)[1];result['skill_target']=target;result['aim_rounds']=align(target)
        before=env.process_infos['player_0']['ink']
        for _ in range(30):
            a=actions();a['player_0']=ink_at(obs(0),target).action;step(a,'local-ink')
        after=env.process_infos['player_0']['ink'];result['ink']=[before,after]
        if before-after<.03:raise AssertionError('ink_at native ink not consumed')
        result['swim']=local_move(0,target,True);capture('local-skills')
        if result['swim']['submerged_samples']<3:raise AssertionError('no native own-ink submerged feedback')
        result['skills_passed']=True;result['probe_completed']=True
        result['passed']=result['route_count']==10 and result['route_rate']>=.9
    except BaseException as error:
        result['errors'].append(repr(error));result['traceback']=traceback.format_exc()
        if env.session:capture('failure');sample_hosts(env.session,out)
    finally:
        try:env.close()
        except BaseException as error:result['passed']=False;result['errors'].append('cleanup: '+repr(error))
        trace.close();result['steps']=steps
    result['passed']=result['passed'] and not result['errors']
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',type=int,choices=(1,2,3),required=True)
    p.add_argument('--timeout',type=float,default=3000);raise SystemExit(main(p.parse_args()))
