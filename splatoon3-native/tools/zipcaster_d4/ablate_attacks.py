"""Zero-new-room per-slash substitution on closed D4 native originals.

Pose -> p110 -> physical direction -> finite per-present trajectory. Core and
side spheres remain separate, and absence of a wall is never a damage event.
"""
import argparse, bisect, json, math, re, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import PAT,sha
from tools.zipcaster_d4.model_v2 import World
from tools.zipcaster_d4.attack_geometry import muzzle,trace_contacts

APPLY=re.compile(r'D3R_APPLY frame=(\d+) seq=\d+ context=camera_compute yaw=([^ ]+) pitch=([^ ]+)')
HP=re.compile(r'RL_DAMAGE frame=(\d+) slot=\d+ hp=(-?\d+)')
VT={'full':'5c76df0','light':'5c75510'}

def read_native(path):
    d=json.loads(path.read_text())
    assert d['freeze_before']==d['freeze_after'] and 'freeze_after'in d
    physical=[];commands=[];hp=[]
    for line in (Path(d['session'])/'player-0/host.log').open(errors='replace'):
        m=PAT.search(line)
        if m and m[4]in VT.values():
            physical.append(dict(frame=int(m[1]),kind=m[2],object=m[3],vtable=m[4],
                                 velocity=list(map(float,m[5].split(','))),position=list(map(float,m[6].split(',')))))
        m=APPLY.search(line)
        if m:commands.append((int(m[1]),float(m[2]),float(m[3])))
    for line in (Path(d['session'])/'player-1/host.log').open(errors='replace'):
        m=HP.search(line)
        if m:hp.append((int(m[1]),int(m[2])))
    steps=[json.loads(l)for l in path.with_name('steps.jsonl').open()]
    return d,physical,commands,hp,steps

def shots(d):
    if 'records'in d:
        for r in d['records']:
            yield dict(index=r['index'],style=r['style'],before=r['before'],
                       release=r['before']['player_0']['frame']+(21 if r['style']=='full'else 0),
                       pitch_delta=r.get('pitch_delta'),goals=r.get('goals'))
    else:
        for i,e in enumerate(d['events']):
            if e['event']in ('full-release','light-input'):
                yield dict(index=i,style='full'if e['event']=='full-release'else'light',
                           before=e['infos'],release=e['infos']['player_0']['frame'])

def ray_trace(origin,direction,style):
    life=26 if style=='full'else 6
    speed=.8 if style=='full'else 2.82
    age=np.arange(life+1,dtype=float)
    points=np.asarray(origin)+age[:,None]*np.asarray(direction)*speed
    if style=='full':points[:,1]-=.0027*np.maximum(age-22,0)*(np.maximum(age-22,0)+1)/2
    return points,age

