"""Pre-outcome control targets with both projectile corridors clear.

Setup uses conservative margins; not target prior selection for calibration.
Native sword core field radii light.3/full.5 differ from thin vision rays.
"""
import argparse,json,sys,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'tools/zipcaster_d3'),str(ROOT)]
from geometry import reachable
from arena.lib.atlas import MapAtlas
from tools.zipcaster_d3r.sphere_cast import first_sphere_hit
from tools.zipcaster.surfaces import load_surfaces

def main(a):
 if a.out.exists():raise ValueError('fresh target plan')
 plan=json.loads(a.plan.read_text())
 for p in plan['points']:
  atlas=MapAtlas.load(p['stage']);pts=np.array(atlas.points);reach=set(reachable(atlas,[atlas.spawns['bravo']['ground']]).tolist());tri,norm,area,attrs=load_surfaces(ROOT/f'work/arena/maps/{p["map"]}');keep=['Fence'not in x['mat_flags']for x in attrs];tri=tri[keep];attach=np.array(p['attach']);floor=p['landing'][1]
  eligible=[n for n in reach if 7<=np.linalg.norm(pts[n]-attach)<=14 and np.linalg.norm(pts[n]-p['source'])>=9 and abs(pts[n,1]-floor)<3];pool=sorted(eligible,key=lambda n:abs(np.linalg.norm(pts[n]-attach)-10));chosen=None
  for n in pool:
   target=pts[n]+[0,1.1,0];safe=True
   for height,forward,radius in[(1.,1.4,.5),(2.5+2.2,.8,.6)]:
    foot=np.array([attach[0],floor,attach[2]]);delta=target-foot;u=delta.copy();u[1]=0;u/=np.linalg.norm(u);origin=foot+[0,height,0]+u*forward;d=target-origin;length=np.linalg.norm(d)
    if first_sphere_hit(tri,origin,d,radius,max(.01,length-.6))is not None:safe=False;break
   if safe:chosen=n;break
  if chosen is None:raise ValueError('no reachable clear-corridor target '+p['id'])
  p.update(target=pts[chosen].tolist(),control_target_node=int(chosen),control_target_selection='pre-outcome geometry-only reachable beta target7..14u,>=9u from source; light/full corridor margins.5/.6u; separate from calibration prior');print(p['id'],p['target'])
 a.out.write_text(json.dumps(plan,separators=(',',':'))+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
