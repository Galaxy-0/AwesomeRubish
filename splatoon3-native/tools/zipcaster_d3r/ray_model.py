"""Frozen R2 camera-tangent ray surrogate; no native game fields inferred.

Developed on batches0/1; batches2..4 are untouched confirmatory collection.
Parameter file is written once before those rooms close. No refit in evaluate.
"""
import argparse,json,math,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r import fit_mapping as f
from tools.zipcaster_d3r.analyze_direction import sha

def direction(yaw,pitch,parameters):
 elev=math.atan(parameters['tangent_scale']*math.tan(pitch)+parameters['tangent_bias'])
 return f.unit(yaw+parameters['yaw_bias'],math.sin(elev))
def inverse_pitch(elevation,parameters):
 return math.atan((math.tan(elevation)-parameters['tangent_bias'])/parameters['tangent_scale'])
def predict(row,parameters,geo):
 v=direction(row['command']['yaw'],row['command']['native_pitch'],parameters)
 # Reuse only geometry/origin logic; override native pitch with physical sine.
 proxy=dict(row,command=dict(row['command'],native_pitch=float(v[1]),yaw=math.atan2(v[0],v[2])))
 # bases() must retain original camera axes for the fitted effective origin.
 origin=np.asarray(row['source'])+f.bases(row)@parameters['origin_coefficients']
 from tools.zipcaster.surfaces import first_hit
 tri,norm,attrs=geo[row['map']];hit=first_hit(tri,origin,origin+v*45);result=dict(origin=origin.tolist(),direction=v.tolist(),eligible=False,distance=None,point=None)
 if hit is not None:
  i,p,_=hit;distance=float(np.linalg.norm(p-origin));result.update(point=p.tolist(),distance=distance,eligible='SuperHookCantBind'not in attrs[i]['mat_flags']and distance<=parameters['effective_range'],normal=norm[i].tolist(),material_flags=attrs[i]['mat_flags'])
 if row['tip_direction']is not None:result['direction_error_degrees']=f.angle(v,row['tip_direction'])
 if row['anchor']is not None and result['point']is not None:result['anchor_error']=float(np.linalg.norm(np.asarray(result['point'])-row['anchor']))
 return result

def freeze(a):
 if a.out.exists():raise ValueError('fresh immutable path required')
 snapshot=json.loads(a.snapshot.read_text());rows=snapshot['rows'];assert all(r['batch']<2 for r in rows)
 rays=[r for r in rows if r['split']=='train'and r['tip_direction']is not None]
 x=np.array([[math.tan(r['command']['native_pitch']),1]for r in rays]);y=np.array([r['tip_direction'][1]/np.linalg.norm(np.asarray(r['tip_direction'])[[0,2]])for r in rays]);coef=np.linalg.lstsq(x,y,rcond=None)[0]
 par=f.fit(rows);par.update(tangent_scale=float(coef[0]),tangent_bias=float(coef[1]),effective_range=35.,model='atan(scale*tan(native_pitch)+bias)',fit_batches=[0,1],confirmatory_batches=[2,3,4],development_held_out_exploratory=True)
 # Freeze range35 from independent D2 measurement, not from confirmatory data.
 out=dict(schema='inklab.d3r.ray.frozen.v2',parameters=par,snapshot=str(a.snapshot),snapshot_sha256=sha(a.snapshot),frozen_unix=time.time(),sources={str(p.relative_to(ROOT)):sha(p)for p in[Path(__file__),Path(f.__file__)]},limits=['Effective origin/pitch surrogate, not native fields.','Model form selected during development batches0/1; their held-out diagnostics are exploratory.','No batch2/3/4 outcome used in fit or model choice. Confirmatory evaluation never refits.'])
 a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
def evaluate(a):
 if a.out.exists():raise ValueError('fresh output path required')
 frozen=json.loads(a.parameters.read_text());par=frozen['parameters'];rows,runs,opened=f.collect();geo=f.geometry()
 for r in rows:r['ray_v2']=predict(r,par,geo);r['p_v2']=float(r['ray_v2']['eligible'])
 def stats(rs):
  errors=[r['ray_v2']['anchor_error']for r in rs if r['native_bind']and'anchor_error'in r['ray_v2']];angles=[r['ray_v2']['direction_error_degrees']for r in rs if'direction_error_degrees'in r['ray_v2']]
  return dict(**f.metrics(rs,'p_v2'),anchor_n=len(errors),anchor_median=float(np.median(errors))if errors else None,anchor_p90=float(np.quantile(errors,.9))if errors else None,anchor_max=max(errors)if errors else None,direction_n=len(angles),direction_median_degrees=float(np.median(angles))if angles else None,direction_p90_degrees=float(np.quantile(angles,.9))if angles else None)
 out=dict(schema='inklab.d3r.mapping.confirmatory.v2',full_d3r_passed=False,parameters_sha256=sha(a.parameters),parameters=par,runs=runs,open_rooms_excluded=opened,metrics={part:stats([r for r in rows if(part=='development'and r['batch']<2)or(part=='confirmatory'and r['batch']>=2)or(part=='all')])for part in['development','confirmatory','all']},per_map={m:stats([r for r in rows if r['map']==m and r['batch']>=2])for m in['Yunohana','District00','Yagara']},rows=rows,source_sha256=sha(__file__))
 a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out['metrics'],indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','evaluate']);p.add_argument('--snapshot',type=Path);p.add_argument('--parameters',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();(freeze if a.mode=='freeze'else evaluate)(a)
