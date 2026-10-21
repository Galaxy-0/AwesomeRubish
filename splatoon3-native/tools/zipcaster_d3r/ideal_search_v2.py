"""D3-R finite ranking from measured native hooks, explicit operation bands.

All reachable enemy grid cells x8 headings xvalid forms are coarse-screened.
Fine Monte Carlo is explicitly sampled; no continuous/global optimum claim.
"""
import argparse,json,math,sys,time
from pathlib import Path
from dataclasses import asdict
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'tools/zipcaster_d3'),str(ROOT)]
from tools.zipcaster_d3r.fit_mapping import collect
from tools.zipcaster_d3r.analyze_direction import sha
from arena.lib.atlas import MapAtlas
from geometry import CollisionMesh,reachable
from batch_geometry import BatchMesh
from paired_rays import clear_pairs
from tools.zipcaster_d3r.ideal_duel import Config
from tools.zipcaster_d3r.native_kinematics import JUMP_T,JUMP_Y
from tools.zipcaster_d3r.blade_field import BladeField
from tools.zipcaster_d3r.ideal_duel import duel_batch
from search_v2 import graph_motion
from budget import Gauge

def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,separators=(',',':'))+'\n')
def flight(row):
 data=json.loads((ROOT/row['artifact']).read_text());rec=next(c for c in data['records']if c['index']==row['index']);arr=rec.get('arrival_first_ack',{}).get('player_0')
 if arr is None:return None
 begin=row['source_frame'];end=arr['frame'];samples={begin:row['source']}
 for line in (ROOT/row['artifact']).with_name('steps.jsonl').open():
  d=json.loads(line);i=d['infos']['player_0']
  if begin<i['frame']<=end:samples[i['frame']]=i['position']
 frames=np.array(sorted(samples));points=np.array([samples[f]for f in frames]);return np.column_stack([np.interp(np.arange(begin,end+1),frames,points[:,i])for i in range(3)])
def trajectory(point,speed,style="full-light"):
 path=np.array(point['native_flight']);arrival=len(path)-1;attach=path[-1].copy();floor=point['landing'][1];tail=[]
 for t in range(1,speed+100):
  dy=float(np.interp(t,JUMP_T,JUMP_Y))if t<=64 else float(JUMP_Y[-1]-.24*(t-64));q=attach.copy();q[1]=max(floor,attach[1]+dy);tail.append(q)
 path=np.concatenate([path,np.array(tail)]);charge_start=arrival+speed-21
 cost=Gauge().cost(arrival+speed+(45 if style=="full-light"else 71),hooks=1,lights=1 if style=="full-light"else 3,fulls=int(style=="full-light"))
 if cost>=.96:return None,None,None
 events=[dict(frame=0,event='出钩'),dict(frame=arrival,event='到达 / B跳离')]
 if style=='full-light':events.extend([dict(frame=charge_start,event='开始蓄力'),dict(frame=arrival+speed,event='满蓄释放'),dict(frame=arrival+speed+36,event='轻斩输入')])
 else:events.extend(dict(frame=arrival+speed+j*30,event='轻斩输入'+str(j+1))for j in range(3))
 return path,charge_start,dict(spent=cost,available_at_R=.96,events=events,requires_precharge=False,style=style)

