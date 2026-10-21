"""Exact shared-origin segment batches, NumPy BVH; same thin-wall tests.

The original CollisionMesh is the oracle. BVH only prunes triangle candidates;
no voxelization, ray quantization, one-sided faces or visibility approximation.
"""
import numpy as np
from arena.geometry import CollisionMesh
class BatchMesh(CollisionMesh):
    def __init__(self,triangles,leaf_size=20):
        super().__init__(triangles);self.e1=self.triangles[:,1]-self.triangles[:,0];self.e2=self.triangles[:,2]-self.triangles[:,0];self.norm=np.cross(self.e1,self.e2);self.nodes=[];self.queries=0
        centers=(self.low+self.high)/2
        def build(ids):
            index=len(self.nodes);low=self.low[ids].min(axis=0);high=self.high[ids].max(axis=0);self.nodes.append(None)
            if len(ids)<=leaf_size:self.nodes[index]=(low,high,None,None,ids)
            else:
                axis=np.ptp(centers[ids],axis=0).argmax();order=ids[np.argsort(centers[ids,axis],kind='stable')];mid=len(ids)//2
                left=build(order[:mid]);right=build(order[mid:]);self.nodes[index]=(low,high,left,right,None)
            return index
        self.root=build(np.arange(len(self.triangles)))
    def clear_many(self,start,ends,epsilon=.015):
        start=np.asarray(start,float);ends=np.asarray(ends,float).reshape(-1,3);direction=ends-start;length=np.linalg.norm(direction,axis=1);alive=np.ones(len(ends),bool);self.queries+=len(ends)
        threshold=epsilon/np.maximum(length,1e-30);zero=np.abs(direction)<1e-15
        inv=np.divide(1.,direction,out=np.zeros_like(direction),where=~zero)
        def visit(node_index,ids):
            ids=ids[alive[ids]]
            if not len(ids):return
            lo,hi,left,right,tri_ids=self.nodes[node_index];d=direction[ids];z=zero[ids]
            a=(lo-epsilon-start)*inv[ids];b=(hi+epsilon-start)*inv[ids]
            near=np.where(z,-np.inf,np.minimum(a,b)).max(axis=1);far=np.where(z,np.inf,np.maximum(a,b)).min(axis=1)
            valid=(~z|((start>=lo-epsilon)&(start<=hi+epsilon))).all(axis=1)&(near<=far)&(far>threshold[ids])&(near<1-threshold[ids])
            ids=ids[valid]
            if not len(ids):return
            if tri_ids is None:
                # Closer child first helps occlusion early-out. AABB center
                # distance is only an ordering heuristic, never a filter.
                ln=self.nodes[left];rn=self.nodes[right]
                if np.linalg.norm((ln[0]+ln[1])/2-start)<=np.linalg.norm((rn[0]+rn[1])/2-start):visit(left,ids);visit(right,ids)
                else:visit(right,ids);visit(left,ids)
                return
            d=direction[ids];tvec=start-self.triangles[tri_ids,0];q=np.cross(tvec,self.e1[tri_ids]);det=-(d@self.norm[tri_ids].T);good=np.abs(det)>1e-10
            reciprocal=np.divide(1.,det,out=np.zeros_like(det),where=good)
            u=(d@np.cross(self.e2[tri_ids],tvec).T)*reciprocal;v=(d@q.T)*reciprocal;t=np.einsum('ij,ij->i',self.e2[tri_ids],q)[None,:]*reciprocal
            good&=(u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8)&(t>threshold[ids,None])&(t<1-threshold[ids,None])
            alive[ids[good.any(axis=1)]]=False
        ids=np.flatnonzero(length>=epsilon)
        if len(ids):visit(self.root,ids)
        return alive
    def clear_pairs(self,starts,ends,epsilon=.015):
        starts=np.asarray(starts,float);ends=np.asarray(ends,float);unique,inverse=np.unique(starts,axis=0,return_inverse=True);result=np.ones(len(starts),bool)
        for i,p in enumerate(unique):
            ids=np.flatnonzero(inverse==i);targets,back=np.unique(ends[ids],axis=0,return_inverse=True);result[ids]=self.clear_many(p,targets,epsilon)[back]
        return result
