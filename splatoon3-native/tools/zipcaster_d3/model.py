"""Seeded finite duel model; all outputs conditional on the declared priors.

Geometry is supplied by GeometricVision-compatible rays. Defender never aims
at hidden current positions. Attacker uses a linear lead from a known target
state; no claim that this idealized aiming matches a player or a strategy.
"""
from dataclasses import dataclass
import math
import numpy as np
@dataclass(frozen=True)
class Config:
    reaction_min:int=12
    reaction_max:int=25
    turn_radians_per_frame:float=math.radians(220.785)/60
    turn_ramp_frames:int=10
    aim_sigma_degrees:float=2.
    native_spread_degrees:float=6.
    hook_range:float=35.
    hook_tip_speed:float=3.36
    hook_body_speed:float=65./60
    hook_initial_speed:float=.06
    hook_acceleration:float=.1
    bind_wait:int=12
    arrival_setup:int=14
    charge:int=21
    full_spawn_after_release:int=6
    full_speed:float=.8
    light_input_after_charge:int=57
    light_spawn_after_input:int=9
    light_speed:float=2.82
    receive_delay:int=4
    duration:int=540
    gun_interval:int=9
    gun_max:float=52.
    gun_min:float=30.
    gun_full_range:float=12.9352
    gun_falloff_hp_per_unit:float=5.9119
    gun_max_range:float=15.5
    light_range:float=19.
    full_range:float=22.
    enemy_walk:float=.06
    half_fov:float=math.pi/3
    armor_damage_scale:float=1.
    seed:int=520321

def wrap(x):return (x+np.pi)%(2*np.pi)-np.pi

def gun_flight_frames(distance):
    # Measured sparse velocity/segment evolution supplies a phenomenological
    # table. Origin/age offset is uncertain; this is a calibration parameter,
    # not a recovered native integrator. Near-end player/bullet radii .35+.285.
    d=np.maximum(0,np.asarray(distance)-.635)
    ages=np.interp(d,[0,3.06,6.12,8.4,10.2,11.8,12.6,13.15,13.7,15.5],[0,1,2,3,4,8,12,16,20,35])
    return np.maximum(1,np.ceil(ages).astype(int))

def hook_path(start,anchors,landings,cfg=Config()):
    pos=np.array(start,float);path=[pos.copy()];events=[]
    for j,(anchor,landing)in enumerate(zip(anchors,landings)):
        anchor=np.array(anchor,float);landing=np.array(landing,float)
        distance=np.linalg.norm(anchor-(pos+[0,1.1,0]))
        if distance>cfg.hook_range or distance<=0:return None,[]
        events.append(dict(frame=len(path)-1,event='出钩',hook=j))
        path.extend([pos.copy()for _ in range(math.ceil(distance/cfg.hook_tip_speed)+cfg.bind_wait)])
        events.append(dict(frame=len(path)-1,event='挂住',hook=j))
        delta=landing-pos;length=np.linalg.norm(delta);travelled=0.;speed=cfg.hook_initial_speed
        while travelled<length:
            speed=min(cfg.hook_body_speed,speed+cfg.hook_acceleration);travelled=min(length,travelled+speed)
            path.append(pos+delta*(travelled/max(length,1e-9)))
        pos=landing.copy();events.append(dict(frame=len(path)-1,event='到达',hook=j))
        path.extend([pos.copy()for _ in range(6 if j<len(anchors)-1 else cfg.arrival_setup)])
    events.append(dict(frame=len(path)-1,event='开始蓄力'))
    path.extend([pos.copy()for _ in range(cfg.light_input_after_charge+cfg.light_spawn_after_input+40)])
    if len(path)>cfg.duration:return None,[]
    return np.array(path),events

