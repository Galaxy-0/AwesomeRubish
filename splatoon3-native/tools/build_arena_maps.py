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


def graph(triangles,swim_flags,resolution=1.,min_y=0.,max_y=24.):
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
    edges=[[] for _ in nodes]
    for i,p in enumerate(nodes):
        x,z=round(p[0]/resolution),round(p[2]/resolution)
        for dx,dz in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            for j in by_cell.get((x+dx,z+dz),[]):
                q=nodes[j];rise=q[1]-p[1]
                if not -.0-3.5<=rise<=.7:continue
                if dx and dz:
                    if not all(any(abs(nodes[k][1]-p[1])<=.7 for k in by_cell.get(c,[])) for c in ((x+dx,z),(x,z+dz))):continue
                high=max(p[1],q[1]);start=(p[0],high+.35,p[2]);end=(q[0],high+.35,q[2])
                perpendicular=np.array([-(q[2]-p[2]),0.,q[0]-p[0]],float);perpendicular*=.3/np.linalg.norm(perpendicular)
                if not all(mesh.clear(np.array(start)+offset,np.array(end)+offset,.01) for offset in (np.zeros(3),perpendicular,-perpendicular)):continue
                edges[i].append(j)
    return nodes,edges


def build(stage,resolution):
    name=STAGES[stage];directory=ROOT/'work/arena/maps'/name
    manifest=json.loads((directory/'manifest.json').read_text());parts=[];swim=[]
    for a in manifest['actors']:
        for source in (directory/'sources'/a['actor']).glob('*.obj'):
            tri,flags=surfaces(source);matrix,translation=transform({'Rotate':a['rotate'],'Scale':a['scale'],'Translate':a['translate']})
            parts.append(tri@matrix.T+translation);swim.append(flags)
    triangles=np.concatenate(parts);nodes,edges=graph(triangles,np.concatenate(swim),resolution)
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
    shared=reachable(nearest(spawns['alpha']['ground'])) & reachable(nearest(spawns['bravo']['ground']))
    if not shared:raise ValueError('no shared traversable area reachable from both spawn grounds')
    def shared_nearest(p):
        return min(shared,key=lambda i:(nodes[i][0]-p[0])**2+(nodes[i][2]-p[2])**2+.05*(nodes[i][1]-p[1])**2)
    center=nodes[shared_nearest((0,3,0))][:3];regions={}
    targets={'center':center,'west_lane':nodes[shared_nearest((-18,center[1],0))][:3],
             'east_lane':nodes[shared_nearest((18,center[1],0))][:3],
             'alpha_base':spawns['alpha']['ground'],'bravo_base':spawns['bravo']['ground']}
    high=[i for i in shared if abs(nodes[i][0])<25 and abs(nodes[i][2])<25]
    targets['central_high']=nodes[max(high,key=lambda i:(nodes[i][1],-math.hypot(nodes[i][0],nodes[i][2])))][:3]
    for label,p in targets.items():
        regions[label]=dict(center=p,radius=6.,kind='experimental geometry label')
    data=dict(schema='arena.map.v1',stage_id=stage,name=name,resolution=resolution,nodes=nodes,edges=edges,
              regions=regions,spawns=spawns,omitted=manifest['omitted'],
              scope=dict(min_y=0.,max_y=24.,max_rise=.7,max_drop=3.5,body_radius=.3,
                         description='Static conservative graph; swim flag is material potential, never live ink'))
    (directory/'navigation.json').write_text(json.dumps(data,separators=(',',':'))+'\n')
    print(json.dumps(dict(stage=stage,name=name,nodes=len(nodes),edges=sum(map(len,edges)),regions=regions,spawns=spawns)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',type=int,choices=STAGES,nargs='+',default=list(STAGES));parser.add_argument('--resolution',type=float,default=1.)
    args=parser.parse_args()
    if not .5<=args.resolution<=2:raise ValueError('resolution must be .5..2')
    for stage in args.stage:build(stage,args.resolution)
