"""Bounded referee-only scene setup. A4 will validate the public skill library."""
import heapq
import math
import numpy as np


class SetupGrid:
    def __init__(self,mesh):
        self.heights={}
        for x in range(-40,41):
            for z in range(-80,81):
                y=mesh.floor(x,z)
                if y is not None and -.05<=y<=20:self.heights[x,z]=y
        # Scene setup uses human movement: give the body clearance from raised
        # corners instead of letting a point path scrape a half-unit curb.
        self.clear={p for p,y in self.heights.items() if all(
            self.heights.get((p[0]+dx,p[1]+dz),y)<=y+.4
            for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)))}

    def nearest(self,p):
        return min(self.heights,key=lambda q:(q[0]-p[0])**2+(q[1]-p[2])**2+4*(self.heights[q]-p[1])**2)

    def route(self,start,end):
        a,b=self.nearest(start),self.nearest(end);queue=[(0.,a)];cost={a:0};prev={a:None}
        while queue:
            _,p=heapq.heappop(queue)
            if p==b:break
            for dx,dz in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                q=(p[0]+dx,p[1]+dz)
                if q not in self.heights:continue
                rise=self.heights[q]-self.heights[p]
                if rise>.7 or rise< -3.5:continue
                if q not in self.clear and rise>=-.5:continue
                n=cost[p]+math.hypot(dx,dz)+abs(rise)*.3
                if n>=cost.get(q,math.inf):continue
                cost[q]=n;prev[q]=p;heapq.heappush(queue,(n+math.dist(q,b),q))
        if b not in prev:raise ValueError(f'no setup route {a} -> {b}')
        points=[];q=b
        while q is not None:points.append((q[0],self.heights[q],q[1]));q=prev[q]
        return list(reversed(points))


def movement(position,target,camera_forward):
    delta=np.asarray(target)[[0,2]]-np.asarray(position)[[0,2]]
    forward=np.asarray(camera_forward)[[0,2]];forward/=np.linalg.norm(forward)
    right=np.array([-forward[1],forward[0]])
    xy=np.array([delta@right,delta@forward]);norm=np.linalg.norm(xy)
    return xy/max(norm,1.)