def duel_batch(path,arrival,enemy_positions,headings,forms,clear,*,cfg=Config(),samples=16,behavior='stand',seed=0,move_clear=None,ballistic_clear=None):
    """Scenarios x MC. Kill includes trades; survivor probability is separate.

    Native spread is represented by a bounded uniform horizontal prior plus
    Gaussian player aim error. Their distribution is an assumption; phase1
    samples did not isolate the game's intrinsic PDF. Moving opponents use
    preplanned conservative graph routes supplied by caller, not hidden-target
    movement. They begin walking at t0; reaction gates aiming/firing only.
    """
    if behavior not in ('stand','strafe','retreat'):raise ValueError('finite behavior only')
    if behavior!='stand'and move_clear is None:raise ValueError('moving behavior requires collision-checked paths')
    rng=np.random.default_rng(cfg.seed+seed);n=len(enemy_positions);k=n*samples
    enemy=np.repeat(np.asarray(enemy_positions,float),samples,axis=0);yaw=np.repeat(np.asarray(headings,float),samples).copy()
    reaction=rng.integers(cfg.reaction_min,cfg.reaction_max+1,k);omega=cfg.turn_radians_per_frame*rng.uniform(.8,1.2,k)
    first=np.full(k,-1,int);clock=np.zeros(k,int);atk_hp=np.full(k,100.);def_hp=np.full(k,100.)
    atk_ko=np.full(k,-1,int);def_ko=np.full(k,-1,int);horizon=len(path)
    pending=np.zeros((horizon+80,k),np.float32);swings=[];damage70=np.zeros(k,bool);damage35=np.zeros(k,bool)
    full_fire=arrival+cfg.charge+cfg.full_spawn_after_release
    light_fire=arrival+cfg.light_input_after_charge+cfg.light_spawn_after_input
    previous_enemy=enemy.copy()
    for t,p in enumerate(path):
        if move_clear is not None:enemy=np.repeat(move_clear['positions'][t],samples,axis=0)
        velocity=enemy-previous_enemy;previous_enemy=enemy.copy()
        los=np.repeat((move_clear['clear'][t]if move_clear is not None else clear[t]),samples)
        delta=p-enemy;distance=np.linalg.norm(delta,axis=1);bearing=np.arctan2(delta[:,0],delta[:,2])
        visible=los&(np.abs(wrap(bearing-yaw))<=cfg.half_fov)
        first[(first<0)&visible]=t
        ready=visible&(first>=0)&(t-first>=reaction)&(def_hp>0)&(atk_hp>0)
        ramp=np.clip((t-first-reaction+1)/cfg.turn_ramp_frames,0,1)
        yaw+=np.where(ready,np.clip(wrap(bearing-yaw),-omega*ramp,omega*ramp),0.)
        clock-=1
        shoot=ready&(np.abs(wrap(bearing-yaw))<math.radians(8))&(clock<=0)&(distance<=cfg.gun_max_range)
        if shoot.any():
            err=rng.normal(0,math.radians(cfg.aim_sigma_degrees),k)+rng.uniform(-math.radians(cfg.native_spread_degrees),math.radians(cfg.native_spread_degrees),k)
            hit=shoot&(np.abs(wrap(bearing-yaw)+err)<=np.arctan2(.635,np.maximum(distance,.01)))
            lag=gun_flight_frames(distance)+cfg.receive_delay
            damage=np.clip(cfg.gun_max-(distance-cfg.gun_full_range)*cfg.gun_falloff_hp_per_unit,cfg.gun_min,cfg.gun_max)
            scale=cfg.armor_damage_scale if t<arrival else 1.
            ix=np.flatnonzero(hit);np.add.at(pending,(np.minimum(t+lag[ix],len(pending)-1),ix),damage[ix]*scale);clock[shoot]=cfg.gun_interval
        atk_hp-=pending[t];atk_ko[(atk_ko<0)&(atk_hp<=0)]=t
        if t in (full_fire,light_fire):
            full=t==full_fire;speed=cfg.full_speed if full else cfg.light_speed;limit=cfg.full_range if full else cfg.light_range
            lag=np.ceil(distance/speed).astype(int)+cfg.receive_delay
            aim=enemy+velocity*lag[:,None]
            origin=np.broadcast_to(p+[0,2.2 if full else 1.,0],(k,3)).copy()
            shot_los=los.copy()
            if ballistic_clear is not None:shot_los=ballistic_clear(origin,aim+[0,.85,0])
            emitted=(atk_hp>0)&(distance<=limit)&shot_los
            swings.append(dict(full=full,due=t+lag,aim=aim,emitted=emitted,origin=origin))
        for swing in swings:
            due=swing['emitted']&(swing['due']==t)&(def_hp>0)
            # Linear prediction can miss corners; capsule/blade widths bound
            # the positional error. This is an approximation, not native shape.
            error=enemy-swing['aim'];horizontal=np.linalg.norm(error[:,[0,2]],axis=1)
            hit=due&(horizontal<=(.65 if swing['full']else 1.6))&(np.abs(error[:,1])<=(2.2 if swing['full']else .9))
            if swing['full']:def_hp[hit]-=70;damage70|=hit
            else:def_hp[hit]-=35;damage35|=hit
            def_ko[(def_ko<0)&(def_hp<=0)]=t
    kill=def_ko>=0;trade=kill&(atk_ko>=0);survive=kill&((atk_ko<0)|(atk_ko>def_ko))
    shape=(n,samples)
    return dict(kills=kill.reshape(shape),ties=trade.reshape(shape),surviving_kills=survive.reshape(shape),first_seen=first.reshape(shape),atk_ko=atk_ko.reshape(shape),def_ko=def_ko.reshape(shape),hit70=damage70.reshape(shape),hit35=damage35.reshape(shape))

def wilson(successes,n,z=1.96):
    if n==0:return [None,None]
    p=successes/n;d=1+z*z/n;c=(p+z*z/2/n)/d;r=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0,c-r),min(1,c+r)]
