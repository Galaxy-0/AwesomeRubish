"""Exact ray semantics from CollisionMesh, with a local uniform broad phase.

Only the triangle candidate set changes. Intersection epsilon / thin-wall /
double-sided semantics are inherited, checked against the original mesh.
"""
import sys
from pathlib import Path
from collections import defaultdict
from functools import lru_cache
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from arena.geometry import CollisionMesh,GeometricVision,VisionConfig
class IndexedMesh(CollisionMesh):
    def __init__(self,triangles,cell=8.):
        super().__init__(triangles);self.cell=cell;self.cells=defaultdict(list);self.queries=0
        for i,(lo,hi)in enumerate(zip(self.low,self.high)):
            a=np.floor(lo/cell).astype(int);b=np.floor(hi/cell).astype(int)
            for x in range(a[0],b[0]+1):
                for y in range(a[1],b[1]+1):
                    for z in range(a[2],b[2]+1):self.cells[x,y,z].append(i)
    def hits(self,start,end,epsilon=.015):
        self.queries+=1;a=np.array(start,float);b=np.array(end,float)
        # Samples at <=cell/4 on segment, plus neighboring cells: conservative
        # superset even at grid edges/corners and with surface epsilon.
        n=max(2,int(np.linalg.norm(b-a)/self.cell*4)+2);cells=np.floor((a+(b-a)*np.linspace(0,1,n)[:,None])/self.cell).astype(int)
        ids=set()
        for c in set(map(tuple,cells)):
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    for dz in (-1,0,1):ids.update(self.cells.get((c[0]+dx,c[1]+dy,c[2]+dz),()))
        if not ids:return np.empty(0)
        ix=np.fromiter(ids,int);obj=object.__new__(CollisionMesh);obj.triangles=self.triangles[ix];obj.low=self.low[ix];obj.high=self.high[ix]
        return CollisionMesh.hits(obj,start,end,epsilon)

def reachable(atlas,starts):
    todo=[atlas.nearest(p)for p in starts];seen=set(todo)
    for n in todo:
        for q in atlas.edges[n]:
            if q not in seen:seen.add(q);todo.append(q)
    return np.array(sorted(seen),dtype=int)
