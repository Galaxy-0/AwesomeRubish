"""Finite two-defender resource simulation, conditional on declared assumptions.

Both .52 defenders share one attacker's HP/gauge. Enemy HP persists between
combos. This is NOT independent single-duel probability multiplication. Native
calibration covers one defender; joint crossfire/target switching remain model
assumptions. No armor benefit; return damage is explicitly bracketed.
"""
import math
import numpy as np
from model_v2 import Config,hook_path,wrap,gun_flight_frames
from budget import Gauge

def simulate(path,events,enemy_motion,headings,forms,los_human,los_squid,ballistic,*,style='full-light',seed=0,cfg=Config(),return_vulnerable=True):
    rng=np.random.default_rng(seed);horizon,n,ne,_=enemy_motion.shape
    if ne!=2 or style not in ('full-light','triple-light'):raise ValueError('finite two enemy fixture')
    gauge=Gauge();resource=np.full(n,.96);atk_hp=np.full(n,100.);hp=np.full((n,ne),100.);yaw=headings.copy();first=np.full((n,ne),-1,int);reaction=rng.integers(cfg.reaction_min,cfg.reaction_max+1,(n,ne));omega=cfg.turn_radians_per_frame*rng.uniform(.8,1.2,(n,ne));clock=np.zeros((n,ne),int)
    pending=np.zeros((horizon+80,n),np.float32);swords=[];return_start=np.full(n,-1,int);atk_down=np.full(n,-1,int);killed=np.zeros((n,ne),bool);target=np.full(n,-1,int);combostart=next(e['frame']for e in events if e['event']=='开始蓄力');hooks={e['frame']for e in events if e['event']=='出钩'};attacks=fulls=lights=0
    # Paths continue to stay/fall only until resource ends. Return geometry is
    # an observed-duration parabola approximation, no collision/invuln claim.
    positions=np.empty((n,3));return_origins=np.empty((n,3));previous=enemy_motion[0].copy()
    for t in range(horizon):
        p=path[min(t,len(path)-1)];enemy=enemy_motion[t];velocity=enemy-previous;previous=enemy.copy()
        active=return_start<0;resource[active]-=gauge.drain
        if t in hooks:resource[active]-=gauge.hook_ink/gauge.capacity
        began=(resource<=0)&active&(atk_hp>0);return_start[began]=t;return_origins[began]=p
        returning=(return_start>=0)&(t-return_start<100)&(atk_hp>0);positions[:]=p
        if returning.any():
            u=np.clip((t-return_start[returning])/100,0,1);positions[returning]=return_origins[returning]*(1-u[:,None])+path[0]*u[:,None];positions[returning,1]+=32*4*u*(1-u)
        returned=(return_start>=0)&~returning;positions[returned]=path[0]
        delta=positions[:,None,:]-enemy;distance=np.linalg.norm(delta,axis=2);bearing=np.arctan2(delta[:,:,0],delta[:,:,2]);los=np.where(forms,los_squid[t],los_human[t])
        emerged=(first>=0)&(t-first>=reaction);los=np.where(emerged,los_human[t],los)
        # Precomputed rays cover pre-return pose. Return vulnerability brackets
        # damage conservatively with clear LOS; survivor score has wider limits.
        los[returning]=True
        visible=los&(np.abs(wrap(bearing-yaw))<=cfg.half_fov);first[(first<0)&visible]=t
        ready=visible&(first>=0)&(t-first>=reaction)&(hp>0)&(atk_hp[:,None]>0)
        ramp=np.clip((t-first-reaction+1)/cfg.turn_ramp_frames,0,1);yaw+=np.where(ready,np.clip(wrap(bearing-yaw),-omega*ramp,omega*ramp),0);clock-=1
        shoot=ready&(np.abs(wrap(bearing-yaw))<math.radians(8))&(clock<=0)&(distance<=cfg.gun_max_range)
        if shoot.any():
            error=rng.normal(0,math.radians(cfg.aim_sigma_degrees),(n,ne))+rng.uniform(-math.radians(cfg.native_spread_degrees),math.radians(cfg.native_spread_degrees),(n,ne))
            hit=shoot&(np.abs(wrap(bearing-yaw)+error)<=np.arctan2(.635,np.maximum(distance,.01)))
            lag=gun_flight_frames(distance)+cfg.receive_delay;damage=np.clip(cfg.gun_max-(distance-cfg.gun_full_range)*cfg.gun_falloff_hp_per_unit,cfg.gun_min,cfg.gun_max)
            rows,cols=np.where(hit);np.add.at(pending,(np.minimum(t+lag[rows,cols],len(pending)-1),rows),damage[rows,cols]);clock[shoot]=cfg.gun_interval
        damage=pending[t].copy()
        if not return_vulnerable:damage[returning]=0
        atk_hp-=damage;atk_down[(atk_down<0)&(atk_hp<=0)]=t
        relative=t-combostart;offset=relative%110
        if relative>=0 and offset==0:
            # One known-target acquisition per fixed110f program. Fully aware
            # attacker is a model assumption, not a sandbox policy capability.
            candidate=(hp>0)&los&(distance<=cfg.full_range if style=='full-light'else distance<=cfg.light_range)
            score=np.where(candidate,distance,np.inf);target=np.argmin(score,axis=1);target[~candidate.any(axis=1)]=-1
        if relative>=0:
            full=style=='full-light'and offset==cfg.charge+cfg.full_spawn_after_release
            light=(style=='full-light'and offset==cfg.light_input_after_charge+cfg.light_spawn_after_input)or(style=='triple-light'and offset in(9,39,69))
            # Reserve charge cost at input, suppress emission if gauge expired.
            if style=='full-light'and offset==0:
                ix=(target>=0)&(atk_hp>0)&(return_start<0);resource[ix]-=gauge.full_ink/gauge.capacity
            if light or full:
                index=np.maximum(target,0);alive_target=hp[np.arange(n),index]>0;ix=(target>=0)&alive_target&(atk_hp>0)&(return_start<0)&(resource>0)
                if light:resource[ix]-=gauge.light_ink/gauge.capacity;ix&=resource>0
                if ix.any():
                    targetpos=enemy[np.arange(n),index];dist=distance[np.arange(n),index];speed=cfg.full_speed if full else cfg.light_speed;limit=cfg.full_range if full else cfg.light_range;lag=np.ceil(dist/speed).astype(int)+cfg.receive_delay;aim=targetpos+velocity[np.arange(n),index]*lag[:,None]
                    origin=positions+[0,2.2 if full else 1.,0];clear=ballistic(origin,aim+[0,.85,0]);emit=ix&(dist<=limit)&clear
                    swords.append(dict(due=t+lag,target=index.copy(),aim=aim,emit=emit,full=full));attacks+=int(emit.sum());fulls+=int(emit.sum())if full else 0;lights+=int(emit.sum())if light else 0
        for s in swords:
            ix=np.flatnonzero(s['emit']&(s['due']==t))
            if not len(ix):continue
            cols=s['target'][ix];error=enemy[ix,cols]-s['aim'][ix];hit=(np.linalg.norm(error[:,[0,2]],axis=1)<=(.65 if s['full']else 1.6))&(np.abs(error[:,1])<=(2.2 if s['full']else .9));rows=ix[hit];cols=cols[hit];hp[rows,cols]-=70 if s['full']else 35;killed|=hp<=0
    counts=killed.sum(axis=1)
    return dict(kills=counts,attacker_alive=atk_hp>0,returned=return_start>=0,spent=1-np.maximum(resource,0),full_emissions=fulls,light_emissions=lights,return_rule='vulnerable_clear_los_upper_risk'if return_vulnerable else'invulnerable_during100f_return_bound',limits=['Ideal target acquisition and linear lead; conditional single-defender calibration only.','Fixed110f repeated program, no pursuit. Triple-light input period30f verified A6, joint sequencing unverified.','No native two-enemy validation or armor benefit. Return LOS/trajectory brackets, not native authority.'])
