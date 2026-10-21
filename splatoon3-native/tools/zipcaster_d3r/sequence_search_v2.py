"""Finite budgeted measured-wall graph; bounded beam, not global optimum.

<=35u edges use the frozen hook-origin/tangent/sphere model, reject intervening
surfaces. Intermediate B6/ideal preaim is an explicit unvalidated link model.
No R-in-flight native action is executed by this offline script.
"""
import argparse,json,sys,math,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'tools/zipcaster_d3'),str(ROOT)]
from tools.zipcaster_d3r.analyze_direction import sha
from tools.zipcaster_d3r.aim_solver import hook_angles
from tools.zipcaster_d3r.ray_model import direction
from tools.zipcaster_d3r.sphere_cast import first_sphere_hit
from tools.zipcaster_d3r.native_kinematics import JUMP_T,JUMP_Y
from tools.zipcaster_d3r.sweep_fit import geometry
from budget import Gauge

def edge(a,b,geo,parameters):
 start=np.array(a['attach'])+[0,float(np.interp(6,JUMP_T,JUMP_Y)),0];anchor=np.array(b['anchor']);distance=np.linalg.norm(anchor-start-[0,1.1,0])
 if not 2<distance<=35:return None
 yaw,pitch=hook_angles(start,0,anchor,parameters)
 if abs(pitch)>.85:return None
 from tools.zipcaster_d3r.fit_mapping import bases
 origin=start+bases(dict(command=dict(yaw=yaw),body_heading=0))@parameters['origin_coefficients'];u=direction(yaw,pitch,parameters);tri,norm,attrs=geo;lo=np.minimum(origin,origin+u*35)-.40001;hi=np.maximum(origin,origin+u*35)+.40001;ids=np.flatnonzero(((tri.min(axis=1)<=hi)&(tri.max(axis=1)>=lo)).all(axis=1));h=first_sphere_hit(tri[ids],origin,u,.4,35)if len(ids)else None
 if h is None:return None
 i,hit,length=h;i=ids[i]
 if np.linalg.norm(hit-anchor)>.8 or'SuperHookCantBind'in attrs[i]['mat_flags']or'KeepOut'in attrs[i]['mat_flags']or abs(norm[i,1])>.5:return None
 wait=math.ceil(distance/3.36)+12;path=[start.copy()for _ in range(wait)];end=np.array(b['attach']);delta=end-start;total=np.linalg.norm(delta);travel=0.;speed=.06
 while travel<total:
  speed=min(65/60,speed+.1);travel=min(total,travel+speed);path.append(start+delta*travel/max(1e-9,total))
 return dict(path=np.array(path),frames=6+len(path),predicted_anchor=hit.tolist(),request_error=float(np.linalg.norm(hit-anchor)))

def main(a):
 if a.out.exists():raise ValueError('fresh sequence plan')
 source=json.loads(a.plan.read_text());parameters=json.loads(a.ray.read_text())['parameters'];geo=geometry(True);newmaps=[];points=[];began=time.monotonic();counts={}
 for m in source['maps']:
  nodes=[]
  for p in m['candidates']:
   if not any(np.linalg.norm(np.array(p['anchor'])-n['anchor'])<1.5 for n in nodes):nodes.append(p)
  links={}
  for i,p in enumerate(nodes):
   for j,q in enumerate(nodes):
    if i==j:continue
    try:r=edge(p,q,geo[m['id']],parameters)
    except ValueError:r=None
    if r:links[i,j]=r
  candidates=[];expanded=0;budget_rejected=0
  for first in[p for p in source['points']if p['map']==m['id']]:
   index=min(range(len(nodes)),key=lambda i:np.linalg.norm(np.array(nodes[i]['anchor'])-first['anchor']));beam=[dict(sequence=[index],path=np.array(first['native_flight']),score=first['heuristic_score'],events=[dict(frame=0,event='出钩1')])]
   for depth in range(2,a.depth+1):
    nexts=[]
    for state in beam:
     i=state['sequence'][-1]
     for j in range(len(nodes)):
      if j in state['sequence']or(i,j)not in links:continue
      old=state['path'];link=edge(dict(nodes[i],attach=old[-1].tolist()),nodes[j],geo[m['id']],parameters)
      if link is None:continue
      attach=old[-1];jump=np.array([attach+[0,float(np.interp(t,JUMP_T,JUMP_Y)),0]for t in range(1,7)]);path=np.concatenate([old,jump,link['path']]);required=Gauge().cost(len(path)-1+20+71,hooks=depth,lights=3,fulls=0);expanded+=1
      if required>=.96:budget_rejected+=1;continue
      score=nodes[j]['heuristic_score']-.0001*len(path);events=state['events']+[dict(frame=len(old)-1,event='到达 / B跳离'+str(depth-1)),dict(frame=len(old)+5,event='出钩'+str(depth))];row=dict(sequence=state['sequence']+[j],path=path,score=score,events=events);nexts.append(row)
      q=nodes[j];candidates.append(first|dict(id=first['id']+'-chain-'+'-'.join(str(k)for k in row['sequence']),sequence=[first['id']]+[nodes[k]['id']for k in row['sequence'][1:]],sequence_anchors=[first['anchor']]+[nodes[k]['anchor']for k in row['sequence'][1:]],anchor=q['anchor'],attach=q['attach'],landing=q['landing'],native_flight=path.tolist(),chain_events=events,heuristic_score=score,sequence_link_model='measured first flight; subsequent B6/65u-s acceleration/ray binding predicted, not native certified',required_conservative=required))
    beam=sorted(nexts,key=lambda r:-r['score'])[:a.beam]
  chosen=[]
  for p in sorted(candidates,key=lambda p:-p['heuristic_score']):
   if any(np.linalg.norm(np.array(p['anchor'])-q['anchor'])<3 for q in chosen):continue
   chosen.append(p)
   if len(chosen)==a.per_map:break
  points.extend(chosen);newmaps.append(m);counts[m['id']]=dict(nodes=len(nodes),edges=len(links),states_expanded=expanded,budget_pruned=budget_rejected,fine_sequences=len(chosen));print('CHAIN_GRAPH '+json.dumps(counts[m['id']]),flush=True)
 out=dict(schema='inklab.d3r.sequence.plan.v2',full_d3r_passed=False,points=points,maps=newmaps,counts=counts,depth=a.depth,beam=a.beam,seconds=time.monotonic()-began,source_sha256={str(p.relative_to(ROOT)):sha(p)for p in[Path(__file__),a.plan,a.ray]},limits=source['limits']+['Finite measured-wall graph depth<=3, beam pruning and heuristic preselection, not exhaustive/global optimum.','Only first flight is native measured for this source. Subsequent B6/direct-aim rehook links are predicted and require native control.','Graph prunes only paths unable to fund20f light3; fine rechecks exact program/time/hook count.','Chain native kill ranking is not calibrated by the single-hook54-case cohort.'])
 a.out.write_text(json.dumps(out,separators=(',',':'))+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,default=ROOT/'work/d3r/ideal-plan-v1.json');p.add_argument('--ray',type=Path,default=ROOT/'work/d3r/ray-v2-frozen.json');p.add_argument('--out',type=Path,required=True);p.add_argument('--depth',type=int,choices=[2,3],default=3);p.add_argument('--beam',type=int,default=6);p.add_argument('--per-map',type=int,default=3);main(p.parse_args())
