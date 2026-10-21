"""Training-only ray fit + independent native bind/anchor validation.

Works only on CLOSED fixtures. Full per-cast geometry stays in ignored work/.
R1 fits pitch/origin/range from train; R2 adds declared orientation-bin rates.
No held-out outcome is used to choose parameters or range.
"""
import argparse,json,math,sys
from pathlib import Path
from collections import defaultdict
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha,angle
from tools.zipcaster.surfaces import load_surfaces,first_hit

def wrap(a):return np.arctan2(np.sin(a),np.cos(a))
def unit(yaw,vertical):
 vertical=float(np.clip(vertical,-.999999,.999999));horizontal=math.sqrt(1-vertical*vertical)
 return np.array([math.sin(yaw)*horizontal,vertical,math.cos(yaw)*horizontal])
def bases(r):
 y=r['command']['yaw'];b=r['body_heading']
 return np.array([[0,1,0],[math.sin(y),0,math.cos(y)],[math.cos(y),0,-math.sin(y)],[math.sin(b),0,math.cos(b)],[math.cos(b),0,-math.sin(b)]]).T
def collect():
 rows=[];open_rooms=[];runs=[]
 for p in sorted((ROOT/'work/a6').glob('d3-r-map-*/result.json')):
  d=json.loads(p.read_text())
  if 'freeze_after'not in d:open_rooms.append(str(p.relative_to(ROOT)));continue
  runs.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p),passed=d['passed'],errors=d['errors']))
  for source,h in d['raw_sha256'].items():assert sha(source)==h,source
  sensor=p.with_name('sensors.jsonl')
  if not sensor.exists():continue
  samples=[json.loads(l)for l in sensor.open()];job=d['mapping_job']
  for c in d['records']:
   if not c['eligible']:continue
   start=c['before_R']['player_0']['frame'];end=c['flight_end']['player_0']['frame'];ss=[s for s in samples if s['process']==0 and start<s['native_frame']<=end];tips=[s for s in ss if s['state_native']==1 and s['hook_tip_world']is not None];vectors=[]
   for a,b in zip(tips,tips[1:]):
    v=np.asarray(b['hook_tip_world'])-a['hook_tip_world']
    if b['native_frame']>a['native_frame']and np.linalg.norm(v)>.01:vectors.append(v/np.linalg.norm(v))
   direction=np.mean(vectors,axis=0)if vectors else None
   if direction is not None:direction/=np.linalg.norm(direction)
   bound=next((s for s in ss if s['bind_witness']and s['state_native']in(2,3)),None);before=c['before_R']['player_0'];native_bind=bound is not None or any(s in(2,3)for _,s in c['phases'])
   rows.append(dict(map=job['map'],stage=job['stage'],batch=job['batch'],index=c['index'],id=c['proposal']['id'],split=c['proposal']['split'],kind=c['proposal']['kind'],source_region=job['source_region'],source=before['position'],source_frame=start,body_heading=before['heading'],command=c['command'],native_bind=bool(native_bind),anchor=bound['anchor_world']if bound else None,normal=bound['hit_normal_world']if bound else None,tip_direction=direction.tolist()if direction is not None else None,tip_line_point=tips[0]['hook_tip_world']if tips else None,tip_count=len(tips),arrival=c.get('arrival_settled_ack',c.get('arrival_first_ack',{})).get('player_0'),flight_end=c['flight_end']['player_0'],artifact=str(p.relative_to(ROOT)),raw_sha256=sha(p),sensor_sha256=sha(sensor)))
 return rows,runs,open_rooms

def fit(rows):
 rs=[r for r in rows if r['split']=='train'and r['tip_direction']is not None]
 if len(rs)<6:raise ValueError('at least6 training rays required')
 x=np.array([[r['command']['native_pitch'],1.]for r in rs]);y=np.array([r['tip_direction'][1]for r in rs]);pitch=np.linalg.lstsq(x,y,rcond=None)[0]
 bias=float(np.angle(np.mean([np.exp(1j*(math.atan2(r['tip_direction'][0],r['tip_direction'][2])-r['command']['yaw']))for r in rs])))
 a=[];b=[]
 for r in rs:
  v=np.asarray(r['tip_direction']);projection=np.eye(3)-v[:,None]*v[None,:];a.extend(projection@bases(r));b.extend(projection@(np.asarray(r['tip_line_point'])-r['source']))
 a=np.asarray(a);b=np.asarray(b);prior=np.array([1.1,0,0,0,0]);origin=np.linalg.solve(a.T@a+.05*np.eye(5),a.T@b+.05*prior);origin=np.clip(origin,[-0.,-3,-3,-3,-3],[3,3,3,3,3]);return dict(pitch_scale=float(pitch[0]),pitch_bias=float(pitch[1]),yaw_bias=bias,origin_coefficients=origin.tolist(),training_tip_rays=len(rs),origin_ridge=.05)

def geometry():
 out={}
 for name in ['Yunohana','District00','Yagara']:
  tri,normal,area,attr=load_surfaces(ROOT/f'work/arena/maps/{name}');keep=np.array(['SplPlayerSuperHookCheck'not in a['col_disable_flags']for a in attr]);out[name]=(tri[keep],normal[keep],[a for a,k in zip(attr,keep)if k])
 return out