def plan(a):
 if a.out.exists():raise ValueError('fresh plan')
 rows,runs,opened=collect()
 if opened:raise ValueError('finish mapping first')
 points=[];maps=[];began=time.monotonic()
 for stage,name in enumerate(['Yunohana','District00','Yagara'],1):
  atlas=MapAtlas.load(stage);pts=np.asarray(atlas.points);ids=reachable(atlas,[atlas.region('center'),*[v['ground']for v in atlas.spawns.values()]]);mesh=BatchMesh(CollisionMesh.load(ROOT/f'work/arena/maps/{name}/sight.npz').triangles);pool=[]
  for r in rows:
   if r['map']!=name or not r['native_bind']or r['anchor']is None or r['arrival']is None or r['normal']is None or abs(r['normal'][1])>.5:continue
   path=flight(r)
   if path is None:continue
   attach=np.array(r['arrival']['position']);floor_node=atlas.nearest(attach);landing=pts[floor_node];dist=np.linalg.norm(pts[ids]-attach,axis=1);potential=float((dist<=19).mean());exposed=float((dist<=15.5).mean());score=potential-.6*exposed
   # A separate native calibration target with a genuine close-range .52 threat.
   dst=np.linalg.norm(pts-attach,axis=1);src=np.linalg.norm(pts-r['source'],axis=1);eligible=np.flatnonzero((dst>=7)&(dst<=11.5)&(src>=9)&(abs(pts[:,1]-landing[1])<4))
   ordered=sorted(eligible,key=lambda n:(abs(dst[n]-9),np.linalg.norm(pts[n]-atlas.region('center'))));target=None
   for n in ordered:
    if mesh.clear_many(attach+[0,1.1,0],np.array([pts[n]+[0,.85,0]]))[0]:target=pts[n].tolist();break
   if target is None:continue
   h=math.atan2(r['source'][0]-target[0],r['source'][2]-target[2]);pool.append(dict(id=f'{name}-b{r["batch"]}-c{r["index"]}',original_id=r['id'],map=name,stage=stage,source=r['source'],anchor=r['anchor'],normal=r['normal'],attach=attach.tolist(),landing=landing.tolist(),target=target,headings=[h-math.pi/3,h,h+math.pi/3],native_flight=path.tolist(),mapping_artifact=r['artifact'],mapping_sha256=r['raw_sha256'],heuristic_score=score,finite_static_range_upper=potential,enemy_grid_nodes=len(ids)))
  unique=[]
  for p in sorted(pool,key=lambda x:-x['heuristic_score']):
   if not any(np.linalg.norm(np.array(p['anchor'])-q['anchor'])<2 for q in unique):unique.append(p)
  chosen=[]
  for band,percent in[('high',.05),('middle',.5),('low',.95)]:
   candidates=sorted(range(len(unique)),key=lambda j:abs(j/max(1,len(unique)-1)-percent));count=0
   for j in candidates:
    p=unique[j]
    if p['id']in{x['id']for x in chosen}:continue
    chosen.append(p|dict(band=band,coarse_rank=j+1));count+=1
    if count==2:break
  if len(chosen)!=6:raise ValueError('six distinct measurable hooks needed '+name)
  points.extend(chosen);maps.append(dict(id=name,stage=stage,reachable_ids=ids.tolist(),reachable_nodes=len(ids),coarse_cells_headings_forms=len(ids)*16*len(pool),candidate_count=len(pool),distinct_hooks=len(unique),candidates=pool))
 out=dict(schema='inklab.d3r.ideal.plan.v1',full_d3r_passed=False,points=points,maps=maps,runs=runs,speeds=[20,40,60,129],limits=['Coarse score is a range/threat heuristic, not kill probability.','Measured source/anchor/arrival; subsequent B trajectory uses one low-wall measured template and nearest atlas floor until native validation.','Fine grid sampling disclosed, all-grid coarse screen does not prove global optimality.','20f requires at least1f in-flight precharge; unverified and marked conditional.','Native cohort heading prior is three source-facing angles; separate from global eight-heading prior.','Only single hooks are measured; a subsequent graph/beam path is an unvalidated model sequence.'],seconds=time.monotonic()-began,source_sha256=sha(__file__))
 write(a.out,out);print('PLANNED '+str(len(points)))

