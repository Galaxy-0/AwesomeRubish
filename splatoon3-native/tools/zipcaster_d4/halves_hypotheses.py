"""Reclassify closed per-slash tables with outward half clipping, no rooms."""
import argparse,json,math
from pathlib import Path
import numpy as np
from tools.zipcaster_d4.blade_halves import first_hit
from tools.zipcaster_d3r.analyze_direction import sha

def evaluate_stage(stage,core):
 r=stage['independent_sides'];events=r['side_events']
 if not events:return None
 body=np.array([e['body_time']if e['body_time']is not None else np.inf for e in events]);field=np.array([e['field_time']if e['field_time']is not None else np.inf for e in events])
 out=first_hit(body,field,core);alternative=first_hit(body,field,core,'positive')
 survived=[i for i in range(len(body))if body[i]<out['stops'][i]-1e-7]
 return dict(stage=stage['stage'],legacy_independent_hit=r['hit'],outward_hit=bool(out['hit']),
  outward_ball=int(out['damage_sphere'])if out['hit']else None,
  centre_positive_alternative_hit=bool(alternative['hit']),
  surviving_target_balls=survived,
  invalidated_target_balls=[i for i in range(len(body))if math.isfinite(body[i])and i not in survived],
  blocked_opposite_half=bool(out['hit']and any(math.isfinite(field[j])and (j-core)*(int(out['damage_sphere'])-core)<0 for j in range(len(body)))),
  balls=[dict(index=i,half='centre'if i==core else'left/upper'if i<core else'right/lower',
   body_time=None if not math.isfinite(body[i])else float(body[i]),field_time=None if not math.isfinite(field[i])else float(field[i]),
   outward_stop=None if not math.isfinite(out['stops'][i])else float(out['stops'][i]))for i in range(len(body))])

def main(a):
 runs={};inputs={}
 for p in a.tables:
  inputs[str(p)]=sha(p)
  for r in json.loads(p.read_text())['runs']:runs[r['artifact']]=r
 rows=[]
 for run in runs.values():
  for shot in run['shots']:
   if shot.get('no_birth'):continue
   stages=[evaluate_stage(s,3 if shot['style']=='full'else 2)for s in shot['stages']];stages=[s for s in stages if s]
   rows.append(dict(artifact=run['artifact'],index=shot['index'],style=shot['style'],native_hp_edges=shot['native_large_hp_edges'],
    stages=stages,contact_not_inferred=True))
 out=dict(schema='inklab.d4.blade.halves.hypotheses.v1',rows=rows,new_native_shots=0,
  summary=dict(slashes=len(rows),light=sum(r['style']=='light'for r in rows),full=sum(r['style']=='full'for r in rows),
   changed_stages=sum(s['legacy_independent_hit']!=s['outward_hit']for r in rows for s in r['stages']),
   surviving_opposite_half_stages=sum(s['blocked_opposite_half']for r in rows for s in r['stages'])),
  input_sha256=inputs,source_sha256={str(p):sha(p)for p in [Path(__file__),Path(__file__).with_name('blade_halves.py')]},
  limits=['Geometric per-ball reclassification, not native ball-lifetime readback.',
   '140/20 contact body is separately registered and is not made into halves by this calculation.',
   'Observed projectile prefixes can be right-censored. HP timing/ownership must be examined before calling a geometric hit a native damage prediction.'])
 assert not a.out.exists();a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out['summary']))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--tables',type=Path,nargs='+',required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