def prediction(r,par,geo):
 origin=np.asarray(r['source'])+bases(r)@par['origin_coefficients'];vertical=math.sin(r['command']['native_pitch'])if par.get('pitch_mode')=='angle'else par['pitch_scale']*r['command']['native_pitch']+par['pitch_bias'];direction=unit(r['command']['yaw']+par['yaw_bias'],vertical);tri,norm,attrs=geo[r['map']];hit=first_hit(tri,origin,origin+direction*45)
 out=dict(direction=direction.tolist(),origin=origin.tolist(),distance=None,point=None,eligible=False,group='no-hit')
 if hit is not None:
  i,p,_=hit;flags=attrs[i]['mat_flags'];ny=abs(norm[i][1]);group='horizontal'if ny>.7 else'wall'if ny<.3 else'slant';eligible='SuperHookCantBind'not in flags
  out.update(distance=float(np.linalg.norm(p-origin)),point=p.tolist(),eligible=eligible,group=group,material_flags=flags,normal=norm[i].tolist())
 if r['anchor']is not None and out['point']is not None:out['anchor_error']=float(np.linalg.norm(np.asarray(out['point'])-r['anchor']))
 if r['tip_direction']is not None:out['direction_error_degrees']=angle(direction,r['tip_direction'])
 return out

def metrics(rows,field):
 if not rows:return dict(n=0)
 p=np.array([r[field]for r in rows]);y=np.array([r['native_bind']for r in rows]);pred=p>=.5
 return dict(n=len(rows),native_bind_rate=float(y.mean()),mean_predicted=float(p.mean()),accuracy=float((pred==y).mean()),brier=float(((p-y)**2).mean()),mae=float(abs(p-y).mean()),tp=int((pred&y).sum()),fp=int((pred&~y).sum()),tn=int((~pred&~y).sum()),fn=int((~pred&y).sum()))
def main(a):
 if a.out.exists():raise ValueError('fresh output path required')
 rows,runs,open_rooms=collect();par=fit(rows);geo=geometry();base=dict(pitch_mode='angle',pitch_scale=1.,pitch_bias=0.,yaw_bias=0.,origin_coefficients=[1.1,0,0,0,0]);train=[r for r in rows if r['split']=='train']
 for r in rows:
  r['baseline_ray']=prediction(r,base,geo);r['corrected_ray']=prediction(r,par,geo);r['p_baseline']=float(r['baseline_ray']['eligible']and r['baseline_ray']['distance']<=35)
 def probability(r,limit):g=r['corrected_ray'];return float(g['eligible']and g['distance']<=limit)
 choices=np.linspace(30,40,101);limit=min(choices,key=lambda length:(sum((probability(r,length)-r['native_bind'])**2 for r in train),abs(length-35)))
 par['effective_range']=float(limit);counts=defaultdict(lambda:[0,0])
 for r in train:
  g=r['corrected_ray']
  if probability(r,limit):counts[g['group']][0]+=int(r['native_bind']);counts[g['group']][1]+=1
 rates={k:(s+1)/(n+2)for k,(s,n)in counts.items()};par['training_orientation_rates']=dict(rates);par['training_orientation_counts']=dict(counts)
 for r in rows:r['p_geometry']=probability(r,limit);r['p_orientation']=r['p_geometry']*rates.get(r['corrected_ray']['group'],1.)
 def spatial(rs,key):
  e=[r[key]['anchor_error']for r in rs if r['native_bind']and'anchor_error'in r[key]];d=[r[key]['direction_error_degrees']for r in rs if'direction_error_degrees'in r[key]]
  return dict(anchor_n=len(e),anchor_median=float(np.median(e))if e else None,anchor_p90=float(np.quantile(e,.9))if e else None,anchor_max=max(e)if e else None,direction_n=len(d),direction_median_degrees=float(np.median(d))if d else None,direction_p90_degrees=float(np.quantile(d,.9))if d else None)
 result=dict(schema='inklab.d3r.mapping.fit.v1',full_d3r_passed=False,parameters=par,runs=runs,open_rooms_excluded=open_rooms,native_casts=len(rows),train_casts=len(train),held_out_casts=sum(r['split']=='held-out'for r in rows),metrics={split:{key:metrics([r for r in rows if split=='all'or r['split']==split],key)for key in ['p_baseline','p_geometry','p_orientation']}for split in ['train','held-out','all']},spatial={split:{key:spatial([r for r in rows if split=='all'or r['split']==split],key)for key in ['baseline_ray','corrected_ray']}for split in ['train','held-out','all']},per_map={m:{key:metrics([r for r in rows if r['map']==m and r['split']=='held-out'],key)for key in ['p_baseline','p_geometry','p_orientation']}for m in ['Yunohana','District00','Yagara']},rows=rows,limits=['Only closed eligible casts, original setup/runtime failures retained separately.','Global pitch sinusoid coefficient and effective origin are surrogates fitted only on training rays. They are not recovered native component fields.','Range chosen on train30..40u;45u geometry query. CantBind blocks but cannot bind, HookCheck-disabled triangles omitted.','R2 orientation bins have Beta(1,1) training means; no held-out outcome used to fit.','Static geometry may omit dynamic collision; near/short casts can lack a sampled tip ray.','Native arrival/landing measured; no guarantee of subsequent sword hits or ranking.'],source_sha256={str(p.relative_to(ROOT)):sha(p)for p in [Path(__file__),ROOT/'tools/zipcaster/surfaces.py',ROOT/'tools/stage_collision.py']})
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:result[k]for k in ['native_casts','held_out_casts','parameters','metrics','spatial']},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args())
