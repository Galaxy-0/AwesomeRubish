"""Train a finite sphere-sweep/material surrogate; future batches3/4 untouched.

Fitting cap: batches0..2 only. Every frozen candidate setting is disclosed.
No assumption that a fitted radius is the native physical collider radius.
"""
import argparse,json,math,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r import fit_mapping as f
from tools.zipcaster_d3r.ray_model import direction
from tools.zipcaster_d3r.sphere_cast import first_sphere_hit
from tools.zipcaster_d3r.analyze_direction import sha

def geometry(skip_fence):
 from tools.zipcaster.surfaces import load_surfaces
 out={}
 for name in['Yunohana','District00','Yagara']:
  tri,norm,area,attrs=load_surfaces(ROOT/f'work/arena/maps/{name}');keep=np.array(['SplPlayerSuperHookCheck'not in a['col_disable_flags']and(not skip_fence or'Fence'not in a['mat_flags'])for a in attrs]);out[name]=(tri[keep],norm[keep],[a for a,k in zip(attrs,keep)if k])
 return out

def prediction(r,par,geo,radius,minimum):
 origin=np.asarray(r['source'])+f.bases(r)@par['origin_coefficients'];v=direction(r['command']['yaw'],r['command']['native_pitch'],par);tri,norm,attrs=geo[r['map']];hit=first_sphere_hit(tri,origin,v,radius,par['effective_range']);out=dict(eligible=False,point=None,distance=None)
 if hit is not None:
  i,p,d=hit;out.update(eligible=bool('SuperHookCantBind'not in attrs[i]['mat_flags']and d>=minimum),point=p.tolist(),distance=d,normal=norm[i].tolist(),material_flags=attrs[i]['mat_flags'])
 if r['anchor']is not None and out['point']is not None:out['anchor_error']=float(np.linalg.norm(np.asarray(out['point'])-r['anchor']))
 return out

def main(a):
 if a.out.exists():raise ValueError('fresh path required')
 rows,runs,opened=f.collect();prior=json.loads(a.ray.read_text());par=prior['parameters'];began=time.time()
 if a.mode=='fit':
  # Fit only predeclared per-cast train rows in development batches0..2.
  train=[r for r in rows if r['batch']<3 and r['split']=='train'];candidates=[]
  for skip in[False,True]:
   geo=geometry(skip)
   for radius in[0.,.1,.2,.3,.4,.5,.75]:
    predictions=[prediction(r,par,geo,radius,0.)for r in train]
    for minimum in[0.,1.,2.,3.,4.]:
     binary=np.mean([(float(p['eligible']and p['distance']>=minimum)-r['native_bind'])**2 for r,p in zip(train,predictions)]);spatial=[min(3.,p.get('anchor_error',3.))for r,p in zip(train,predictions)if r['native_bind']];loss=float(2*binary+np.mean(spatial)/3)
     candidates.append(dict(skip_fence=skip,radius=radius,minimum_distance=minimum,loss=loss,binary_brier=float(binary),capped_anchor_mean=float(np.mean(spatial)),training_casts=len(train)))
    print('SWEEP_FIT '+str(skip)+' '+str(radius),flush=True)
  best=min(candidates,key=lambda c:(c['loss'],c['radius'],c['minimum_distance']));result=dict(schema='inklab.d3r.sweep.frozen.v1',best=best,candidates=candidates,ray_parameters=par,ray_sha256=sha(a.ray),development_batches=[0,1,2],confirmatory_batches=[3,4],fit_row_keys=[[r['map'],r['batch'],r['index']]for r in train],fit_started_unix=began,frozen_unix=time.time(),source_sha256={str(p.relative_to(ROOT)):sha(p)for p in[Path(__file__),ROOT/'tools/zipcaster_d3r/sphere_cast.py']},limits=['Surrogate radius/minimum are fitted geometry parameters, not native collider measurements.','Fence pass-through is a fitted material hypothesis; CantBind remains a blocker.','Model choice uses development batches0..2 only. Final two batches are confirmatory and never refit.','First-contact collision and native static geometry are approximations; dynamic surfaces not included.'])
 else:
  frozen=json.loads(a.parameters.read_text());par=frozen['ray_parameters'];best=frozen['best'];geo=geometry(best['skip_fence'])
  for r in rows:r['sweep']=prediction(r,par,geo,best['radius'],best['minimum_distance']);r['p_sweep']=float(r['sweep']['eligible'])
  def metrics(rs):
   e=[r['sweep']['anchor_error']for r in rs if r['native_bind']and'anchor_error'in r['sweep']]
   return dict(**f.metrics(rs,'p_sweep'),anchor_n=len(e),anchor_median=float(np.median(e))if e else None,anchor_p90=float(np.quantile(e,.9))if e else None,anchor_max=max(e)if e else None)
  result=dict(schema='inklab.d3r.sweep.confirmatory.v1',full_d3r_passed=False,parameters_sha256=sha(a.parameters),metrics={split:metrics([r for r in rows if split=='all'or(split=='development'and r['batch']<3)or(split=='confirmatory'and r['batch']>=3)])for split in['development','confirmatory','all']},per_map={m:metrics([r for r in rows if r['batch']>=3 and r['map']==m])for m in['Yunohana','District00','Yagara']},rows=rows,runs=runs,open_rooms_excluded=opened)
 a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result.get('best',result.get('metrics')),indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['fit','evaluate']);p.add_argument('--ray',type=Path,default=ROOT/'work/d3r/ray-v2-frozen.json');p.add_argument('--parameters',type=Path);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
