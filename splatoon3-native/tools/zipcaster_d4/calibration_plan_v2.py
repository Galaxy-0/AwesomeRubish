"""Freeze9enemy states × (global score-equivalent top2 + poor control).

Ties may choose an ordinarily reachable setup. A worse resource score is never
renamed globaltop2. No native outcome is used in point selection.
"""
import argparse,gzip,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from arena.lib.atlas import MapAtlas
from tools.zipcaster_d3r.analyze_direction import sha

def main(a):
 if a.out.exists():raise ValueError('fresh frozen plan')
 states=json.loads(a.states.read_text())['states'];points=[];evidence={}
 for state in states:
  name=state['map'];atlas=MapAtlas.load(state['stage']);z=np.load(ROOT/state['graph']/'graph.npz');todo=[atlas.nearest(atlas.spawns[t]['ground'])for t in['alpha','bravo']];seen=set(todo)
  for i in todo:
   for j in atlas.edges[i]:
    if j not in seen:seen.add(j);todo.append(j)
  feasible=lambda row:int(z['ground_atlas_ids'][row['start']])in seen
  # Specific geometry-only override: h2 top1 ties include an unsupported
  # isolated layer. h0 retains two globally top-scoring ordinary setups.
  heading=0 if name=='Yagara'and state['region']=='central_high'else state['heading'];path=a.bank/f"{name}-e{state['enemy_index']}-h{heading}-s40.json.gz";q=json.loads(gzip.decompress(path.read_bytes()))['result'];assert q['search_complete'];evidence[str(path.resolve().relative_to(ROOT))]=sha(path)
  winners=sorted([r for r in q['rows']if r['probability']==1],key=lambda r:(r['cost'],r['exposure_frames'],r['start']));selected=[r for r in winners if feasible(r)][:2];assert len(selected)==2
  for i,r in enumerate(selected):assert abs(r['cost']-winners[i]['cost'])<1e-9 and r['exposure_frames']==winners[i]['exposure_frames'],'no worse-score substitution'
  poor=[r for r in q['rows']if r['status']=='dies-before-any-declared-route-can-move-or-kill'and feasible(r)and 2<np.linalg.norm(np.array(r['position'])-state['enemy'])<11 and ((np.array(r['position'])-state['enemy'])[0]*np.sin(heading*np.pi/2)+(np.array(r['position'])-state['enemy'])[2]*np.cos(heading*np.pi/2))>2.0 and ((np.array(r['position'])-state['enemy'])[0]*np.sin(heading*np.pi/2)+(np.array(r['position'])-state['enemy'])[2]*np.cos(heading*np.pi/2))/np.linalg.norm(np.array(r['position'])-state['enemy'])>.5];assert poor,'needs a physical close-threat control';control=min(poor,key=lambda r:(np.linalg.norm(np.array(r['position'])-state['enemy']),r['start']))
  for label,r in[('top1',selected[0]),('top2',selected[1]),('control',control)]:
   points.append(dict(id=f"{name}-{state['region']}-{label}",graph=state['graph'],enemy=state['enemy'],enemy_index=state['enemy_index'],heading=heading,region=state['region'],source=r['position'],speed=40,hooks=r.get('hooks',[]),program=r.get('program','full-light'),band=label,minimum_actual_control_margin=1.0,model=r,global_original_top2=[{k:v[k]for k in['start','position','cost','exposure_frames']}for v in winners[:2]],selection_scope='Same exact primary resource and exposure score as globaltop2; ordinarily reachable tie preferred. Control chosen geometrically inside FOV with>2u projected forward margin and cosine>.5; initial actual danger+>1u margin required before combat. No combat-outcome-driven selection.'))
 out=dict(schema='inklab.d4.native.plan.v1',points=points,repeats=8,source_sha256=sha(__file__),inputs_sha256=evidence,states_sha256=sha(a.states),scope='Three common enemy states/map,27points,8repeats216planned. Stationary fixed FOV/ideal aim. Primary globaltop2 happen to be zero-hook ground baselines; does not validate best hooked routes. Geometry-feasible ties explicitly recorded, no native-success-driven resampling.');a.out.write_text(json.dumps(out,indent=2)+'\n');print(a.out)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--bank',type=Path,required=True);p.add_argument('--states',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
