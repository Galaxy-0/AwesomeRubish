"""Derive compact numeric query inputs for an offline browser worker.

No renderer models/textures/raw resource files. Indexed collision-only numbers,
own BVH, own graph and own6KB geometry code; outputs remain ignored.
"""
import base64,hashlib,json,shutil,struct,subprocess,zlib
from dataclasses import asdict
from pathlib import Path
import numpy as np

def encoded(raw):return base64.b64encode(zlib.compress(raw,9)).decode()
def bvh(tri):
 low=tri.min(axis=1);high=tri.max(axis=1);center=low+high;nodes=[];order=[]
 def build(ids):
  lo=low[ids].min(axis=0);hi=high[ids].max(axis=0);index=len(nodes);node=[*lo,*hi,len(order),len(order)+len(ids),-1,-1];nodes.append(node)
  if len(ids)<=12:order.extend(ids.tolist())
  else:
   axis=int(np.argmax(hi-lo));mid=len(ids)//2;split=np.argpartition(center[ids,axis],mid);node[8]=build(ids[split[:mid]]);node[9]=build(ids[split[mid:]])
  return index
 if len(tri):build(np.arange(len(tri)))
 data=b''.join(struct.pack('<6d4i',*n)for n in nodes);return data,np.array(order,dtype='<i4').tobytes(),len(nodes)
def mesh_data(tri):
 tri=np.asarray(tri,float);vertices,indices=np.unique(tri.reshape(-1,3),axis=0,return_inverse=True);nodes,order,n=bvh(tri);v=vertices.astype('<f8').tobytes();ids=indices.astype('<u4').tobytes();raw=v+ids+nodes+order
 return dict(vertices=len(vertices),triangles=len(tri),nodes=n,bytes=len(raw),encoding='zlib-base64',data=encoded(raw),layout=['float64 vertices','uint32 triangle vertex indices','64byte BVH nodes:6double+4int','int32 original-triangle leaf order'])
def wasm(root,source):
 p=source('showcase/d4_geometry.cpp');digest=hashlib.sha256(p.read_bytes()).hexdigest();out=root/'work/d4/browser-build'/digest[:16];target=out/'geometry.wasm';meta=out/'build.json'
 if not target.exists():
  out.mkdir(parents=True,exist_ok=True);compiler=Path('/opt/homebrew/opt/llvm@17/bin/clang++');linkers=list((Path.home()/'.rustup/toolchains').glob('stable-*/lib/rustlib/*/bin/gcc-ld/wasm-ld'));linker=linkers[0]if linkers else shutil.which('wasm-ld')
  if not compiler.exists()or not linker:raise RuntimeError('local wasm32 compiler/linker needed; no package install performed')
  command=[str(compiler),'--target=wasm32-unknown-unknown','-fuse-ld='+str(linker),'-O3','-std=c++17','-ffreestanding','-fno-exceptions','-fno-rtti','-fno-math-errno','-nostdlib','-Wl,--no-entry','-Wl,--export-all','-Wl,--export-memory','-Wl,--initial-memory=33554432','-Wl,--max-memory=134217728',str(p),'-o',str(target)]
  subprocess.run(command,check=True,capture_output=True);meta.write_text(json.dumps(dict(source_sha256=digest,output_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),command=command),indent=2)+'\n')
 record=json.loads(meta.read_text());assert record['source_sha256']==digest and record['output_sha256']==hashlib.sha256(target.read_bytes()).hexdigest();source(meta);source(target);return base64.b64encode(target.read_bytes()).decode()
def compile_runtime(root,source):
 from arena.geometry import CollisionMesh
 from tools.zipcaster.surfaces import load_surfaces
 from tools.zipcaster_d4.model_v2 import Config
 from tools.zipcaster_d3r.native_kinematics import JUMP_T,JUMP_Y
 maps=[]
 for name in['Yunohana','District00','Yagara']:
  directory=root/f'work/d4/graph-v2-{name}';source(directory/'graph.npz');meta=json.loads(source(directory/'graph.json').read_text());z=np.load(directory/'graph.npz');tri,_,_,attrs=load_surfaces(root/f'work/arena/maps/{name}');field=tri[np.array(['Fence'not in a['mat_flags']for a in attrs])];source(root/f'work/arena/maps/{name}/sight.npz');vision=CollisionMesh.load(root/f'work/arena/maps/{name}/sight.npz').triangles
  g=len(z['ground']);h=len(z['anchors']);counts=np.bincount(z['edge_source'],minlength=g+h);ptr=np.r_[0,np.cumsum(counts)].astype('<u4');assert len(z['edge_frames'])==ptr[-1]and max(z['edge_frames'])<256 and h<65536
  arrays=[z[k].astype('<f8').tobytes()for k in['ground','anchors','normals','floor']]+[ptr.tobytes(),z['edge_destination'].astype('<u2').tobytes(),z['edge_frames'].astype('u1').tobytes()];raw=b''.join(arrays)
  maps.append(dict(id=name,g=g,h=h,edges=len(z['edge_frames']),encoding='zlib-base64',data=encoded(raw),field=mesh_data(field),vision=mesh_data(vision),flight=meta['flight_model'],layout=['float64 groundGx3','float64 anchorsHx3','float64 normalsHx3','float64 floorsH','uint32 source pointers(G+H+1)','uint16 destinationsE','uint8 framesE']))
 return dict(schema='showcase.d4.runtime.v1',maps=maps,wasm=wasm(root,source),config=asdict(Config()),jump_t=JUMP_T.tolist(),jump_y=JUMP_Y.tolist(),attack_parameters=json.loads(source('work/d3r/attack-parameters-v1.json').read_text()),scope='Browser recomputes selected routes on collision-only deduplicated numeric geometry and own BVH, same predicates. No original renderer model/texture/screenshot/audio. All graph/geometry outputs and generatedHTML ignored.')
if __name__=='__main__':
 import sys
 root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));seen={}
 def source(p):
  p=Path(p);p=p if p.is_absolute()else root/p;seen[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest();return p
 out=root/'work/d4/browser/runtime-v1.json';assert not out.exists();d=compile_runtime(root,source);d['sources']=seen;out.write_text(json.dumps(d,separators=(',',':'))+'\n');print('RUNTIME_BYTES',out.stat().st_size)
