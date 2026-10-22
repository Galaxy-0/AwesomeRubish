"""Compare the accelerator to original predicates, including native witnesses."""
import json,sys,time,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d4.geometry import Mesh
from tools.zipcaster_d3r.sphere_cast import first_sphere_hit
from arena.geometry import CollisionMesh
from tools.zipcaster.surfaces import load_surfaces

def main():
 rng=np.random.default_rng(41022);results=[];began=time.monotonic()
 for name in ['Yunohana','District00','Yagara']:
  original=CollisionMesh.load(ROOT/f'work/arena/maps/{name}/sight.npz');accelerated=Mesh(original.triangles);lo=original.triangles.min(axis=(0,1));hi=original.triangles.max(axis=(0,1));starts=rng.uniform(lo,hi,(1000,3));ends=starts+rng.uniform(-35,35,(1000,3));expected=np.array([original.clear(a,b)for a,b in zip(starts,ends)]);actual=accelerated.clear_pairs(starts,ends);assert np.array_equal(actual,expected),(name,np.flatnonzero(actual!=expected)[:10])
  tri,_,_,attrs=load_surfaces(ROOT/f'work/arena/maps/{name}');keep=['Fence'not in a['mat_flags']for a in attrs];tri=tri[keep];accelerated=Mesh(tri);origins=rng.uniform(tri.min(axis=(0,1)),tri.max(axis=(0,1)),(240,3));directions=rng.normal(size=(240,3));radii=rng.choice([0.,.3,.4,.5],240);ids,points,dist=accelerated.sphere(origins,directions,radii);hits=0
  for i,(o,d,r)in enumerate(zip(origins,directions,radii)):
   witness=first_sphere_hit(tri,o,d,r)
   assert(ids[i]>=0)==(witness is not None),(name,i,'hit parity')
   if witness is not None:
    hits+=1;assert abs(dist[i]-witness[2])<1e-6 and np.linalg.norm(points[i]-witness[1])<1e-5,(name,i,dist[i],witness)
  # Both directions and endpoints are deliberate, not merely open-space rays.
  assert not accelerated.clear_pairs([[0,1,-1000]],[[0,1,1000]])[0]or original.clear([0,1,-1000],[0,1,1000])
  results.append(dict(map=name,vision_cases=1000,sphere_cases=240,sphere_hits=hits));print('D4_GEOMETRY '+json.dumps(results[-1]),flush=True)
 tri=np.array([[[0,0,0],[2,0,0],[0,2,0]]],float);mesh=Mesh(tri);idx,p,t=mesh.sphere([[2.3,0,2],[2.3,0,2],[.4,.4,2]],[[0,0,-1]]*3,[.4,.2,.3]);assert idx.tolist()==[0,-1,0];assert abs(t[2]-1.7)<1e-9
 out=dict(passed=True,maps=results,total_comparisons=3723,seconds=time.monotonic()-began,scope='Same two-sided finite thin-ray and exact sphere face/edge/vertex predicates; original game assets not exported',source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in[Path(__file__),Path(__file__).with_name('geometry.cpp'),Path(__file__).with_name('geometry.py')]});path=ROOT/'work/d4/geometry-check-v1.json';assert not path.exists();path.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