def one_run(path,world,parameters):
    d,physical,commands,hp,steps=read_native(path)
    step_frames=[r['infos']['player_0']['frame']for r in steps]
    command_frames=[r[0]for r in commands]
    out=[]
    for s in shots(d):
        style=s['style'];release=s['release'];before=s['before']
        candidates=[r for r in physical if release<r['frame']<=release+18
                    and r['vtable']==VT[style] and r['kind']=='setter_input'
                    and np.linalg.norm(r['velocity'])>(1. if style=='full'else 3.)]
        if not candidates:
            out.append(dict(index=s['index'],style=style,no_birth=True));continue
        birth=candidates[0];bf=birth['frame'];origin=np.array(birth['position']);v=np.array(birth['velocity']);v/=np.linalg.norm(v)
        yaw=math.atan2(v[0],v[2]);elevation=math.asin(v[1]);actual_source=np.array(before['player_0']['position']);actual_enemy=np.array(before['player_1']['position'])
        requested_source=np.array((s.get('goals') or d['point'])['source']);requested_enemy=np.array((s.get('goals') or d['point'])['enemy'])
        collision=parameters[('vertical'if style=='full'else'horizontal')+'_projectile']['CollisionParam']
        stages=[]
        for label,source,enemy,override_origin,override_direction in [
                ('nominal_pose',requested_source,requested_enemy,None,None),
                ('actual_pose',actual_source,actual_enemy,None,None),
                ('actual_p110',actual_source,actual_enemy,origin,None),
                ('actual_direction',actual_source,actual_enemy,origin,v)]:
            o=source+[0,2.2 if style=='full'else 1.,0]
            direction=enemy+[0,1.1,0]-o;direction/=np.linalg.norm(direction)
            if override_origin is not None:o=override_origin
            if override_direction is not None:direction=override_direction
            yy=math.atan2(direction[0],direction[2]);ee=math.asin(direction[1]);points,frames=ray_trace(o,direction,style)
            enemies=np.repeat(enemy[None,:],len(points),axis=0)
            legacy_end=float(np.linalg.norm(enemy+[0,1.1,0]-o))-(.5 if style=='full'else .3)-.35
            ids,_,_=world.field.sphere(o,direction,.5 if style=='full'else .3,max(legacy_end,1e-9))
            core=trace_contacts(world.field,points,frames,enemies,yy,ee,collision,True)
            sides=trace_contacts(world.field,points,frames,enemies,yy,ee,collision)
            uncut=trace_contacts(world.field,points,frames,enemies,yy,ee,collision,side_policy='core_lifetime')
            stages.append(dict(stage=label,legacy_no_wall_credit=bool(ids[0]<0),core=core,independent_sides=sides,core_lifetime_sides=uncut))
        same=[r for r in physical if r['object']==birth['object']and bf<=r['frame']<=bf+40]
        samples={bf:birth}
        for r in same:
            if r['frame']not in samples or r['kind']=='getter':samples[r['frame']]=r
        seq=sorted(samples.values(),key=lambda r:r['frame'])
        points=np.array([r['position']for r in seq]);frames=np.array([r['frame']-bf for r in seq],float)
        enemies=[]
        for r in seq:
            i=max(0,bisect.bisect_right(step_frames,r['frame'])-1)
            enemies.append(steps[i]['infos']['player_1']['position'])
        observed=dict(stage='actual_trajectory_observed_prefix',core=trace_contacts(world.field,points,frames,enemies,yaw,elevation,collision,True),independent_sides=trace_contacts(world.field,points,frames,enemies,yaw,elevation,collision),core_lifetime_sides=trace_contacts(world.field,points,frames,enemies,yaw,elevation,collision,side_policy='core_lifetime'),observed_frames=len(seq),first_zero_velocity=next((r['frame']-bf for r in seq if np.linalg.norm(r['velocity'])<1e-6),None),observation_end=frames[-1])
        # The getter is called before collision/deletion. A hit can delete the
        # actor without any accessor at the new endpoint. Do not turn this
        # censored final update into an observed geometric miss.
        censored=bool(np.linalg.norm(seq[-1]['velocity'])>1e-6 and observed['core']['core_field_time']is None)
        observed['right_censored']=censored
        observed['miss_is_observed']=not censored
        stages.append(observed)
        if censored:
            step=np.asarray(seq[-1]['velocity'],float);step/=np.linalg.norm(step)
            step*=.8 if style=='full'else 2.82
            tail_points=np.concatenate([points,[points[-1]+step]])
            tail_frames=np.r_[frames,frames[-1]+1]
            tail_enemies=np.concatenate([enemies,[enemies[-1]]])
            stages.append(dict(stage='unobserved_final_update_hypothesis',core=trace_contacts(world.field,tail_points,tail_frames,tail_enemies,yaw,elevation,collision,True),independent_sides=trace_contacts(world.field,tail_points,tail_frames,tail_enemies,yaw,elevation,collision),core_lifetime_sides=trace_contacts(world.field,tail_points,tail_frames,tail_enemies,yaw,elevation,collision,side_policy='core_lifetime'),native_observed=False))
        offset=before['player_0']['frame']-before['player_1']['frame'];native_edges=[];last=None
        next_birth=min([r['frame']for r in physical if r['kind']=='setter_input'and r['frame']>bf+8 and np.linalg.norm(r['velocity'])>3.]or[bf+75])
        for frame,value in hp:
            frame+=offset
            if bf-6<=frame<=min(bf+70,next_birth):
                if last is not None and last-value>=190:native_edges.append(dict(frame=frame-bf,drop=(last-value)/10))
                last=value
        model_origin,_=muzzle(actual_source,yaw,elevation,style)
        command=commands[max(0,bisect.bisect_right(command_frames,bf)-1)]if commands else None
        after_target=np.array(s['before']['player_1']['position'])
        if 'records'in d:
            after_target=np.array(next(r['after']['player_1']['position']for r in d['records']if r['index']==s['index']))
        out.append(dict(index=s['index'],style=style,input_release=release,birth_frame=bf,native_pitch=command[2]if command else None,emitted_elevation=elevation,actual_source=actual_source.tolist(),actual_enemy=actual_enemy.tolist(),requested_source=requested_source.tolist(),requested_enemy=requested_enemy.tolist(),actual_p110=origin.tolist(),muzzle_prediction=model_origin.tolist(),muzzle_error=float(np.linalg.norm(model_origin-origin)),direction=v.tolist(),native_large_hp_edges=native_edges,target_displacement=(after_target-actual_enemy).tolist(),stages=stages))
    return dict(artifact=str(path.relative_to(ROOT)),sha256=sha(path),raw_sha256=d['raw_sha256'],shots=out)

