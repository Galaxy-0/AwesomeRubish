"""Fixed enemy, ideal-operation deterministic D4 contract, no invented prior.

P is0/1 until an explicit error distribution is added. Native repetition rates
are separate. No enemy turning/walking; logical180deg cone remains fixed even
when the gun can aim within it. Source activation exposure is included.
"""
import math,sys,json
from dataclasses import dataclass,asdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'tools/zipcaster_d3'),str(ROOT)]
from tools.zipcaster_d4.geometry import Mesh
from tools.zipcaster_d4.flight_v2 import path as flight_path
from tools.zipcaster_d3r.native_kinematics import JUMP_T,JUMP_Y
from tools.zipcaster.surfaces import load_surfaces
@dataclass(frozen=True)
class Config:
 activation_frames:int=30
 activation_drain_grace:int=11
 drain:float=.1/60
 hook_cost:float=.04/1.5
 light_cost:float=.052/1.5
 full_cost:float=.117/1.5
 vision_range:float=30.
 gun_range:float=13.4
 gun_interval:int=9
 gun_spawn:int=2
 receive_delay:int=4
 gun_radius:float=.285
 gun_full_range:float=12.9352
 gun_falloff:float=5.9119
 full_speed:float=.8
 light_speed:float=2.82
 light_spawn:int=11
 full_spawn:int=6
 full_range:float=22.
 light_range:float=19.
 charge:int=21
 max_hooks:int=3
 counter_capacity:int=540

def post_path(attach,floor,length):
 out=np.repeat(np.asarray(attach,float)[None,:],length+1,axis=0);t=np.arange(length+1);dy=np.interp(t,JUMP_T,JUMP_Y);dy[t>64]=JUMP_Y[-1]-.24*(t[t>64]-64);out[:,1]=np.maximum(floor,out[:,1]+dy);return out

def schedule(speed,program,cfg=Config()):
 if speed not in[20,40,60,129]:raise ValueError('operation band')
 if program=='light3':return[(speed+j*30,'light')for j in range(3)]
 if program=='light-full':return[(speed,'light'),(speed+30+cfg.charge,'full')]
 if speed<cfg.charge:return[] # Measured20f full precharge did not work.
 if program=='full-light':return[(speed,'full'),(speed+36,'light')]
 if program=='full2':return[(speed,'full'),(speed+36+cfg.charge,'full')]
 raise ValueError('unknown finite attack program')

def damage_at_distance(distance,cfg=Config()):return max(30.,min(52.,52.-(distance-cfg.gun_full_range)*cfg.gun_falloff))
def gun_distance(age):return float(np.interp(age,[0,1,2,3,4,8,12,16,20,35],[0,3.06,6.12,8.4,10.2,11.8,12.6,13.15,13.7,15.5]))
def segment_distance(a,b,p,q):
 # Closest distance of two finite segments; degenerate cases included.
 u=b-a;v=q-p;w=a-p;aa=float(u@u);bb=float(u@v);cc=float(v@v);dd=float(u@w);ee=float(v@w);den=aa*cc-bb*bb
 if aa<1e-15:return float(np.linalg.norm(a-(p+v*np.clip(ee/max(cc,1e-15),0,1))))
 if cc<1e-15:return float(np.linalg.norm(p-(a+u*np.clip(-dd/aa,0,1))))
 s=float(np.clip((bb*ee-cc*dd)/den,0,1))if den>1e-15 else 0.;t=(bb*s+ee)/cc
 if t<0:t=0.;s=float(np.clip(-dd/aa,0,1))
 elif t>1:t=1.;s=float(np.clip((bb-dd)/aa,0,1))
 return float(np.linalg.norm(w+s*u-t*v))

def capsule_hit_fraction(a,b,radius=.635):
 """First contact of a relative moving bullet with the vertical body capsule."""
 a=np.asarray(a,float);b=np.asarray(b,float);d=b-a;nearest=a-np.array([0,np.clip(a[1],.35,1.35),0])
 if nearest@nearest<=radius*radius:return 0.
 hits=[];aa=float(d[[0,2]]@d[[0,2]]);bb=float(a[[0,2]]@d[[0,2]]);cc=float(a[[0,2]]@a[[0,2]]-radius*radius);disc=bb*bb-aa*cc
 if aa>1e-15 and disc>=0:
  t=(-bb-math.sqrt(disc))/aa
  if 0<=t<=1 and .35<=a[1]+t*d[1]<=1.35:hits.append(t)
 for y in[.35,1.35]:
  q=a-[0,y,0];aa=float(d@d);bb=float(q@d);cc=float(q@q-radius*radius);disc=bb*bb-aa*cc
  if aa>1e-15 and disc>=0:
   t=(-bb-math.sqrt(disc))/aa
   if 0<=t<=1:hits.append(t)
 return min(hits)if hits else None

