"""Parameterized human-like visibility approximation, independent of game camera."""
from dataclasses import dataclass
import math
from pathlib import Path
import numpy as np
from .referee import VisibilityWitness


@dataclass(frozen=True)
class VisionConfig:
    human_eye: float = 1.1
    squid_eye: float = .25
    body_heights: tuple[float, ...] = (.12, .7, 1.3)
    half_fov_degrees: float = 60.
    max_distance: float = 100.
    surface_epsilon: float = .015

    def __post_init__(self):
        if not 0 < self.half_fov_degrees <= 180 or self.max_distance <= 0:
            raise ValueError('invalid FOV/range')
        if min(self.human_eye,self.squid_eye,*self.body_heights) <= 0:
            raise ValueError('eye/body heights must be positive')


class CollisionMesh:
    def __init__(self, triangles):
        self.triangles=np.asarray(triangles,dtype=float).reshape((-1,3,3))
        if not len(self.triangles) or not np.isfinite(self.triangles).all():raise ValueError('invalid collision mesh')
        self.low=self.triangles.min(axis=1);self.high=self.triangles.max(axis=1)

    @classmethod
    def load(cls,path:Path):
        with np.load(path,allow_pickle=False) as data:return cls(data['triangles'])

    def hits(self,start,end,epsilon=.015):
        """Double-sided Moller-Trumbore segment hits, including thin walls."""
        a=np.asarray(start,float);b=np.asarray(end,float);d=b-a;length=np.linalg.norm(d)
        if length<epsilon:return np.empty(0)
        keep=((self.low<=np.maximum(a,b)+epsilon)&(self.high>=np.minimum(a,b)-epsilon)).all(axis=1)
        tri=self.triangles[keep]
        if not len(tri):return np.empty(0)
        e1=tri[:,1]-tri[:,0];e2=tri[:,2]-tri[:,0]
        p=np.cross(np.broadcast_to(d,e2.shape),e2);det=np.einsum('ij,ij->i',e1,p)
        good=np.abs(det)>1e-10
        inv=np.zeros_like(det);inv[good]=1/det[good]
        tvec=a-tri[:,0];u=np.einsum('ij,ij->i',tvec,p)*inv
        q=np.cross(tvec,e1);v=q@d*inv;t=np.einsum('ij,ij->i',e2,q)*inv
        good &= (u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8)&(t>epsilon/length)&(t<1-epsilon/length)
        return np.sort(t[good]*length)

    def clear(self,start,end,epsilon=.015):return len(self.hits(start,end,epsilon))==0

    def floor(self,x,z,top=80.,bottom=-30.):
        hits=self.hits((x,top,z),(x,bottom,z),.0001)
        return top-hits[0] if len(hits) else None


class GeometricVision:
    def __init__(self,mesh:CollisionMesh,config=VisionConfig()):self.mesh=mesh;self.config=config

    def witnesses(self,truth,observer):
        own=next(p for p in truth.players if p.player_id==observer);result=[];c=self.config
        for target in truth.players:
            if target.team==own.team:continue
            fov=clear=None
            if own.position is not None and target.position is not None and own.heading is not None and own.form_squid is not None:
                dx=target.position[0]-own.position[0];dz=target.position[2]-own.position[2]
                delta=math.atan2(math.sin(math.atan2(dx,dz)-own.heading),math.cos(math.atan2(dx,dz)-own.heading))
                fov=math.hypot(dx,dz)<=c.max_distance and abs(delta)<=math.radians(c.half_fov_degrees)
                eye=np.array(own.position)+[0,c.squid_eye if own.form_squid else c.human_eye,0]
                clear=any(self.mesh.clear(eye,np.array(target.position)+[0,height,0],c.surface_epsilon) for height in c.body_heights)
            result.append(VisibilityWitness(truth.match_id,truth.frame,observer,target.player_id,
                                            target.sample_frame,fov,clear))
        return tuple(result)
