"""Source-bound local C++ BVH. Exact predicates, no quantized/voxel LOS.

Only accelerates collision queries on existing local derived triangles. Shared
library builds under work/d4 keyed by source SHA, never a game host path.
"""
import ctypes as C,hashlib,json,subprocess
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
D=np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS');I=np.ctypeslib.ndpointer(dtype=np.int32,flags='C_CONTIGUOUS');U=np.ctypeslib.ndpointer(dtype=np.uint8,flags='C_CONTIGUOUS')
_LIBRARY=None

def library():
 global _LIBRARY
 if _LIBRARY is None:
  source=Path(__file__).with_suffix('.cpp');digest=hashlib.sha256(source.read_bytes()).hexdigest();out=ROOT/'work/d4/geometry-build'/digest[:16];out.mkdir(parents=True,exist_ok=True);target=out/'geometry.dylib';record=out/'build.json'
  if not target.exists():
   command=['c++','-O3','-std=c++17','-dynamiclib',str(source),'-o',str(target)]
   with(out/'build.log').open('w')as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True)
   record.write_text(json.dumps(dict(source_sha256=digest,output_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),command=command),indent=2)+'\n')
  meta=json.loads(record.read_text());assert meta['source_sha256']==digest and meta['output_sha256']==hashlib.sha256(target.read_bytes()).hexdigest()
  lib=C.CDLL(str(target));lib.d4_geometry_version.restype=C.c_int;assert lib.d4_geometry_version()==1
  lib.d4_mesh_new.argtypes=[D,C.c_int];lib.d4_mesh_new.restype=C.c_void_p;lib.d4_mesh_delete.argtypes=[C.c_void_p]
  lib.d4_sphere_batch.argtypes=[C.c_void_p,C.c_int,D,D,D,D,I,D,D];lib.d4_clear_batch.argtypes=[C.c_void_p,C.c_int,D,D,C.c_double,U];_LIBRARY=lib
 return _LIBRARY
class Mesh:
 def __init__(self,triangles):self.lib=library();self.tri=np.ascontiguousarray(triangles,dtype=np.float64).reshape(-1,3,3);self.pointer=self.lib.d4_mesh_new(self.tri,len(self.tri))
 def __del__(self):
  if getattr(self,'pointer',None):self.lib.d4_mesh_delete(self.pointer);self.pointer=None
 def sphere(self,origins,directions,radius=.4,length=35.):
  a,d=np.broadcast_arrays(np.asarray(origins,float),np.asarray(directions,float));a=np.ascontiguousarray(a.reshape(-1,3));d=np.ascontiguousarray(d.reshape(-1,3));n=len(a);r=np.ascontiguousarray(np.broadcast_to(radius,(n,)));ll=np.ascontiguousarray(np.broadcast_to(length,(n,)));ids=np.empty(n,np.int32);p=np.empty((n,3));dist=np.empty(n);self.lib.d4_sphere_batch(self.pointer,n,a,d,r,ll,ids,p,dist);return ids,p,dist
 def clear_pairs(self,starts,ends,epsilon=.015):
  a,b=np.broadcast_arrays(np.asarray(starts,float),np.asarray(ends,float));a=np.ascontiguousarray(a.reshape(-1,3));b=np.ascontiguousarray(b.reshape(-1,3));out=np.empty(len(a),np.uint8);self.lib.d4_clear_batch(self.pointer,len(a),a,b,epsilon,out);return out.astype(bool)
