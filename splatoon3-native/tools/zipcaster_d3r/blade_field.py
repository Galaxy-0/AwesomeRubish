"""Native Saber core field sphere proxy, independent of thin vision rays.

Selected sparse numeric parameters: light CoreIndex2/radius.3, full3/.5.
Native light impact points in two pilots reproduce at <.001u from exact birth
pose/vector. This does not validate all materials/dynamic objects or side spheres.
"""
import numpy as np
from tools.zipcaster.surfaces import load_surfaces
from tools.zipcaster_d3r.sphere_cast import first_sphere_hit
class BladeField:
 def __init__(self,directory):
  tri,norm,area,attrs=load_surfaces(directory);keep=np.array(['Fence'not in a['mat_flags']for a in attrs]);self.tri=tri[keep];self.low=self.tri.min(axis=1);self.high=self.tri.max(axis=1);self.cache={};self.queries=0
 def hit(self,origin,direction,radius,length):
  o=np.asarray(origin);d=np.asarray(direction);d=d/np.linalg.norm(d);end=o+d*length;lo=np.minimum(o,end)-radius-1e-6;hi=np.maximum(o,end)+radius+1e-6;ix=np.flatnonzero(((self.low<=hi)&(self.high>=lo)).all(axis=1));self.queries+=1
  return first_sphere_hit(self.tri[ix],o,d,radius,length)if len(ix)else None
 def clear_pairs(self,origins,targets,full):
  out=[];radius=.5 if full else .3;offset=.8 if full else 1.4
  rows=np.concatenate([origins,targets],axis=1);unique,inverse=np.unique(rows,axis=0,return_inverse=True)
  for row in unique:
   key=(bool(full),*row);value=self.cache.get(key)
   if value is None:
    o=row[:3];delta=row[3:]-o;length=np.linalg.norm(delta)
    if length<1e-9:value=True
    else:
     direction=delta/length;start=o+direction*min(offset,length);maximum=max(0.,length-offset-radius-.35);value=bool(maximum<=0 or self.hit(start,direction,radius,maximum)is None)
    self.cache[key]=value
   out.append(value)
  return np.asarray(out,bool)[inverse]
