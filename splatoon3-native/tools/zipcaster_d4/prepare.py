"""Complete declared3u ground/wall graph. No strategy-ranked hook subset.

Material-filter all known vertical hook surfaces; both face sides sampled.
A corrected sphere-center aim maps every link to the requested face point.
Ceiling/ground bind rules remain unsupported, not silently certified surfaces.
"""
import argparse,json,math,sys,time,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d4.geometry import Mesh
from tools.zipcaster.surfaces import load_surfaces
from arena.lib.atlas import MapAtlas
from tools.zipcaster_d3r.native_kinematics import JUMP_T,JUMP_Y

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def wall_samples(tri,norm,eligible,spacing):
 samples={};faces=set()
 for i in np.flatnonzero(eligible):
  a,b,c=tri[i];n=int(math.ceil(max(np.linalg.norm(a-b),np.linalg.norm(a-c),np.linalg.norm(b-c))/spacing));n=max(1,n);pp=[(a+b+c)/3]
  # Interior barycentric lattice covers each triangle, not merely its vertices.
  if n>1:
   for j in range(n):
    for k in range(n-j):pp.append(a+(b-a)*(j+.333333333)/n+(c-a)*(k+.333333333)/n)
  for p in pp:
   for sign in[-1,1]:
    normal=norm[i]*sign;key=(*np.floor(p/spacing+.5).astype(int),*np.round(normal*16).astype(int));candidate=dict(point=p,normal=normal,face=int(i))
    if key not in samples:samples[key]=candidate
  faces.add(int(i))
 return list(samples.values()),faces

def commands(starts,centers,par):
 coef=par['origin_coefficients'];yaw=np.arctan2(centers[:,0]-starts[:,0],centers[:,2]-starts[:,2])-par['yaw_bias']
 for _ in range(8):
  origin=starts+np.c_[coef[1]*np.sin(yaw)+coef[2]*np.cos(yaw)+coef[4],np.full(len(yaw),coef[0]),coef[1]*np.cos(yaw)-coef[2]*np.sin(yaw)+coef[3]];d=centers-origin;yaw=np.arctan2(d[:,0],d[:,2])-par['yaw_bias']
 distance=np.linalg.norm(d,axis=1);u=d/np.maximum(distance[:,None],1e-15);elev=np.arctan2(d[:,1],np.hypot(d[:,0],d[:,2]));pitch=np.arctan((np.tan(elev)-par['tangent_bias'])/par['tangent_scale']);return origin,u,yaw,pitch,distance

