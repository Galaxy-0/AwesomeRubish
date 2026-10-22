"""D4 corrected attack chain: native muzzle, volume, contact and recoil.

Finite-program conditional model, not an unconditional game proof. Components
return unresolved geometry/dynamics explicitly for query/report consumers.
"""
import math
from pathlib import Path
import json
import numpy as np
from tools.zipcaster_d4.model_v2 import (ROOT,World as BaseWorld,Config,post_path,
    schedule as old_schedule,gun_distance,damage_at_distance)
from tools.zipcaster_d4.attack_geometry import capsule_fraction
from tools.zipcaster_d4.attack_model_v4 import Shots
from tools.zipcaster_d4.attack_sequence_v2 import sequence

PROGRAMS=['full1','light2','full-light','light3','light-full','full2']


def schedule(speed,program,cfg=Config()):
    if program=='full1':return [(speed,'full')]if speed>=cfg.charge else []
    if program=='light2':return [(speed,'light'),(speed+30,'light')]
    return old_schedule(speed,program,cfg)


class World(BaseWorld):
    def __init__(self,directory,cfg=Config(),fit=None,recoil=None):
        super().__init__(directory,cfg)
        self.shots=Shots(self,fit or ROOT/'work/d4/restart-v3/attack-fit-v1.json')
        self.recoil=json.loads(Path(recoil or ROOT/'work/d4/restart-v3/recoil-fit-v2.json').read_text())['profiles']

    def visibility(self,path,enemy,heading):
        path=np.asarray(path,float);enemy=np.broadcast_to(np.asarray(enemy,float),path.shape)
        d=path-enemy;dist=np.linalg.norm(d,axis=1)
        eligible=(d[:,0]*math.sin(heading)+d[:,2]*math.cos(heading)>=-1e-8)&(dist<=self.cfg.vision_range)
        visible=np.zeros(len(path),bool);ids=np.flatnonzero(eligible)
        if len(ids):
            ends=np.concatenate([path[ids]+[0,h,0]for h in [.12,.7,1.3]])
            starts=np.concatenate([enemy[ids]+[0,1.1,0]]*3)
            visible[ids]=self.vision.clear_pairs(starts,ends).reshape(3,-1).any(axis=0)
        return visible,visible&(dist<=self.cfg.gun_range)

    def terminal(self,node,enemy,speed,program,ground=False):
        inputs=schedule(speed,program,self.cfg)
        if not inputs:return None
        position=self.graph['ground'][node]if ground else self.graph['attach'][node]
        if np.linalg.norm(position-enemy)>28:return None
        horizon=inputs[-1][0]+80
        body=np.repeat(position[None,:],horizon+1,axis=0)if ground else post_path(position,self.graph['floor'][node],horizon)
        result=sequence(self.shots,body,enemy,inputs,self.recoil,self.cfg.receive_delay)
        kill=result['kill_frame']
        if kill is None:return None
        used=[(t,k)for t,k in inputs if t<=kill]
        extra=sum(self.cfg.full_cost if k=='full'else self.cfg.light_cost for t,k in used)
        activation=self.cfg.activation_frames-self.cfg.activation_drain_grace if ground else 0
        return dict(node=node,ground=ground,speed=speed,program=program,
                    cost=(kill+activation)*self.cfg.drain+extra,kill_frame=kill,
                    damage_events=result['damage_events'],inputs=used,post=body[:kill+1],
                    enemy_path=result['target_path'][:kill+1],attack_casts=result['casts'],
                    uncertainties=result['uncertainties'],
                    program_native_verified=False,
                    scope='Native-informed volume/contact finite model; no beam. Recoil support and receiver/side ambiguity explicit. Program/ranking cohort pending.')

    def simulate(self,path,arrival,term,enemy,heading,gun_phase=0):
        cfg=self.cfg;path=np.asarray(path,float);enemy=np.asarray(enemy,float)
        target_path=np.repeat(enemy[None,:],len(path),axis=0)
        if 'enemy_path'in term:
            count=min(len(term['enemy_path']),len(path)-arrival)
            target_path[arrival:arrival+count]=term['enemy_path'][:count]
            if arrival+count<len(path):target_path[arrival+count:]=target_path[arrival+count-1]
        visible,danger=self.visibility(path,target_path,heading)
        due=[dict(e,**{k:arrival+e[k]for k in ['input','birth','due']})for e in term['damage_events']]
        hp=100.;enemy_hp=100.;atk_down=None;enemy_down=None;pending={};bullets=[];fire_at=gun_phase;shots=[];events=[]
        for t,p in enumerate(path):
            hp-=pending.get(t,0.)
            if hp<=0 and atk_down is None:atk_down=t
            for e in due:
                if e['due']==t and(atk_down is None or e['birth']<atk_down):
                    enemy_hp-=e['damage'];events.append(dict(frame=t,event='命中'+str(e['damage']),source=e.get('source')))
            if enemy_hp<=0 and enemy_down is None:enemy_down=t
            if atk_down is not None or enemy_down is not None:break
            if danger[t]and t>=fire_at:
                origin=target_path[t]+[0,1.1,0];d=p+[0,1.1,0]-origin;d/=max(np.linalg.norm(d),1e-12)
                bullets.append(dict(birth=t+cfg.gun_spawn,origin=origin,direction=d,last=origin.copy(),stopped=False));shots.append(t);fire_at=t+cfg.gun_interval
            for b in bullets:
                age=t-b['birth']
                if b['stopped']or age<1:continue
                if age>35:b['stopped']=True;continue
                end=b['origin']+b['direction']*gun_distance(age);start=b['last'];movement=end-start;length=np.linalg.norm(movement)
                body_hit=capsule_fraction(start-path[max(0,t-1)],end-p,.35+cfg.gun_radius)
                hit,_,distance=self.field.sphere(start,movement,cfg.gun_radius,max(length,1e-9))if length>1e-9 else(np.array([-1]),None,None)
                if body_hit is not None and(hit[0]<0 or length*body_hit<distance[0]-1e-6):
                    travel=gun_distance(age-1)+length*body_hit
                    pending[t+cfg.receive_delay]=pending.get(t+cfg.receive_delay,0.)+damage_at_distance(travel,cfg);b['stopped']=True
                elif hit[0]>=0:b['stopped']=True
                b['last']=end
        finish=min([len(path)-1,*[v for v in [enemy_down,atk_down]if v is not None]])+1
        return dict(kill=enemy_down is not None and(atk_down is None or enemy_down<atk_down),
                    attacker_down=atk_down,enemy_down=enemy_down,exposure_frames=int(visible[:finish].sum()),
                    danger_frames=int(danger[:finish].sum()),stealth=not visible[:finish].any(),visible=visible,
                    shots=shots,events=events,uncertainties=term.get('uncertainties',[]))
