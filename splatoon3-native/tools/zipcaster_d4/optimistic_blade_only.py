"""Necessary lower bounds for contact-excluded projectile feasible routes."""
import math
import numpy as np
from tools.zipcaster_d4.model_v3 import schedule,post_path
from tools.zipcaster_d4.optimistic import envelopes,axis_distance
from tools.zipcaster_d4.blade_only import contact_exclusion

def terminal_bound(world,node,enemy,speed,program,ground=False,bounds=None):
 inputs=schedule(speed,program,world.cfg)
 if not inputs or program in ['full1','light2']:return None
 position=world.graph['ground'][node]if ground else world.graph['attach'][node]
 body=np.repeat(position[None,:],inputs[-1][0]+81,axis=0)if ground else post_path(position,world.graph['floor'][node],inputs[-1][0]+80)
 first,style=inputs[0];cb=first+(4 if style=='full'else 9)
 proof=contact_exclusion(world.shots.parameters,body[cb:cb+4],np.repeat(np.asarray(enemy)[None,:],4,axis=0),style)
 if not proof['certified_disjoint']:return None
 bounds=bounds or envelopes(world.shots.parameters);events=[]
 for release,style in inputs:
  full=style=='full';pb=release+(6 if full else 11)
  if full:
   distance=axis_distance(body[pb],enemy,2.2,.8);free=bounds[style]['projectile']+.03;travel,velocity=26*.8,.8
  else:
   distance=axis_distance(body[pb],enemy);free=bounds[style]['projectile']+math.hypot(1,1.4);travel,velocity=6*2.82,2.82
  if distance<=travel+free+1e-8:
   age=max(0,math.ceil((distance-free-1e-8)/velocity));events.append((pb+age+world.cfg.receive_delay,70 if full else 35))
 hp=100
 for due,damage in sorted(events):
  hp-=damage
  if hp<=0:
   extra=sum(world.cfg.full_cost if k=='full'else world.cfg.light_cost for t,k in inputs if t<=due)
   activation=world.cfg.activation_frames-world.cfg.activation_drain_grace if ground else 0
   return (due+activation)*world.cfg.drain+extra
 return None
