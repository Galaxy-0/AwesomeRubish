#!/usr/bin/env python3
"""Build conservative public walk/potential-swim graphs from local collision.

Outputs contain game geometry and remain under ignored work/. No live paint or
opponent state is used. Material flags and body collision differ from Sight.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.geometry import CollisionMesh
from tools.stage_collision import STAGES,unpack,transform
from tools.byml import read


def surfaces(path):
    materials=json.loads(path.with_suffix('.json').read_text());vertices=[];triangles=[];swim=[];group=None
    for line in path.open():
        if line.startswith('v '):vertices.append([float(v) for v in line.split()[1:4]])
        elif line.startswith('usemtl '):group=materials[line.split()[1]]
        elif line.startswith('f '):
            if group is None:raise ValueError('missing collision material')
            disabled=set(group['col_disable_flags']);flags=set(group['mat_flags'])
            if disabled.intersection(('SplPlayer','SplPlayerHuman')):continue
            ids=[int(v.split('/')[0])-1 for v in line.split()[1:]]
            can_swim=not (disabled.intersection(('SplPlayerSquid_Visible','SplPlayerSquid_Invisible')) or
                          flags.intersection(('ForceColPaintNotPaintable','Fence')))
            for i in range(1,len(ids)-1):triangles.append([vertices[j] for j in (ids[0],ids[i],ids[i+1])]);swim.append(can_swim)
    return np.asarray(triangles,float).reshape((-1,3,3)),np.asarray(swim,bool)


def segments_clear(triangles,starts,ends,epsilon=.005):
    """Batched double-sided segment sweep against a local collision subset."""
    if not len(triangles):return True
    a=np.asarray(starts,float)[:,None,:];d=(np.asarray(ends,float)-np.asarray(starts,float))[:,None,:]
    t=np.asarray(triangles,float)[None,:,:,:];e1=t[:,:,1]-t[:,:,0];e2=t[:,:,2]-t[:,:,0]
    cross=np.cross(d,e2);det=np.sum(e1*cross,axis=2);good=np.abs(det)>1e-10
    inv=np.zeros_like(det);inv[good]=1/det[good]
    delta=a-t[:,:,0];u=np.sum(delta*cross,axis=2)*inv;q=np.cross(delta,e1)
    v=np.sum(d*q,axis=2)*inv;along=np.sum(e2*q,axis=2)*inv
    hits=good & (u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8)&(along>=-1e-8)&(along<=1+1e-8)
    return not bool(np.any(hits))


def edge_kind(mesh,p,q,radius=.3,max_step=.2,max_jump=.8):
    """Terrain-following foot/knee/body lanes; elevated flight is labelled jump.

    This is a sampled capsule approximation, not an exact native physics shape.
    Continuous ramps may rise more than max_step across a whole metre; only
    their local support discontinuities are treated as steps.
    """
    a=np.asarray(p[:3],float);b=np.asarray(q[:3],float);rise=b[1]-a[1]
    if not -3.5<=rise<=max_jump:return None
    low=np.minimum(a,b)-[radius,.21,radius];high=np.maximum(a,b)+[radius,2.6,radius]
    keep=((mesh.low<=high)&(mesh.high>=low)).all(axis=1);tri=mesh.triangles[keep]
    direction=b-a;length=np.linalg.norm(direction[[0,2]])
    side=np.array([-direction[2],0.,direction[0]])*radius/max(length,.001)
    ts=np.linspace(0,1,max(3,math.ceil(length/.2)+1))
    lanes=np.array([a+ts[:,None]*direction+offset for offset in (np.zeros(3),side,-side)])
    normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);up=normals[:,1]/np.maximum(np.linalg.norm(normals,axis=1),1e-10)>=.7
    floor=tri[up];support=np.full(lanes.shape[:2],np.nan)
    if len(floor):
        xz=lanes.reshape(-1,3)[:,[0,2]][:,None,:];base=floor[None,:,0][:,:,[0,2]]
        e1=floor[None,:,1][:,:,[0,2]]-base;e2=floor[None,:,2][:,:,[0,2]]-base
        det=e1[:,:,0]*e2[:,:,1]-e1[:,:,1]*e2[:,:,0];valid=np.abs(det)>1e-10
        inv=np.zeros_like(det);inv[valid]=1/det[valid];delta=xz-base
        u=(delta[:,:,0]*e2[:,:,1]-delta[:,:,1]*e2[:,:,0])*inv
        v=(e1[:,:,0]*delta[:,:,1]-e1[:,:,1]*delta[:,:,0])*inv
        heights=floor[None,:,0,1]+u*(floor[None,:,1,1]-floor[None,:,0,1])+v*(floor[None,:,2,1]-floor[None,:,0,1])
        ok=valid & (u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7)&(heights>=min(a[1],b[1])-.2)&(heights<=max(a[1],b[1])+.2)
        cost=np.where(ok,np.abs(heights-lanes.reshape(-1,3)[:,1,None]),np.inf)
        chosen=cost.argmin(axis=1);values=heights[np.arange(len(chosen)),chosen]
        support=np.where(np.isfinite(cost.min(axis=1)),values,np.nan).reshape(support.shape)
    if not np.isfinite(support[:,[0,-1]]).all():return None
    def sweep(path,steps=False):
        starts=[];ends=[]
        for height in (.08,.3,.55,1.,1.4):
            begin=path[:,:-1,:].copy();end=path[:,1:,:].copy()
            if steps and height==.08:
                # A local <=20cm step is traversed at its raised foot height;
                # a tall face cannot be bypassed by raising the whole edge.
                raised=np.maximum(begin[:,:,1],end[:,:,1]);begin[:,:,1]=raised;end[:,:,1]=raised
            begin[:,:,1]+=height;end[:,:,1]+=height
            starts.extend(begin.reshape(-1,3));ends.extend(end.reshape(-1,3))
            # Cross-sections detect a wall contained between the two side
            # lanes, even when it is parallel to the direction of travel.
            left=path[1].copy();right=path[2].copy();left[:,1]+=height;right[:,1]+=height
            starts.extend(left);ends.extend(right)
        return segments_clear(tri,starts,ends)
    if np.isfinite(support).all() and np.max(np.abs(np.diff(support,axis=1)))<=max_step+1e-5:
        walk=lanes.copy();walk[:,:,1]=support
        if sweep(walk,True):return 'walk'
    # A separate capsule sweep follows an explicit jump arc. Never turn the
    # successful high-level check into an ordinary walk edge.
    arc=lanes.copy()
    if rise < -max_step:
        # Clear the ledge before descending: a straight diagonal from the
        # upper foot into the lower floor incorrectly cuts through its face.
        arc[:,:,1]=a[1]+np.clip((ts-.5)*2,0,1)*rise
    arc[:,:,1]+=np.sin(np.pi*ts)*(1.+max(0.,rise)*.25)
    if sweep(arc):return 'jump'
    return None


def graph(triangles,swim_flags,resolution=1.,min_y=0.,max_y=24.,return_kinds=False):
    normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);norm=np.linalg.norm(normal,axis=1)
    up=(normal[:,1]/np.maximum(norm,1e-10))>=.7
    cells={}
    for tri,swim in zip(triangles[up],swim_flags[up]):
        xz=tri[:,[0,2]];lo=np.ceil(xz.min(axis=0)/resolution).astype(int);hi=np.floor(xz.max(axis=0)/resolution).astype(int)
        if np.any(hi<lo):continue
        xx,zz=np.meshgrid(np.arange(lo[0],hi[0]+1),np.arange(lo[1],hi[1]+1));pts=np.column_stack((xx.ravel(),zz.ravel()))
        v0=xz[1]-xz[0];v1=xz[2]-xz[0];det=v0[0]*v1[1]-v0[1]*v1[0]
        if abs(det)<1e-8:continue
        d=pts*resolution-xz[0];u=(d[:,0]*v1[1]-d[:,1]*v1[0])/det;v=(v0[0]*d[:,1]-v0[1]*d[:,0])/det
        yy=tri[0,1]+u*(tri[1,1]-tri[0,1])+v*(tri[2,1]-tri[0,1])
        valid=(u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7)&(yy>=min_y-.001)&(yy<=max_y)
        for (x,z),y in zip(pts[valid],yy[valid]):
            key=(int(x),int(z),round(float(y)*10))
            # Coincident surfaces with any non-swim material stay conservative.
            old=cells.get(key);cells[key]=(float(y),bool(swim) and (old is None or old[1]))
    mesh=CollisionMesh(triangles);nodes=[];by_cell={}
    for (x,z,level),(y,swim) in sorted(cells.items()):
        # Keep separate walkable layers; reject insufficient headroom.
        if not mesh.clear((x*resolution,y+.05,z*resolution),(x*resolution,y+1.5,z*resolution),.001):continue
        center=np.array((x*resolution,y+.65,z*resolution))
        if not all(mesh.clear(center-axis,center+axis,.001) for axis in (np.array((.32,0,0)),np.array((0,0,.32)))):continue
        i=len(nodes);nodes.append([x*resolution,round(y,4),z*resolution,int(swim)]);by_cell.setdefault((x,z),[]).append(i)
    edges=[[] for _ in nodes];kinds={}
    for i,p in enumerate(nodes):
        x,z=round(p[0]/resolution),round(p[2]/resolution)
        for dx,dz in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            for j in by_cell.get((x+dx,z+dz),[]):
                q=nodes[j]
                if dx and dz and not all(any(abs(nodes[k][1]-p[1])<=.8 for k in by_cell.get(c,[])) for c in ((x+dx,z),(x,z+dz))):continue
                kind=edge_kind(mesh,p,q)
                if kind is None:continue
                edges[i].append(j)
                if kind!='walk':kinds[f'{i}:{j}']=kind
    return (nodes,edges,kinds) if return_kinds else (nodes,edges)


def central_component(edges,start,allowed):
    def reach(graph):
        seen={start};stack=[start]
        while stack:
            for q in graph[stack.pop()]:
                if q not in seen:seen.add(q);stack.append(q)
        return seen
    reverse=[[] for _ in edges]
    for p,links in enumerate(edges):
        for q in links:reverse[q].append(p)
    return reach(edges) & reach(reverse) & allowed


def build(stage,resolution):
    name=STAGES[stage];directory=ROOT/'work/arena/maps'/name
    manifest=json.loads((directory/'manifest.json').read_text());parts=[];swim=[]
    for a in manifest['actors']:
        for source in (directory/'sources'/a['actor']).glob('*.obj'):
            tri,flags=surfaces(source);matrix,translation=transform({'Rotate':a['rotate'],'Scale':a['scale'],'Translate':a['translate']})
            parts.append(tri@matrix.T+translation);swim.append(flags)
    triangles=np.concatenate(parts);nodes,edges,kinds=graph(triangles,np.concatenate(swim),resolution,return_kinds=True)
    np.savez_compressed(directory/'human.npz',triangles=triangles)
    pack=unpack(ROOT/f'work/data/v720896/RomFS/Pack/Scene/Vss_{name}.pack.zs');banc=read(pack[f'Banc/Vss_{name}.bcett.byml'])
    def nearest(p):return min(range(len(nodes)),key=lambda i:sum((nodes[i][j]-p[j])**2*(4 if j==1 else 1) for j in range(3)))
    spawns={}
    for actor in manifest['banc_spawners']:
        target_id=next(link['Dst'] for link in actor['Links'] if link['Name']=='ToTarget_Cube')
        target=next(a for a in banc['Actors'] if a['Hash']==target_id);team=actor['TeamCmp']['Team'].lower()
        spawns[team]=dict(launch_locator=actor['Translate'],landing_locator=target['Translate'],ground=nodes[nearest(target['Translate'])][:3])
    def reachable(start):
        seen={start};stack=[start]
        while stack:
            for q in edges[stack.pop()]:
                if q not in seen:seen.add(q);stack.append(q)
        return seen
    (directory/'graph-candidate.json').write_text(json.dumps(dict(nodes=nodes,edges=edges,edge_kinds=kinds,spawns=spawns),separators=(',',':'))+'\n')
    print(json.dumps(dict(stage=stage,nodes=len(nodes),edges=sum(map(len,edges)),jump_edges=len(kinds))),flush=True)
    shared=reachable(nearest(spawns['alpha']['ground'])) & reachable(nearest(spawns['bravo']['ground']))
    if not shared:raise ValueError('no shared traversable area reachable from both spawn grounds')
    def shared_nearest(p):
        return min(shared,key=lambda i:(nodes[i][0]-p[0])**2+(nodes[i][2]-p[2])**2+.05*(nodes[i][1]-p[1])**2)
    center_index=shared_nearest((0,3,0));center=nodes[center_index][:3];regions={}
    returnable=central_component(edges,center_index,shared)
    def central_nearest(p):
        return min(returnable,key=lambda i:(nodes[i][0]-p[0])**2+(nodes[i][2]-p[2])**2+.05*(nodes[i][1]-p[1])**2)
    targets={'center':center,'west_lane':nodes[central_nearest((-18,center[1],0))][:3],
             'east_lane':nodes[central_nearest((18,center[1],0))][:3],
             'alpha_base':spawns['alpha']['ground'],'bravo_base':spawns['bravo']['ground']}
    high=[i for i in returnable if abs(nodes[i][0])<25 and abs(nodes[i][2])<25]
    targets['central_high']=nodes[max(high,key=lambda i:(nodes[i][1],-math.hypot(nodes[i][0],nodes[i][2])))][:3]
    for label,p in targets.items():
        regions[label]=dict(center=p,radius=6.,kind='experimental geometry label')
    data=dict(schema='arena.map.v1',stage_id=stage,name=name,resolution=resolution,nodes=nodes,edges=edges,
              regions=regions,spawns=spawns,edge_kinds=kinds,omitted=manifest['omitted'],
              scope=dict(min_y=0.,max_y=24.,max_rise=.8,max_step=.2,max_drop=3.5,body_radius=.3,sweep_spacing=.2,
                         sweep_heights=[.08,.3,.55,1.,1.4],jump_arc_height=1.,central_returnable_nodes=len(returnable),
                         region_selection="central lanes/high require a return path; one-way sinks remain in graph",
                         description='Static conservative graph; swim flag is material potential, never live ink'))
    (directory/'navigation.json').write_text(json.dumps(data,separators=(',',':'))+'\n')
    print(json.dumps(dict(stage=stage,name=name,nodes=len(nodes),edges=sum(map(len,edges)),jump_edges=len(kinds),regions=regions,spawns=spawns)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',type=int,choices=STAGES,nargs='+',default=list(STAGES));parser.add_argument('--resolution',type=float,default=1.)
    args=parser.parse_args()
    if not .5<=args.resolution<=2:raise ValueError('resolution must be .5..2')
    for stage in args.stage:build(stage,args.resolution)
