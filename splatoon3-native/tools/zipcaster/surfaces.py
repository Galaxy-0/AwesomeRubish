"""Local collision faces with material metadata; exports are derived/ignored."""
from pathlib import Path
import json
import numpy as np
from tools.stage_collision import transform


def load_surfaces(directory):
    directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text());parts=[];attributes=[]
    for actor in manifest['actors']:
        matrix,translation=transform({'Rotate':actor['rotate'],'Scale':actor['scale'],'Translate':actor['translate']})
        for path in sorted((directory/'sources'/actor['actor']).glob('*.obj')):
            materials=json.loads(path.with_suffix('.json').read_text());vertices=[];material=None;name=None
            for line in path.open():
                if line.startswith('v '):vertices.append([float(v)for v in line.split()[1:4]])
                elif line.startswith('usemtl '):name=line.split()[1];material=materials[name]
                elif line.startswith('f '):
                    if material is None:raise ValueError('face without material')
                    ids=[int(v.split('/')[0])-1 for v in line.split()[1:]]
                    for i in range(1,len(ids)-1):
                        tri=np.array([vertices[j]for j in (ids[0],ids[i],ids[i+1])])@matrix.T+translation
                        parts.append(tri);attributes.append(dict(actor=actor['actor'],material=name,
                            mat_flags=material.get('mat_flags',[]),col_disable_flags=material.get('col_disable_flags',[])))
    tri=np.asarray(parts).reshape(-1,3,3);normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);area=np.linalg.norm(normal,axis=1);normal/=np.maximum(area[:,None],1e-12)
    return tri,normal,area*.5,attributes


def first_hit(triangles,start,end,epsilon=1e-5):
    a=np.asarray(start,float);d=np.asarray(end,float)-a;tri=np.asarray(triangles)
    lo=np.minimum(a,a+d)-epsilon;hi=np.maximum(a,a+d)+epsilon
    ids=np.flatnonzero(((tri.min(axis=1)<=hi)&(tri.max(axis=1)>=lo)).all(axis=1));t=tri[ids]
    if not len(t):return None
    e1=t[:,1]-t[:,0];e2=t[:,2]-t[:,0];p=np.cross(d,e2);det=np.sum(e1*p,axis=1);valid=np.abs(det)>1e-10
    inv=np.zeros_like(det);inv[valid]=1/det[valid];v=a-t[:,0];u=np.sum(v*p,axis=1)*inv;q=np.cross(v,e1);w=q@d*inv;along=np.sum(e2*q,axis=1)*inv
    valid&=(u>=-1e-7)&(w>=-1e-7)&(u+w<=1+1e-7)&(along>epsilon)&(along<=1+epsilon)
    if not valid.any():return None
    candidates=np.where(valid,along,np.inf);index=candidates.argmin();fraction=float(along[index]);return int(ids[index]),a+d*fraction,fraction