def main(a):
    if a.out.exists():raise ValueError('fresh output required')
    parameters=json.loads((ROOT/'work/a6/parameters.json').read_text());worlds={};runs=[]
    paths=list(a.results or [])
    if not paths:
        paths=list((ROOT/'work/a6').glob('d3-r-d4-attack-r1-*/result.json'))+list((ROOT/'work/a6').glob('d3-r-d4-duel5-attack-r2-*/result.json'))
        batch=json.loads((ROOT/'work/d4/calibration-native-v3/batch.json').read_text())
        paths.extend(ROOT/r['artifact']for r in batch['results']if 'central_high-top'in r['point'])
    for path in sorted(set(paths)):
        path=path.resolve()
        d=json.loads(path.read_text());graph=d['point']['graph']
        if graph not in worlds:worlds[graph]=World(ROOT/graph)
        runs.append(one_run(path,worlds[graph],parameters))
    out=dict(schema='inklab.d4.attack.ablation.v1',new_native_shots=0,runs=runs,source_sha256={str(Path(__file__).relative_to(ROOT)):sha(__file__),str(Path(__file__).with_name('attack_geometry.py').relative_to(ROOT)):sha(Path(__file__).with_name('attack_geometry.py'))},limits=['Native actor world matrix/side-sphere update policy not recorded; assembly alternatives remain separate.','Finite projectile lifetime26/6 is an empirical observation envelope; per-shot actual trajectory not extended beyond its last accessor.','Damage Body reference is not proven identical to ColBullet capsule. No wall-clear-only damage credit.','HP acknowledgement has finite receipt latency; reported geometric times are not equated with HP callback frames.','Nominal/actual finite rays use the same capsule test. Native no-large-damage includes ink-only cases.'])
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2)+'\n')
    for r in runs:
        for s in r['shots']:
            if s.get('no_birth'):continue
            print(json.dumps(dict(run=Path(r['artifact']).parent.name,index=s['index'],style=s['style'],muzzle_error=s['muzzle_error'],hp=s['native_large_hp_edges'],stages=[dict(name=t['stage'],core=t['core']['hit'],sides=t['independent_sides']['hit'],uncut=t['core_lifetime_sides']['hit'],field=t['core']['core_field_time'],body=t['core']['body_time'])for t in s['stages']]),ensure_ascii=False),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--results',nargs='+',type=Path);main(p.parse_args())