class World:
 def __init__(self,directory,cfg=Config()):
  self.directory=Path(directory);self.meta=json.loads((self.directory/'graph.json').read_text());self.graph=dict(np.load(self.directory/'graph.npz'));self.attack_parameters=json.loads((ROOT/'work/d3r/attack-parameters-v1.json').read_text());self.cfg=cfg;self.g=len(self.graph['ground']);self.h=len(self.graph['anchors']);self.flight=self.meta['flight_model'];name=self.meta['map'];tri,n,area,attrs=load_surfaces(ROOT/f'work/arena/maps/{name}');self.field=Mesh(tri[np.array(['Fence'not in a['mat_flags']for a in attrs])]);from arena.geometry import CollisionMesh
  self.vision=Mesh(CollisionMesh.load(ROOT/f'work/arena/maps/{name}/sight.npz').triangles)
 def visibility(self,path,enemy,heading):
  d=path-enemy;facing=d[:,0]*math.sin(heading)+d[:,2]*math.cos(heading);dist=np.linalg.norm(d,axis=1);eligible=(facing>=-1e-8)&(dist<=self.cfg.vision_range);visible=np.zeros(len(path),bool);ids=np.flatnonzero(eligible)
  if len(ids):
   ends=np.concatenate([path[ids]+[0,h,0]for h in[.12,.7,1.3]]);clear=self.vision.clear_pairs(np.asarray(enemy)+[0,1.1,0],ends).reshape(3,-1).any(axis=0);visible[ids]=clear
  return visible,visible&(dist<=self.cfg.gun_range)
 def terminal(self,node,enemy,speed,program,ground=False):
  cfg=self.cfg;inputs=schedule(speed,program,cfg)
  if not inputs:return None
  horizon=inputs[-1][0]+70;body=np.repeat(self.graph['ground'][node][None,:],horizon+1,axis=0) if ground else post_path(self.graph['attach'][node],self.graph['floor'][node],horizon);casts=[];damages=[];hp=100.
  for event,kind in inputs:
   full=kind=='full';birth=event+(cfg.full_spawn if full else cfg.light_spawn);pose=body[birth];footdelta=np.asarray(enemy)-pose;limit=cfg.full_range if full else cfg.light_range
   if np.linalg.norm(footdelta)>limit:continue
   origin=pose+[0,2.2 if full else 1.,0];delta=np.asarray(enemy)+[0,1.1,0]-origin;length=np.linalg.norm(delta)
   if length<1e-9:continue
   pitch=(math.atan2(delta[1],math.hypot(delta[0],delta[2]))-self.attack_parameters['blade_elevation_bias'])/self.attack_parameters['blade_elevation_scale']
   if abs(pitch)>.85:continue # Never grant an angle the native fixture clamps.
   direction=delta/length;offset=.8 if full else 1.4;radius=.5 if full else.3;maximum=max(0.,length-offset-radius-.35)
   if maximum>0:
    hit,_,_=self.field.sphere(origin+direction*min(offset,length),direction,radius,maximum)
    if hit[0]>=0:continue
   due=birth+int(math.ceil(np.linalg.norm(footdelta)/(cfg.full_speed if full else cfg.light_speed)))+cfg.receive_delay;casts.append(dict(input=event,birth=birth,due=due,kind=kind,damage=70 if full else 35))
  for cast in sorted(casts,key=lambda c:c['due']):
   hp-=cast['damage'];damages.append(cast)
   if hp<=0:break
  if hp>0:return None
  kill=damages[-1]['due'];lights=sum(k=='light'and t<=kill for t,k in inputs);fulls=sum(k=='full'and t<=kill for t,k in inputs);extra=lights*cfg.light_cost+fulls*cfg.full_cost;return dict(node=node,ground=ground,speed=speed,program=program,cost=(kill+(cfg.activation_frames-cfg.activation_drain_grace if ground else 0))*cfg.drain+extra,kill_frame=kill,damage_events=damages,inputs=inputs,post=body[:kill+1],program_native_verified=program in['full-light','light3'],scope='Static core sphere proxy andD3-R timing; full2/light-full need dedicated native control. No contact/melee bonus, regeneration or weapon aim errors.')
 def route_path(self,candidate,term):
  z=self.graph;pieces=[];events=[];elapsed=0;path_edges=candidate['edges']
  for i,edge in enumerate(path_edges):
   src=int(z['edge_source'][edge]);dst=int(z['edge_destination'][edge]);source=z['ground'][src]if src<self.g else z['attach'][src-self.g]
   if not i:
    prefix=np.repeat(source[None,:],self.cfg.activation_frames,axis=0);events.append(dict(frame=0,event='开大 / RS'));pieces.append(prefix);elapsed+=len(prefix)
   else:
    prefix=post_path(source,-40.,6)[1:];events.append(dict(frame=elapsed,event='B跳离'));pieces.append(prefix);elapsed+=6;source=prefix[-1]
   events.append(dict(frame=elapsed,event='出钩',node=dst));flight=flight_path(source,z['attach'][dst],self.flight)[1:];pieces.append(flight);elapsed+=len(flight);events.append(dict(frame=elapsed,event='挂住 / 到达',node=dst))
  if not path_edges:
   source=z['ground'][term['node']];pieces.append(np.repeat(source[None,:],self.cfg.activation_frames,axis=0));elapsed=self.cfg.activation_frames;events.append(dict(frame=0,event='开大 / 地面零钩基线'))
  arrival=elapsed;pieces.append(term['post']);return np.concatenate(pieces),arrival,events
 def simulate(self,path,arrival,term,enemy,heading,gun_phase=0):
  cfg=self.cfg;enemy=np.asarray(enemy,float);visible,danger=self.visibility(path,enemy,heading);due_events=[dict(e,**{k:arrival+e[k]for k in['input','birth','due']})for e in term['damage_events']];kill_expected=arrival+term['kill_frame'];hp=100.;enemy_hp=100.;atk_down=None;enemy_down=None;pending={};bullets=[];fire_at=gun_phase;shots=[];events=[]
  if not danger.any():return dict(kill=True,attacker_down=None,enemy_down=kill_expected,exposure_frames=int(visible.sum()),danger_frames=0,stealth=not visible.any(),visible=visible,shots=[],events=[])
  for t,p in enumerate(path):
   hp-=pending.get(t,0.)
   if hp<=0 and atk_down is None:atk_down=t
   for e in due_events:
    if e['due']==t and(atk_down is None or e['birth']<atk_down):enemy_hp-=e['damage'];events.append(dict(frame=t,event='命中'+str(e['damage'])))
   if enemy_hp<=0 and enemy_down is None:enemy_down=t
   if danger[t]and hp>0 and enemy_hp>0 and t>=fire_at:
    origin=enemy+[0,1.1,0];d=p+[0,1.1,0]-origin;d/=max(np.linalg.norm(d),1e-12);bullets.append(dict(birth=t+cfg.gun_spawn,origin=origin,direction=d,last=origin.copy(),stopped=False));shots.append(t);fire_at=t+cfg.gun_interval
   for b in bullets:
    age=t-b['birth']
    if b['stopped']or age<1:continue
    if age>35:b['stopped']=True;continue
    end=b['origin']+b['direction']*gun_distance(age);start=b['last'];movement=end-start;length=np.linalg.norm(movement);previous=path[max(0,t-1)];body_hit=capsule_hit_fraction(start-previous,end-p,.35+cfg.gun_radius)
    hit,_,dist=self.field.sphere(start,movement,cfg.gun_radius,max(length,1e-9))if length>1e-9 else(np.array([-1]),None,None)
    if body_hit is not None and(hit[0]<0 or length*body_hit<dist[0]-1e-6):
     travel=gun_distance(age-1)+length*body_hit;pending[t+cfg.receive_delay]=pending.get(t+cfg.receive_delay,0.)+damage_at_distance(travel,cfg);b['stopped']=True
    elif hit[0]>=0:b['stopped']=True
    b['last']=end
   if enemy_down is not None and(atk_down is None or enemy_down<atk_down):break
   if atk_down is not None and t>atk_down+60:break
  finish=min([len(path)-1,*[v for v in[enemy_down,atk_down]if v is not None]])+1
  return dict(kill=enemy_down is not None and(atk_down is None or enemy_down<atk_down),attacker_down=atk_down,enemy_down=enemy_down,exposure_frames=int(visible[:finish].sum()),danger_frames=int(danger[:finish].sum()),stealth=not visible[:finish].any(),visible=visible,shots=shots,events=events)

 def initial_stationary_death(self,start,enemy,heading,ground_terms=()):
  edges=np.flatnonzero(self.graph['edge_source']==start)
  limits=[self.cfg.activation_frames+min(t['kill_frame'] for t in ground_terms)] if ground_terms else []
  if len(edges):
   distances=self.graph['edge_distance'][edges];windups=np.maximum(0,np.floor(self.flight['windup_coefficients'][0]+self.flight['windup_coefficients'][1]*distances));limits.append(self.cfg.activation_frames+int(windups.min()))
  if not limits:return None
  horizon=max(0,min(limits));path=np.repeat(self.graph['ground'][start][None,:],horizon+1,axis=0);dummy=dict(damage_events=[],kill_frame=horizon)
  result=self.simulate(path,0,dummy,enemy,heading)
  down=result['attacker_down'];return down if down is not None and down<horizon else None
