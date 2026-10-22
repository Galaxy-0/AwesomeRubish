"""D4 scoped projectile-only feasible routes. Full/global claims stay false."""
import numpy as np
from tools.zipcaster_d4.model_v3 import World as BaseWorld,ROOT,Config,schedule,post_path
from tools.zipcaster_d4.blade_only import Shots,sequence

class World(BaseWorld):
 def __init__(self,directory,cfg=Config(),fit=None,recoil=None):
  super().__init__(directory,cfg,fit,recoil)
  self.shots=Shots(self,fit or ROOT/'work/d4/restart-v3/attack-fit-v1.json')
 def terminal(self,node,enemy,speed,program,ground=False):
  inputs=schedule(speed,program,self.cfg)
  # full1/light2 cannot reach100HP when all contact is excluded.
  if not inputs or program in ['full1','light2']:return None
  position=self.graph['ground'][node]if ground else self.graph['attach'][node]
  if np.linalg.norm(position-enemy)>28:return None
  horizon=inputs[-1][0]+80
  body=np.repeat(position[None,:],horizon+1,axis=0)if ground else post_path(position,self.graph['floor'][node],horizon)
  result=sequence(self.shots,body,enemy,inputs,self.recoil,self.cfg.receive_delay)
  kill=result['kill_frame']
  if kill is None or not result['eligible_feasible_route']:return None
  used=[(t,k)for t,k in inputs if t<=kill]
  activation=self.cfg.activation_frames-self.cfg.activation_drain_grace if ground else 0
  return dict(node=node,ground=ground,speed=speed,program=program,cost=(kill+activation)*self.cfg.drain+sum(self.cfg.full_cost if k=='full'else self.cfg.light_cost for t,k in used),
   kill_frame=kill,damage_events=result['damage_events'],inputs=used,post=body[:kill+1],enemy_path=result['target_path'][:kill+1],
   attack_casts=result['casts'],contact_exclusion=result['contact_exclusion'],uncertainties=result['uncertainties'],
   program_native_verified=False,full_d4_passed=False,
   scope='Contact-guaranteed-disjoint AND whole-wave-clear projectile feasible route; unrestricted/native optimality unclosed.')