def prepare(a):
 if a.out.exists():raise ValueError('fresh output directory required')
 a.out.mkdir(parents=True);began=time.monotonic();atlas=MapAtlas.load(a.stage);name=atlas.data['name'];tri,norm,area,attrs=load_surfaces(ROOT/f'work/arena/maps/{name}');usable=np.array(['SplPlayerSuperHookCheck'not in d['col_disable_flags']and'Fence'not in d['mat_flags']for d in attrs]);canbind=np.array(['SuperHookCantBind'not in d['mat_flags']and'KeepOut'not in d['mat_flags']for d in attrs]);eligible=usable&canbind&(abs(norm[:,1])<.5)&(area>1e-8);candidates,faces=wall_samples(tri,norm,eligible,a.spacing)
 allground=np.array(atlas.points);ground_ids=np.flatnonzero(np.isclose(allground[:,0]/a.spacing,np.round(allground[:,0]/a.spacing))&np.isclose(allground[:,2]/a.spacing,np.round(allground[:,2]/a.spacing)));ground=allground[ground_ids];anchors=np.array([p['point']for p in candidates]);normals=np.array([p['normal']for p in candidates]);faceids=np.array([p['face']for p in candidates]);attach=anchors+normals*.6-[0,.6,0]
 # Range-only exclusion is exhaustive relative to the declared ground grid.
 # Do not filter by native-policy reachability or a preferred starting region.
 near=np.zeros(len(anchors),bool)
 for start in ground:near|=np.linalg.norm(anchors-start-[0,1.1,0],axis=1)<=35.8
 anchors,normals,faceids,attach=anchors[near],normals[near],faceids[near],attach[near];radius=.4;par=json.loads(a.ray.read_text())['parameters'];mesh=Mesh(tri[usable]);local_can=canbind[usable];local_norm=norm[usable];parts=[];queries=0
 sources=np.concatenate([ground,attach+[0,float(np.interp(6,JUMP_T,JUMP_Y)),0]]);allsource=[];alldest=[];yaws=[];pitches=[];distances=[]
 for i,start in enumerate(sources):
  delta=anchors-start-[0,1.1,0];distance=np.linalg.norm(delta,axis=1);facing=(delta*normals).sum(axis=1)<-.05;ids=np.flatnonzero((distance<=35.8)&facing)
  if i>=len(ground):ids=ids[ids!=i-len(ground)]
  if not len(ids):continue
  ss=np.broadcast_to(start,(len(ids),3));origin,u,yaw,pitch,distance=commands(ss,anchors[ids]+normals[ids]*radius,par);good=(abs(pitch)<=.9)&(distance<=35.000001);ids=ids[good];origin=origin[good];u=u[good];yaw=yaw[good];pitch=pitch[good]
  if not len(ids):continue
  hit,point,length=mesh.sphere(origin,u,radius,35.);queries+=len(ids);ok=hit>=0;safe=np.maximum(hit,0);ok&=local_can[safe]&(np.linalg.norm(point-anchors[ids],axis=1)<=.15)&(abs((local_norm[safe]*normals[ids]).sum(axis=1))>.95)
  keep=ids[ok];allsource.extend([i]*len(keep));alldest.extend(keep.tolist());yaws.extend(yaw[ok]);pitches.extend(pitch[ok]);distances.extend(np.linalg.norm(attach[keep]-start,axis=1).tolist())
  if i%200==0:print('D4_GRAPH '+json.dumps(dict(map=name,source=i,total_sources=len(sources),links=len(allsource),sphere_queries=queries)),flush=True)
 source=np.array(allsource,np.int32);destination=np.array(alldest,np.int32);distances=np.array(distances);frames=np.ceil(25.6+1.55*distances).astype(np.uint16)
 # Kill poses land on a floor below the wall-side attachment, preserving layers.
 # Never choose a nearby floor above attachment merely because it is closer.
 floors=np.full(len(attach),-40.)
 for i,p in enumerate(attach):
  dxz=np.linalg.norm(allground[:,[0,2]]-p[[0,2]],axis=1);valid=(dxz<=1.1)&(allground[:,1]<=p[1]+.15)
  if valid.any():
   minimum=dxz[valid].min();valid&=dxz<=minimum+.12;floors[i]=allground[valid,1].max()
 np.savez_compressed(a.out/'graph.npz',ground=ground,ground_atlas_ids=ground_ids,anchors=anchors,normals=normals,face_ids=faceids,attach=attach,floor=floors,edge_source=source,edge_destination=destination,edge_distance=distances.astype(np.float32),edge_frames=frames,edge_yaw=np.array(yaws,np.float32),edge_pitch=np.array(pitches,np.float32))
 meta=dict(schema='inklab.d4.graph.v1',map=name,stage=a.stage,ground_spacing=a.spacing,ground_nodes=len(ground),candidate_wall_faces=int(eligible.sum()),wall_faces_sampled=len(faces),sampled_wall_nodes_before_range=int(near.size),wall_nodes=len(anchors),links=len(source),sphere_queries=queries,seconds=time.monotonic()-began,ray_parameters_sha256=sha(a.ray),geometry_accelerator_sha256=sha(Path(__file__).with_name('geometry.cpp')),source_sha256={str(p.relative_to(ROOT)):sha(p)for p in[Path(__file__),Path(__file__).with_name('geometry.py'),ROOT/'tools/zipcaster/surfaces.py',ROOT/'tools/zipcaster_d3r/native_kinematics.py']},input_sha256={str(p.relative_to(ROOT)):sha(p)for p in[ROOT/f'work/arena/maps/{name}/navigation.json',ROOT/f'work/arena/maps/{name}/manifest.json']},graph_sha256=sha(a.out/'graph.npz'),scope=['All lattice ground points/all material-eligible known vertical faces, no policy-reachability/start-region/score cap. Both wall normals sampled.','Full3u declared graph only, not every continuous point. Ground/ceiling hook eligibility remains unsupported; not falsely declared unbindable.','Links use fittedD3-R origin/tangent/sphere.4/Fence proxy and sphere-center aim; first-contact point within.15 and material/normal checked. Native validation required.','Fixed nominal source pose/body heading0; incoming contact and native attachment can vary. No unvalidated dynamic geometry.','Flight frame rule is provisional25.6+1.55*body distance pending own-motion regression. B6 and low-wall fall extrapolate; floor cannot snap above attachment.'])
 (a.out/'graph.json').write_text(json.dumps(meta,indent=2)+'\n');print('D4_GRAPH_DONE '+json.dumps(meta),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--stage',type=int,choices=[1,2,3],required=True);p.add_argument('--spacing',type=int,choices=[2,3],default=3);p.add_argument('--ray',type=Path,default=ROOT/'work/d3r/ray-v2-frozen.json');p.add_argument('--out',type=Path,required=True);prepare(p.parse_args())
