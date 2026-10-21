"""Same calibrated surrogate; skip rays whose hit/emission mask is already false."""
import numpy as np,math
from dataclasses import dataclass
from calibrated_model import Config as BaseConfig,hook_path,wrap,gun_flight_frames
@dataclass(frozen=True)
class Config(BaseConfig):
    light_spawn_after_input:int=11 # seven native fixed-angle shots, input->birth11f
    style:str="full-light"
    light_period:int=30
    gun_spawn_after_input:int=2 # six native isolated gun births input+2f


def duel_batch(path,arrival,enemy_positions,headings,forms,clear,*,cfg=Config(),samples=16,behavior='stand',seed=0,move_clear=None,ballistic_clear=None,blade_clear=None):
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
    schedule={full_fire:True,light_fire:False}if cfg.style=='full-light'else{arrival+cfg.charge+cfg.light_spawn_after_input+j*cfg.light_period:False for j in range(3)}
    previous_enemy=enemy.copy()
    for t,p in enumerate(path):
        if move_clear is not None:enemy=np.repeat(move_clear['positions'][t],samples,axis=0)
        velocity=enemy-previous_enemy;previous_enemy=enemy.copy()
        los=np.repeat((move_clear['clear'][t]if move_clear is not None else clear[t]),samples)
        if move_clear is not None and 'clear_human'in move_clear:
            human=np.repeat(move_clear['clear_human'][t],samples);los=np.where((first>=0)&(t-first>=reaction),human,los)
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
            if cfg.defender_pitch_sigma_degrees>0:
                vertical=rng.normal(0,math.radians(cfg.defender_pitch_sigma_degrees),k);hit&=np.abs(vertical)<=np.arctan2(1.1,np.maximum(distance,.01))
            if ballistic_clear is not None:
                candidate=np.flatnonzero(hit)
                if len(candidate):hit[candidate]&=ballistic_clear(enemy[candidate]+[0,1.1,0],np.broadcast_to(p+[0,.85,0],(len(candidate),3)))
            lag=gun_flight_frames(distance)+cfg.receive_delay+cfg.gun_spawn_after_input
            damage=np.clip(cfg.gun_max-(distance-cfg.gun_full_range)*cfg.gun_falloff_hp_per_unit,cfg.gun_min,cfg.gun_max)
            scale=cfg.armor_damage_scale if t<arrival else 1.
            ix=np.flatnonzero(hit);np.add.at(pending,(np.minimum(t+lag[ix],len(pending)-1),ix),damage[ix]*scale);clock[shoot]=cfg.gun_interval
        atk_hp-=pending[t];atk_ko[(atk_ko<0)&(atk_hp<=0)]=t
        if t in schedule:
            full=schedule[t];speed=cfg.full_speed if full else cfg.light_speed;limit=cfg.full_range if full else cfg.light_range
            lag=np.ceil(distance/speed).astype(int)+cfg.receive_delay
            aim=enemy+velocity*lag[:,None]
            origin=np.broadcast_to(p+[0,2.2 if full else 1.,0],(k,3)).copy()
            shot_los=los.copy()
            if blade_clear is not None or ballistic_clear is not None:
                candidate=np.flatnonzero((atk_hp>0)&(distance<=limit));shot_los=np.zeros(k,bool)
                if len(candidate):
                    shot_los[candidate]=(blade_clear(origin[candidate],aim[candidate]+[0,1.1,0],full)if blade_clear is not None else ballistic_clear(origin[candidate],aim[candidate]+[0,1.1,0]))
            emitted=(atk_hp>0)&(distance<=limit)&shot_los
            swings.append(dict(full=full,due=t+lag,aim=aim,emitted=emitted,origin=origin))
        for swing in swings:
            due=swing['emitted']&(swing['due']==t)&(def_hp>0)
            # Linear prediction can miss corners; capsule/blade widths bound
            # the positional error. This is an approximation, not native shape.
            error=enemy-swing['aim'];horizontal=np.linalg.norm(error[:,[0,2]],axis=1)
            hit=due&(horizontal<=(.65 if swing['full']else 1.6))&(np.abs(error[:,1])<=(2.2 if swing['full']else .9))
            reliability=cfg.full_reliability if swing['full']else cfg.light_reliability
            if reliability<1:hit&=rng.random(k)<reliability
            if swing['full']:def_hp[hit]-=70;damage70|=hit
            else:def_hp[hit]-=35;damage35|=hit
            def_ko[(def_ko<0)&(def_hp<=0)]=t
    kill=def_ko>=0;trade=kill&(atk_ko>=0);survive=kill&((atk_ko<0)|(atk_ko>def_ko))
    shape=(n,samples)
    return dict(kills=kill.reshape(shape),ties=trade.reshape(shape),surviving_kills=survive.reshape(shape),first_seen=first.reshape(shape),atk_ko=atk_ko.reshape(shape),def_ko=def_ko.reshape(shape),hit70=damage70.reshape(shape),hit35=damage35.reshape(shape))
