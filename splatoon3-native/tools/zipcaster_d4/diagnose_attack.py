"""Read-only native miss attribution; core vs whole multi-sphere projectile.

Alternative collision assembly is a hypothesis. Do not change the accepted
physics or certify a route from this diagnostic alone. All cases remain data.
"""
import argparse,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d4.model_v2 import World,segment_distance
from tools.zipcaster_d3r.analyze_direction import PAT,sha

def diagnose(path,world):
 d=json.loads(path.read_text());start=next(e['infos']['player_0']['frame']for e in d['events']if e['event']=='before-RS');steps=[json.loads(l)for l in path.with_name('steps.jsonl').open()];rows=[]
 for e in d['events']:
  kind={'full-release':'full','light-input':'light'}.get(e['event'])
  if kind is None:continue
  f=e['infos']['player_0']['frame'];vt='5c76df0'if kind=='full'else'5c75510';samples=[]
  for l in(Path(d['session'])/'player-0/host.log').open():
   m=PAT.search(l)
   if m and m[4]==vt and f<=int(m[1])<=f+40:samples.append(dict(frame=int(m[1]),kind=m[2],object=m[3],velocity=list(map(float,m[5].split(','))),position=list(map(float,m[6].split(',')))))
  birth=next((s for s in samples if s['kind']=='setter_input'and math.dist(s['velocity'],[0,0,0])>(1. if kind=='full' else 3.)),None)
  if birth is None:rows.append(dict(style=kind,no_birth=True));continue
  same=[s for s in samples if s['object']==birth['object']and s['frame']>=birth['frame']];pose=min(steps,key=lambda s:abs(s['infos']['player_0']['frame']-birth['frame']));q=np.array(pose['infos']['player_1']['position']);origin=np.array(birth['position']);direction=np.array(birth['velocity']);direction/=np.linalg.norm(direction);yaw=math.atan2(direction[0],direction[2]);el=math.asin(direction[1]);right=np.array([math.cos(yaw),0,-math.sin(yaw)]);up=np.cross(direction,right)
  params=json.loads((ROOT/'work/a6/parameters.json').read_text())[('vertical'if kind=='full'else'horizontal')+'_projectile']['CollisionParam'];hits=[]
  for index,(offset,r)in enumerate(zip(params['OffsetArray'],params['ParamArray'])):
   o=origin+right*offset['X']+up*offset['Y']+direction*offset['Z'];radius=r['InitRadiusForField'];ids,p,dist=world.field.sphere(o,direction,radius,25.)
   hits.append(dict(index=index,core=index==params['CoreIndex'],radius=radius,hit=int(ids[0]),distance=float(dist[0])if ids[0]>=0 else None,projectile_root_contact=(p[0]-(o-origin)).tolist()if ids[0]>=0 else None))
  valid=[h for h in hits if h['distance']is not None];first=min(valid,key=lambda h:h['distance'])if valid else None;last=next((s for s in same if np.linalg.norm(s['velocity'])<1e-8),same[-1]);rows.append(dict(style=kind,input=f-start,birth=birth,last_observed=last,enemy_at_birth=q.tolist(),core_ray_capsule_axis_distance=segment_distance(origin,origin+direction*25,q+[0,.35,0],q+[0,1.3,0]),field_spheres=hits,earliest_sphere=first,nearest_assembly_root_to_last=None if first is None else float(np.linalg.norm(np.asarray(first['projectile_root_contact'])-last['position']))))
 return dict(artifact=str(path.relative_to(ROOT)),sha256=sha(path),shots=rows,raw_sha256=d['raw_sha256'])
def main(a):
 if a.out.exists():raise ValueError('fresh diagnosis output')
 batch=json.loads(a.batch.read_text());worlds={};rows=[]
 for item in batch['results']:
  path=ROOT/item['artifact'];d=json.loads(path.read_text())
  if d['point']['band']=='control':continue
  graph=d['point']['graph']
  if graph not in worlds:worlds[graph]=World(ROOT/graph)
  rows.append(diagnose(path,worlds[graph]))
 out=dict(schema='inklab.d4.attack.diagnosis.v1',cases=rows,source_sha256=sha(__file__),scope='Native birth vectors/positions, unchanged field geometry and parameter sphere assembly; rigid assembly and lifetime are hypotheses, not yet native parity. No model ranking correction or tuning on held-out tests. Near contact140/20 remains a separate volume requiring verification.')
 a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps([dict(artifact=r['artifact'],shots=[dict(style=s['style'],core_miss=s.get('core_ray_capsule_axis_distance'),sphere=s.get('earliest_sphere',{}).get('index')if s.get('earliest_sphere')else None,root_error=s.get('nearest_assembly_root_to_last'))for s in r['shots']])for r in rows],indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