def fine(a):
 if a.out.exists():raise ValueError('fresh output directory')
 a.out.mkdir(parents=True);plan_data=json.loads(a.plan.read_text());rng=np.random.default_rng(520328);began=time.monotonic();results=[]
 sources=[Path(__file__),*[ROOT/'tools/zipcaster_d3r'/name for name in['ideal_duel.py','native_kinematics.py','blade_field.py','sphere_cast.py']],*[ROOT/'tools/zipcaster_d3'/name for name in['calibrated_model.py','optimized_model.py','model.py','model_v2.py','budget.py','geometry.py','batch_geometry.py','paired_rays.py','search_v2.py']]];manifest={str(p.relative_to(ROOT)):sha(p)for p in sources};write(a.out/'source-manifest.json',manifest)
 for p in sources:
  q=a.out/'source-snapshot'/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes())
 for m in plan_data['maps']:
  if a.stage and a.stage!=m['stage']:continue
  atlas=MapAtlas.load(m['stage']);pts=np.asarray(atlas.points);mesh=BatchMesh(CollisionMesh.load(ROOT/f'work/arena/maps/{m["id"]}/sight.npz').triangles);field=BladeField(ROOT/f'work/arena/maps/{m["id"]}')
  for p in[p for p in plan_data['points']if p['map']==m['id']][:a.limit or None]:
   allids=np.array(m['reachable_ids']);near=allids[np.linalg.norm(pts[allids]-p['attach'],axis=1)<=30];sample=np.sort(rng.choice(near,min(a.enemy_nodes,len(near)),replace=False));ids=np.repeat(sample,16);heading=np.tile(np.repeat(np.arange(8)*math.pi/4,2),len(sample));forms=np.tile([False,True],len(sample)*8);weight=np.where(forms&~np.array(atlas.swimmable)[ids],0.,np.where(~forms&~np.array(atlas.swimmable)[ids],2.,1.));enemy=pts[ids]
   for speed,style in[(speed,style)for speed in a.speeds for style in(['light3']if speed==20 else['full-light','light3'])]:
    cfg=Config(arrival_setup=max(0,speed-21),full_reliability=1.,light_reliability=1.,style=style);path,start,budget=trajectory(p,speed,style)
    if path is None:continue
    probabilities=[];behaviors=[];tic=time.monotonic()
    for bi,mode in enumerate(['stand','strafe','retreat']):
     motion=graph_motion(atlas,ids,heading,mode,len(path),cfg,mesh=mesh,threat=p['source']);clear=np.zeros((len(path),len(ids)),bool);human=clear.copy();cache={}
     for t,pos in enumerate(path):
      eyes=motion[t]+np.c_[np.zeros(len(ids)),np.where(forms,.25,1.1),np.zeros(len(ids))];key=(tuple(pos),eyes.tobytes())
      if key not in cache:
       unique,inv=np.unique(eyes,axis=0,return_inverse=True);visible=np.zeros(len(unique),bool)
       for h in[.12,.7,1.3]:
        pending=np.flatnonzero(~visible)
        if len(pending):visible[pending]=mesh.clear_many(pos+[0,h,0],unique[pending])
       cache[key]=visible[inv]
      clear[t]=cache[key]
      # Forms become human once reaction/firing is active; exact same collision.
      human[t]=clear_pairs(mesh,np.broadcast_to(pos+[0,.7,0],enemy.shape),motion[t]+[0,1.1,0])
     r=duel_batch(path,start,enemy,heading,forms,clear,cfg=cfg,samples=a.samples,behavior=mode,seed=bi,move_clear=dict(positions=motion,clear=clear,clear_human=human),ballistic_clear=lambda x,y:clear_pairs(mesh,x,y),blade_clear=field.clear_pairs);probs=r['kills'].mean(axis=1);probabilities.append(probs);behaviors.append(dict(behavior=mode,local=float(np.average(probs,weights=weight)),episodes=int(r['kills'].size),kills=int(r['kills'].sum()),fired_or_seen=float((r['first_seen']>=0).mean())))
    pp=np.stack(probabilities);mass=len(near)/len(allids);expected=float(np.average(pp.mean(axis=0),weights=weight))*mass;worst=float(min(np.average(v,weights=weight)for v in pp))*mass
    row=dict(id=p['id'],map=p['map'],stage=p['stage'],speed=speed,style=style,expected=expected,worst=worst,local_expected=expected/mass,local_worst=worst/mass,near_prior_mass=mass,sampled_enemy_nodes=len(sample),reachable_enemy_nodes=len(allids),samples=a.samples,budget=budget,conditional_precharge_unverified=False,behaviors=behaviors,enemy_results=[dict(node=int(n),position=pts[n].tolist(),expected=float(np.average(pp[:,j*16:(j+1)*16].mean(axis=0),weights=weight[j*16:(j+1)*16])),worst=float(min(np.average(v[j*16:(j+1)*16],weights=weight[j*16:(j+1)*16])for v in pp)))for j,n in enumerate(sample)],seconds=time.monotonic()-tic)
    results.append(row);write(a.out/'partial.json',dict(results=results));print('IDEAL_FINE '+json.dumps({k:row[k]for k in['id','speed','expected','worst','seconds']}),flush=True)
 for p,h in manifest.items():assert sha(ROOT/p)==h,p
 write(a.out/'result.json',dict(schema='inklab.d3r.ideal.fine.v2',full_d3r_passed=False,rate_scope='ideal-operation upper bound conditional model',plan_sha256=sha(a.plan),results=results,seconds=time.monotonic()-began,source_sha256=manifest,config=asdict(Config()),limits=[x for x in plan_data['limits']if not x.startswith('20f')]+['20f full-light invalidated by native precharge control;20f evaluates light3 only. Other bands enumerate both programs. V2 corrects B6 native low-wall rise to~3.11u, light birth11f, and core field collisions.3/.5u. Vision remains thin collision rays.','Native pilot poses are training mechanisms; no formal native cohort outcome used.','Core static-sphere proxy omits side-sphere effects, curved late trajectory and dynamic collision; not full native weapon physics.']))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['plan','fine']);p.add_argument('--out',type=Path,required=True);p.add_argument('--plan',type=Path);p.add_argument('--stage',type=int);p.add_argument('--enemy-nodes',type=int,default=12);p.add_argument('--samples',type=int,default=16);p.add_argument('--limit',type=int,default=0);p.add_argument('--speeds',type=int,nargs='+',choices=[20,40,60,129],default=[20,40,60,129]);a=p.parse_args();(plan if a.mode=='plan'else fine)(a)
