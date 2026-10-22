"""New216 plan, contact-disjoint/whole-wave-clear finite fallback only.

3u ground lattice plus the orientation-independent contact exclusion imply
>=6u horizontal separation. With yaw aimed at the target, horizontal side
balls have no forward offset; light muzzle forward projection <=sqrt(2.96),
player extension <=.72. Thus final light travel needs >=2frames on this grid.
A full-light ground KO at93f reaches the declared fallback's lower bound.
Every hook costs2.67% before its attack; even permitting zero projectile
travel cannot beat such a ground route. This is not the unrestricted D4 optimum.
"""
import argparse,json,math,time
from pathlib import Path
import numpy as np
from tools.zipcaster_d4.model_blade_only import World,ROOT,Config
from tools.zipcaster_d4.calibration_plan_v4 import reachable
from tools.zipcaster_d3r.analyze_direction import sha

def lower_bound(cfg=Config()):
 light_age=math.ceil((6-math.hypot(1,1.4)-.72)/2.82)
 assert light_age==2
 activation=cfg.activation_frames-cfg.activation_drain_grace
 costs={
 'full-light':(40+36+11+light_age+cfg.receive_delay+activation)*cfg.drain+cfg.full_cost+cfg.light_cost,
 'light-full':(40+30+21+6+cfg.receive_delay+activation)*cfg.drain+cfg.full_cost+cfg.light_cost,
 'full2':(40+36+21+6+cfg.receive_delay+activation)*cfg.drain+2*cfg.full_cost,
 'light3':(40+60+11+cfg.receive_delay+activation)*cfg.drain+3*cfg.light_cost}
 # Any wall terminal may have non-lattice XZ. Grant age0 and no flight/B time.
 hook=(40+36+11+cfg.receive_delay+activation)*cfg.drain+cfg.full_cost+cfg.light_cost+cfg.hook_cost
 return dict(ground_program_bounds=costs,ground_best=min(costs.values()),one_hook_or_more=hook,
  light_travel_minimum=light_age,scope='Declared40f programs, ideal bearing aim, contact-disjoint 3u ground lattice. No precharge/pre-arrival attacks. Contact/full D4/global game optimality unclosed.')

def main(a):
 assert not a.out.exists();began=time.monotonic();points=[];proofs=[];worlds={};nav={};bound=lower_bound()
 for state in json.loads(a.states.read_text())['states']:
  name=state['map']
  if name not in worlds:worlds[name]=World(ROOT/state['graph']);nav[name]=reachable(state['stage'])
  w=worlds[name];z=w.graph;e=np.array(state['enemy']);assert np.max(np.abs(z['ground'][:,[0,2]]/3-np.round(z['ground'][:,[0,2]]/3)))<1e-8
  assert np.max(np.abs(e[[0,2]]/3-np.round(e[[0,2]]/3)))<1e-8
  # Only exact lower-bound ties are accepted. No sample/rank cap can grant a certificate.
  candidates=[i for i,s in enumerate(z['ground'])if int(z['ground_atlas_ids'][i])in nav[name]and 5.8<np.linalg.norm((s-e)[[0,2]])<=12]
  candidates.sort(key=lambda i:(abs(z['ground'][i,1]-e[1]),np.linalg.norm(z['ground'][i]-e),i))
  selected=None;attempts=[]
  for heading in [state['heading'],*[h for h in range(4)if h!=state['heading']]]:
   wins=[];tested=0
   for i in candidates:
    s=z['ground'][i];visible,danger=w.visibility(np.repeat(s[None,:],2,axis=0),e,heading*math.pi/2)
    if visible.any():continue
    t=w.terminal(i,e,40,'full-light',True);tested+=1
    if t is None or abs(t['cost']-bound['ground_best'])>1e-9:continue
    p,arrival,events=w.route_path(dict(edges=[]),t);out=w.simulate(p,arrival,t,e,heading*math.pi/2)
    if out['kill']and out['stealth']:
     wins.append(dict(start=i,position=s.tolist(),cost=t['cost'],remaining=1-t['cost'],program='full-light',hooks=[],probability=1,
      kill_frame=out['enemy_down'],exposure_frames=out['exposure_frames'],contact_exclusion=t['contact_exclusion']))
     if len(wins)==2:break
   attempts.append(dict(heading=heading,tested=tested,exact_bound_winners=len(wins)))
   if len(wins)<2:continue
   controls=[]
   for i,s in enumerate(z['ground']):
    delta=s-e;distance=np.linalg.norm(delta);forward=float(delta[0]*math.sin(heading*math.pi/2)+delta[2]*math.cos(heading*math.pi/2))
    if int(z['ground_atlas_ids'][i])not in nav[name]or not 2<distance<11 or forward<=2 or forward/distance<=.5:continue
    out=w.simulate(np.repeat(s[None,:],32,axis=0),0,dict(damage_events=[],kill_frame=31),e,heading*math.pi/2)
    if out['attacker_down']is not None and out['attacker_down']<31:controls.append((abs(s[1]-e[1]),distance,i,out['attacker_down']))
   if controls:selected=(heading,wins,min(controls));break
  if selected is None:
   a.out.with_suffix('.partial.json').write_text(json.dumps(dict(points=points,proofs=proofs,failed_state=state,attempts=attempts),indent=2)+'\n');raise RuntimeError(('No exact lower-bound feasible pair; no native trials authorized for unclosed plan',state,attempts))
  heading,wins,control=selected;ci=control[2]
  for band,row in [('top1',wins[0]),('top2',wins[1]),('control',dict(start=ci,position=z['ground'][ci].tolist(),probability=0,attacker_down=control[3]))]:
   points.append(dict(id=f'{name}-{state["region"]}-blade-{band}',graph=state['graph'],enemy=e.tolist(),enemy_index=state['enemy_index'],heading=heading,region=state['region'],source=row['position'],speed=40,hooks=[],program='full-light',band=band,minimum_actual_control_margin=1.,model=row,
    selection_scope='Exact universal lower-bound ties in contact-disjoint/whole-wave-clear fallback; not unrestricted D4 top2. Native outcomes not read.'))
  proofs.append(dict(state=state,heading=heading,bound=bound,attempts=attempts,selected=[r['start']for r in wins],source_candidates=len(candidates),unrestricted_optimality_closed=False))
  a.out.with_suffix('.partial.json').write_text(json.dumps(dict(points=points,proofs=proofs),indent=2)+'\n');print('D4_BLADE_PLAN '+json.dumps(dict(map=name,region=state['region'],heading=heading,selected=[r['start']for r in wins],seconds=time.monotonic()-began)),flush=True)
 out=dict(schema='inklab.d4.blade-only.plan.v1',points=points,proofs=proofs,repeats=8,planned=216,states_sha256=sha(a.states),source_sha256=sha(__file__),full_d4_passed=False,
  scope='New216, no reuse of old12. Restricted feasible-route mechanism qualification required before batch; complete contact/global D4 remains unclosed.')
 a.out.write_text(json.dumps(out,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--states',type=Path,default=Path('work/d4/common-enemy-states-v2.json'));p.add_argument('--out',type=Path,required=True);main(p.parse_args())
