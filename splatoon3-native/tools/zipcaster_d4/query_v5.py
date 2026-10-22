"""Enemy-conditioned all-start query; no uniform enemy-position average.

Top-only can certify the first two winners against global cost lower bounds
without pretending the rest of the heatmap has been completed. A candidate cap
is debug-only and explicitly yields unresolved probability intervals.
"""
import argparse,json,math,sys,time,heapq
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d4.model_v3 import World,Config,PROGRAMS
from tools.zipcaster_d4.reverse_v2 import Reverse
from tools.zipcaster_d3r.analyze_direction import sha

def clean(x):
 if isinstance(x,np.ndarray):return x.tolist()
 if isinstance(x,np.generic):return x.item()
 if isinstance(x,dict):return{k:clean(v)for k,v in x.items()}
 if isinstance(x,(tuple,list)):return[clean(v)for v in x]
 return x

def query(a):
 if a.out.exists():raise ValueError('fresh query output directory')
 a.out.mkdir(parents=True);began=time.monotonic();world=World(a.graph);z=world.graph;enemy=z['ground'][a.enemy_index];heading=a.heading*math.pi/2;terms=[];counts={};t0=time.monotonic()
 for node in range(world.h):
  if np.linalg.norm(z['attach'][node]-enemy)>27:continue
  for program in a.programs:
   term=world.terminal(node,enemy,a.speed,program)
   if term is not None:terms.append(term)
 if a.min_hooks==0:
  for node in range(world.g):
   if np.linalg.norm(z['ground'][node]-enemy)>23:continue
   for program in a.programs:
    term=world.terminal(node,enemy,a.speed,program,ground=True)
    if term is not None:terms.append(term)
 print('D4_TERMINALS '+json.dumps(dict(map=world.meta['map'],enemy=a.enemy_index,heading=a.heading,speed=a.speed,programs=len(terms),seconds=time.monotonic()-t0)),flush=True)
 # Remove identical finite attack programs after an earlier contact KO.
 unique={}
 for term in terms:
  key=(term['node'],term.get('ground',False),term['kill_frame'],tuple(term['inputs']),tuple((e['due'],e['damage'],e['source'])for e in term['damage_events']))
  unique.setdefault(key,term)
 counts['duplicate_programs']=len(terms)-len(unique);terms=list(unique.values())
 # Arrival HP100/no incoming bullets is an optimistic bound. Every possible
 # automatic-gun phase0..8 must lose before a terminal can be safely rejected.
 if a.prune_terminal:
  kept=[]
  for term in terms:
   if any(world.simulate(term['post'],0,term,enemy,heading,phase)['kill']for phase in range(9)):kept.append(term)
  counts['terminal_optimistically_impossible']=len(terms)-len(kept);terms=kept
 prefix_cache={}
 def prefix_check(edges):
  if edges not in prefix_cache:
   node=int(z['edge_destination'][edges[-1]]);dummy=dict(node=node,post=z['attach'][node][None,:],damage_events=[],kill_frame=0);path,arrival,_=world.route_path(dict(edges=edges),dummy);outcome=world.simulate(path,arrival,dummy,enemy,heading);prefix_cache[edges]=outcome['attacker_down'] is None
  return prefix_cache[edges]
 cfg=world.cfg;edge_frames=z['edge_frames'].astype(float)+np.where(z['edge_source']<world.g,cfg.activation_frames-cfg.activation_drain_grace,6);cost=edge_frames*cfg.drain+cfg.hook_cost;reverse=Reverse(z['edge_source'],z['edge_destination'],cost,world.g,world.h,terms,prefix_check=prefix_check);rows=[];best=[];order=np.argsort(reverse.lower[3][:world.g],kind='stable');processed=set();all_candidates=0;top_certified=False
 ground_terms={}
 for term in terms:
  if term.get('ground'):ground_terms.setdefault(term['node'],[]).append(term)
 for start in order:
  start=int(start);lower=float(reverse.lower[3][start]);position=z['ground'][start];row=dict(start=start,position=position.tolist(),probability=None,probability_interval=[0,1],complete=False,status='unresolved',cost_lower_bound=lower if math.isfinite(lower)else None,candidates=0)
  if np.linalg.norm(position[[0,2]]-enemy[[0,2]])<.7 and abs(position[1]-enemy[1])<1.7:row.update(status='occupied',probability_interval=None,complete=True)
  elif not lower<1-1e-10:row.update(probability=0,probability_interval=[0,0],complete=True,status='unreachable-in-declared-graph')
  elif (down:=world.initial_stationary_death(start,enemy,heading,ground_terms.get(start,[]))) is not None:row.update(probability=0,probability_interval=[0,0],complete=True,status='dies-before-any-declared-route-can-move-or-kill',attacker_down=down)
  else:
   for candidate in reverse.candidates(start):
    row['candidates']+=1;all_candidates+=1;term=terms[candidate['terminal']];path,arrival,events=world.route_path(candidate,term);outcome=world.simulate(path,arrival,term,enemy,heading)
    if outcome['kill']:
     row.update(probability=1,probability_interval=[1,1],complete=True,status='predicted-kill',remaining=candidate['remaining'],grade=candidate['grade'],cost=candidate['cost'],edges=list(candidate['edges']),hooks=[int(z['edge_destination'][e])for e in candidate['edges']],program=term['program'],exposure_frames=outcome['exposure_frames'],danger_frames=outcome['danger_frames'],stealth=bool(outcome['stealth']),kill_frame=outcome['enemy_down'],arrival_frame=arrival,route_events=events,terminal_inputs=term['inputs'],program_native_verified=term['program_native_verified'],attack_uncertainties=term.get('uncertainties',[]));break
    if a.max_candidates and row['candidates']>=a.max_candidates:break
   else:row.update(probability=0,probability_interval=[0,0],complete=True,status='no-winning-route-in-declared-model')
  rows.append(row);processed.add(start)
  if row.get('probability')==1:best.append(row);best.sort(key=lambda r:(r['cost'],r['exposure_frames'],r['start']))
  if a.top_only and len(best)>=2:
   unqueried=np.array([i for i in range(world.g)if i not in processed]);bound=float(np.min(reverse.lower[3][unqueried]))if len(unqueried)else np.inf
   if bound>=best[1]['cost']-1e-10 and all(r['complete']or r['cost_lower_bound']>=best[1]['cost']for r in rows):top_certified=True;break
  if len(rows)%100==0:print('D4_QUERY '+json.dumps(dict(processed=len(rows),total=world.g,candidates=all_candidates,kills=sum(r.get('probability')==1 for r in rows),seconds=time.monotonic()-began)),flush=True)
  # Incremental output preserves completed work; incomplete is never converted0.
  if len(rows)%100==0:(a.out/'partial.json').write_text(json.dumps(clean(dict(rows=rows)),separators=(',',':'))+'\n')
 counts['prefix_checked']=len(prefix_cache);counts['prefix_proven_dead']=sum(not v for v in prefix_cache.values())
 out=dict(schema='inklab.d4.query.v3',map=world.meta['map'],stage=world.meta['stage'],enemy_index=a.enemy_index,enemy=enemy.tolist(),heading_quadrant=a.heading,heading_radians=heading,speed=a.speed,programs=a.programs,rows=rows,top2=best[:2],top2_certified_in_declared_model=top_certified or(len(best)>=2 and len(rows)==world.g and all(r['complete']for r in rows)),search_complete=len(rows)==world.g and all(r['complete']for r in rows),ground_nodes=world.g,wall_nodes=world.h,terminals=len(terms),counts=counts,candidates=all_candidates,seconds=time.monotonic()-began,config=clean(cfg.__dict__),source_sha256={str(p.relative_to(ROOT)):sha(p)for p in[Path(__file__),Path(__file__).with_name('model_v3.py'),Path(__file__).with_name('reverse_v2.py'),Path(__file__).with_name('flight_v2.py'),*[Path(__file__).with_name(n)for n in ['attack_model_v3.py','attack_model_v4.py','attack_model_v5.py','attack_geometry.py','attack_batch.py','attack_batch_v2.py','attack_cache.py','attack_sequence_v2.py','contact_shape.py','recoil.py']]]},graph_sha256=sha(a.graph/'graph.npz'),graph_meta_sha256=sha(a.graph/'graph.json'),shot_parameter_sha256=sha(ROOT/'work/a6/parameters.json'),attack_parameters_sha256=sha(ROOT/'work/d3r/attack-parameters-v1.json'),attack_fit_sha256=sha(ROOT/'work/d4/restart-v3/attack-fit-v1.json'),recoil_fit_sha256=sha(ROOT/'work/d4/restart-v3/recoil-fit-v2.json'),minimum_hooks=a.min_hooks,scope=['Conditional on the selected static enemy state, no uniform enemy-position average. Deterministic direction gives0/1, not calibrated native probability.','All declared ground starts and material-wall graph,0..3 hooks (or explicit fly-only filter), ground-zero-hook baseline included, finite named programs. Earliest successful route in exhaustive cost order, not a beam/ranked start bank.','Corrected native muzzle/player-volume/contact140+20 and recoil model; certified only within the declared finite model, not a game-wide proof. Best-route attack uncertainties are explicit.','Full100HP, separate contact140/20 and projectile70/35 accumulation even in stealth. Fixed180deg cone, ideal gun aim within it; pending user clarification retained inGOAL.','Gun falloff can require3shots at13.4u, despite nominal52 two-shot within full-damage range. Contact included; no regen/armor/spread term.','Partial paths contain no own attacks; a native-model death before their end proves every attack-only suffix loses, so that prefix is discarded. No beam/rank cap.','Candidate caps produce unresolved intervals. Top-only is not a completed heatmap; no unknown values painted0.']);(a.out/'result.json').write_text(json.dumps(clean(out),indent=2)+'\n');print('D4_QUERY_DONE '+json.dumps({k:out[k]for k in['map','enemy_index','speed','search_complete','top2_certified_in_declared_model','candidates','seconds']}),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--graph',type=Path,required=True);p.add_argument('--enemy-index',type=int,required=True);p.add_argument('--heading',type=int,choices=[0,1,2,3],default=0);p.add_argument('--speed',type=int,choices=[20,40,60,129],default=40);p.add_argument('--programs',nargs='+',choices=PROGRAMS,default=PROGRAMS);p.add_argument('--out',type=Path,required=True);p.add_argument('--top-only',action='store_true');p.add_argument('--prune-terminal',action=argparse.BooleanOptionalAction,default=True);p.add_argument('--min-hooks',type=int,choices=[0,1],default=0);p.add_argument('--max-candidates',type=int,default=0);query(p.parse_args())
