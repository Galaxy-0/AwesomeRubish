"""First contact of a translating sphere and static triangle soup.

Pure derived-geometry query: two-sided faces, finite edges and vertices.
Returns triangle, contact point and center travel; no game resources exported.
"""
import numpy as np

def first_sphere_hit(triangles,start,direction,radius,max_distance=35.):
 tri=np.asarray(triangles,float);o=np.asarray(start,float);d=np.asarray(direction,float);d=d/np.linalg.norm(d)
 if radius<0:raise ValueError('nonnegative radius')
 end=o+d*max_distance;lo=np.minimum(o,end)-radius-1e-6;hi=np.maximum(o,end)+radius+1e-6;ids=np.flatnonzero(((tri.min(axis=1)<=hi)&(tri.max(axis=1)>=lo)).all(axis=1));tri=tri[ids]
 if not len(ids):return None
 best=np.inf;best_id=None;best_point=None
 def accept(t,p,valid):
  nonlocal best,best_id,best_point
  valid=valid&np.isfinite(t)&(t>1e-5)&(t<=max_distance+1e-6);ts=np.where(valid,t,np.inf);j=int(ts.argmin())
  if ts[j]<best:best=float(ts[j]);best_id=int(ids[j]);best_point=p[j].copy()
 a,b,c=tri[:,0],tri[:,1],tri[:,2];n=np.cross(b-a,c-a);length=np.linalg.norm(n,axis=1);n/=np.maximum(length[:,None],1e-15);nd=n@d;sd=np.sum((o-a)*n,axis=1)
 for sign in[-1.,1.]:
  t=np.divide(sign*radius-sd,nd,out=np.full_like(sd,np.inf),where=np.abs(nd)>1e-12);safe=np.where(np.isfinite(t),t,0);p=o+safe[:,None]*d-sign*radius*n
  v0=b-a;v1=c-a;v2=p-a;d00=np.sum(v0*v0,axis=1);d01=np.sum(v0*v1,axis=1);d11=np.sum(v1*v1,axis=1);d20=np.sum(v2*v0,axis=1);d21=np.sum(v2*v1,axis=1);den=d00*d11-d01*d01
  u=np.divide(d11*d20-d01*d21,den,out=np.zeros_like(den),where=abs(den)>1e-14);v=np.divide(d00*d21-d01*d20,den,out=np.zeros_like(den),where=abs(den)>1e-14)
  accept(t,p,(length>1e-12)&(abs(den)>1e-14)&(u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7))
 for p0,p1 in[(a,b),(b,c),(c,a)]:
  ba=p1-p0;oa=o-p0;baba=np.sum(ba*ba,axis=1);bard=ba@d;baoa=np.sum(ba*oa,axis=1);rdoa=oa@d;oaoa=np.sum(oa*oa,axis=1);aa=baba-bard*bard;bb=baba*rdoa-baoa*bard;cc=baba*oaoa-baoa*baoa-radius*radius*baba;h=bb*bb-aa*cc
  t=np.divide(-bb-np.sqrt(np.maximum(0,h)),aa,out=np.full_like(aa,np.inf),where=abs(aa)>1e-12);safe=np.where(np.isfinite(t),t,0);y=baoa+safe*bard;p=p0+ba*np.divide(y,baba,out=np.zeros_like(y),where=baba>1e-12)[:,None];accept(t,p,(h>=0)&(baba>1e-12)&(y>=0)&(y<=baba))
 for p0 in[a,b,c]:
  oc=o-p0;b0=oc@d;cc=np.sum(oc*oc,axis=1)-radius*radius;h=b0*b0-cc;t=-b0-np.sqrt(np.maximum(h,0));accept(t,p0,h>=0)
 return None if best_id is None else(best_id,best_point,best)
