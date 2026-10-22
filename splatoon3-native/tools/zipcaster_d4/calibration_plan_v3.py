"""Prospective native cohort with global-score ties and robust threat controls.

Enemy positions fixed by geometry. Four headings are tried in declared order
only to find ordinary-setup-supported globaltop2 and an interior-FOV poor case.
No native outcome is read. All earlier boundary-control trials remain separate.
"""
import argparse,gzip,json,sys,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from arena.lib.atlas import MapAtlas
from tools.zipcaster_d4.model_v2 import World
from tools.zipcaster_d3r.analyze_direction import sha

def main(a):
 if a.out.exists():raise ValueError('fresh plan')
 points=[];sources={};decisions=[];worlds={}
 for state in json.loads(a.states.read_text())['states']:
  name=state['map'];atlas=MapAtlas.load(state['stage']);z=np.load(ROOT/state['graph']/'graph.npz');todo=[atlas.nearest(atlas.spawns[t]['ground'])for t in['alpha','bravo']];seen=set(todo)
  for i in todo:
   for j in atlas.edges[i]:
    if j not in seen:seen.add(j);todo.append(j)
  feasible=lambda r:int(z['ground_atlas_ids'][r['start']])in seen
  if name not in worlds:worlds[name]=World(ROOT/state['graph'])
  world=worlds[name];enemy=np.array(state['enemy']);attempts=[];chosen=None
  for heading in[state['heading'],*[i for i in range(4)if i!=state['heading']]]:
   path=a.bank/f"{name}-e{state['enemy_index']}-h{heading}-s40.json.gz";q=json.loads(gzip.decompress(path.read_bytes()))['result'];assert q['search_complete'];sources[str(path.resolve().relative_to(ROOT))]=sha(path);win=sorted([r for r in q['rows']if r['probability']==1],key=lambda r:(r['cost'],r['exposure_frames'],r['start']));top=[r for r in win if feasible(r)][:2]
   equal=len(top)==2 and all(abs(r['cost']-win[i]['cost'])<1e-9 and r['exposure_frames']==win[i]['exposure_frames']for i,r in enumerate(top))
   if not equal:attempts.append(dict(heading=heading,reason='globaltop2 score not reproducible by ordinary-route-supported ties'));continue
   axis=np.array([math.sin(heading*math.pi/2),0,math.cos(heading*math.pi/2)]);pool=[]
   for r in q['rows']:
    delta=np.array(r['position'])-enemy;distance=np.linalg.norm(delta);forward=float(delta@axis)
    if r['probability']==0 and feasible(r)and 2<distance<11 and forward>2 and forward/distance>.5:pool.append(r)
   control=None
   for r in sorted(pool,key=lambda r:(np.linalg.norm(np.array(r['position'])-enemy),r['start'])):
    path0=np.repeat(np.array(r['position'])[None,:],32,axis=0);out=world.simulate(path0,0,dict(damage_events=[],kill_frame=31),enemy,heading*math.pi/2)
    if out['attacker_down']is not None and out['attacker_down']<31:control=r;break
   if control is None:attempts.append(dict(heading=heading,reason='no interior-FOV reachable poor control with modeled pre-attack death'));continue
   chosen=(heading,q,top,control);attempts.append(dict(heading=heading,reason='selected before native outcomes'));break
  assert chosen is not None,(name,state['region'],attempts)
  heading,q,top,control=chosen;decisions.append(dict(map=name,region=state['region'],attempts=attempts))
  for label,r in[('top1',top[0]),('top2',top[1]),('control',control)]:
   points.append(dict(id=f"{name}-{state['region']}-{label}",graph=state['graph'],enemy=state['enemy'],enemy_index=state['enemy_index'],heading=heading,region=state['region'],source=r['position'],speed=40,hooks=r.get('hooks',[]),program=r.get('program','full-light'),band=label,minimum_actual_control_margin=1.,model=r,global_original_top2=[{k:x[k]for k in['start','position','cost','exposure_frames']}for x in q['top2']],selection_scope='Exact global primary score and exposure ties, ordinary setup support tie-break. Poor control is strictly inside FOV, no native outcome selection. Actual initial danger+forward margin>1u checked beforeRS.'))
 out=dict(schema='inklab.d4.native.plan.v3',points=points,repeats=8,source_sha256=sha(__file__),inputs_sha256=sources,states_sha256=sha(a.states),decisions=decisions,scope='9enemy states/27points/8repeats216planned. All prior positive trials may only be reused if original predeclared inputs match; every outcome retained. Earlier boundary controls stay auxiliary, not silently dropped or called void. No native outcome read by selection.');a.out.write_text(json.dumps(out,indent=2)+'\n');print(a.out)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--bank',type=Path,required=True);p.add_argument('--states',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
