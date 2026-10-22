"""Freeze new216 from complete fallback all-start queries, not old12.

Native setup domain is the predeclared ordinary-navigation-supported subset.
Its best two routes are reported alongside unrestricted-grid best two, never
silently substituted as the global game optimum. Full D4 stays unclosed.
"""
import argparse,json,math
from pathlib import Path
import numpy as np
from tools.zipcaster_d4.model_blade_only import World,ROOT
from tools.zipcaster_d4.calibration_plan_v4 import reachable
from tools.zipcaster_d3r.analyze_direction import sha

def main(a):
 assert not a.out.exists();batch=json.loads(a.bank.read_text());points=[];proofs=[];worlds={};nav={}
 assert len(batch['results'])==9
 for entry in sorted(batch['results'],key=lambda x:(x['state']['stage'],['center','central_high','west_lane'].index(x['state']['region']))):
  state=entry['state'];path=Path(entry['artifact']);q=json.loads(path.read_text());assert q['search_complete']or q.get('ordinary_supported_top2_certified')
  name=state['map']
  if name not in worlds:worlds[name]=World(ROOT/state['graph']);nav[name]=reachable(state['stage'])
  w=worlds[name];z=w.graph;e=np.array(state['enemy']);heading=state['heading'];support=lambda i:int(z['ground_atlas_ids'][i])in nav[name]
  wins=sorted([r for r in q['rows']if r.get('probability')==1 and support(r['start'])and not r.get('attack_uncertainties')],key=lambda r:(r['cost'],r['exposure_frames'],abs(r['position'][1]-e[1]),float(np.linalg.norm(np.array(r['position'])-e)),r['start']))
  assert len(wins)>=2,(name,state['region'],'no supported fallback pair')
  selected=wins[:2];controls=[]
  for i,s in enumerate(z['ground']):
   delta=s-e;distance=np.linalg.norm(delta);forward=float(delta[0]*math.sin(heading*math.pi/2)+delta[2]*math.cos(heading*math.pi/2))
   if not support(i)or not 2<distance<11 or forward<=2 or forward/distance<=.5:continue
   out=w.simulate(np.repeat(s[None,:],32,axis=0),0,dict(damage_events=[],kill_frame=31),e,heading*math.pi/2)
   if out['attacker_down']is not None and out['attacker_down']<31:controls.append((abs(s[1]-e[1]),distance,i,out['attacker_down']))
  assert controls,(name,state['region'],'no interior pre-action-death control')
  control=min(controls);ci=control[2]
  proof=dict(state=state,query=str(path),query_sha256=sha(path),heatmap_complete=q['search_complete'],prefix_certificate=q.get('prefix_proof'),all_declared_ground=w.g,ordinary_supported=sum(support(i)for i in range(w.g)),supported_wins=len(wins),
    all_grid_top2=q['top2']if q.get('start_domain')!='ordinary-navigation-supported-only'else None,query_start_domain=q.get('start_domain','all-declared-ground'),selected_supported_top2=selected,global_game_optimum_closed=False,
    selection='Complete cost order/certificate inside ordinary-navigation-supported setup domain; height/distance/ID break exact primary-cost/exposure ties only. Unsupported layers retained in all-grid data; not certified native standing cells.')
  proofs.append(proof)
  for band,r in [('top1',selected[0]),('top2',selected[1]),('control',dict(start=ci,position=z['ground'][ci].tolist(),hooks=[],program='full-light',probability=0,attacker_down=control[3]))]:
   points.append(dict(id=f'{name}-{state["region"]}-blade-bank-{band}',graph=state['graph'],enemy=e.tolist(),enemy_index=state['enemy_index'],heading=heading,region=state['region'],
    source=r['position'],speed=40,hooks=r.get('hooks',[]),program=r.get('program','full-light'),band=band,minimum_actual_control_margin=1.,model=r,
    selection_scope='Top2 in predeclared ordinary-supported, contact-disjoint/whole-wave-clear feasible-route model. Full D4/global native optimum unclosed.'))
 out=dict(schema='inklab.d4.blade-only.plan.bank.v1',points=points,proofs=proofs,repeats=8,planned=216,bank_sha256=sha(a.bank),source_sha256=sha(__file__),old12_reused=False,full_d4_passed=False,
  scope='New216 after mechanism qualification. Unrestricted all-grid results retained separately. Direct aim/special fixture; no formal policies/T1.')
 a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(points=len(points),planned=216,hook_points=sum(bool(p['hooks'])for p in points))))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--bank',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
