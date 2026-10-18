#!/usr/bin/env python3
"""Extract local Turf static collision into ignored work/arena/maps; no downloads."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.byml import read

STAGES={1:'Yunohana',2:'District00',3:'Yagara'}


def unpack(path):
    b=subprocess.check_output(['zstd','-dc',str(path)])
    if b[:4]!=b'SARC':raise ValueError('expected SARC')
    h=struct.unpack_from('<H',b,4)[0];data=struct.unpack_from('<I',b,12)[0]
    count=struct.unpack_from('<H',b,h+6)[0];names=h+12+count*16+8
    result={}
    for i in range(count):
        _,name,lo,hi=struct.unpack_from('<4I',b,h+12+i*16)
        start=names+(name&0xffffff)*4
        key=b[start:b.index(b'\0',start)].decode()
        result[key]=b[data+lo:data+hi]
    return result


def transform(actor):
    x,y,z=actor.get('Rotate',[0,0,0]);cx,sx=math.cos(x),math.sin(x);cy,sy=math.cos(y),math.sin(y);cz,sz=math.cos(z),math.sin(z)
    rx=np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
    ry=np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])
    rz=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])
    return rz@ry@rx@np.diag(actor.get('Scale',[1,1,1])),np.array(actor.get('Translate',[0,0,0]))


def obj_triangles(path):
    materials=json.loads(path.with_suffix('.json').read_text());vertices=[];faces=[];group=None
    for line in path.open():
        if line.startswith('v '):vertices.append([float(v) for v in line.split()[1:4]])
        elif line.startswith('usemtl '):group=line.split()[1]
        elif line.startswith('f '):
            if group is None or group not in materials:raise ValueError('missing collision material')
            if 'Sight' in materials[group].get('col_disable_flags',[]):continue
            indices=[int(v.split('/')[0])-1 for v in line.split()[1:]]
            for i in range(1,len(indices)-1):faces.append([indices[0],indices[i],indices[i+1]])
    v=np.asarray(vertices,float)
    return v[np.asarray(faces,int)] if faces else np.empty((0,3,3))


def extract(stage,converter,config_dir):
    name=STAGES[stage];rom=ROOT/'work/data/v720896/RomFS';out=ROOT/f'work/arena/maps/{name}';out.mkdir(parents=True,exist_ok=True)
    scene=rom/f'Pack/Scene/Vss_{name}.pack.zs';pack=unpack(scene)
    banc=read(pack[f'Banc/Vss_{name}.bcett.byml'])
    manifest=dict(stage_id=stage,name=name,scene_sha256=hashlib.sha256(scene.read_bytes()).hexdigest(),
                  approximation='Turf Cmn/Pnt static meshes; no live moving geometry',actors=[],omitted=[])
    all_tri=[];cache={}
    for actor in banc['Actors']:
        if actor.get('Layer') not in ('Cmn','Pnt'):continue
        key=actor['Gyaml'].removeprefix('Work/Actor/').split('.')[0]
        if not key.startswith(('Fld_','Mpt_FldObj_','Mpt_GeneralCube','DObj_')):continue
        source=rom/f'Pack/Actor/{key}.pack.zs'
        if not source.exists():manifest['omitted'].append(dict(actor=key,reason='actor pack unavailable'));continue
        if key not in cache:
            contents=unpack(source);meshes=[]
            for entry,raw in contents.items():
                if not entry.endswith('.bphsh'):continue
                dest=out/'sources'/key/Path(entry).name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
                subprocess.run([str(converter),'-p',str(dest),'-o',str(dest.parent)],cwd=config_dir,
                               stdout=subprocess.DEVNULL,check=True,timeout=60)
                meshes.append(obj_triangles(dest.with_suffix('.obj')))
            cache[key]=np.concatenate(meshes) if meshes else np.empty((0,3,3))
        tri=cache[key];matrix,translation=transform(actor)
        all_tri.append(tri@matrix.T+translation)
        manifest['actors'].append(dict(actor=key,hash=actor['Hash'],triangles=len(tri),
                                       translate=actor.get('Translate',[0,0,0]),rotate=actor.get('Rotate',[0,0,0]),scale=actor.get('Scale',[1,1,1])))
        if not len(tri):manifest['omitted'].append(dict(actor=key,reason='no embedded Dcc collision'))
    triangles=np.concatenate(all_tri)
    if not len(triangles):raise ValueError('no collision triangles')
    np.savez_compressed(out/'sight.npz',triangles=triangles)
    manifest['triangles']=len(triangles);manifest['banc_spawners']=[a for a in banc['Actors'] if 'LocatorSpawner'==a['Gyaml'] and a.get('Layer') in ('Cmn','Pnt')]
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(stage=stage,triangles=len(triangles),actors=len(manifest['actors']),omitted=manifest['omitted'],out=str(out))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',type=int,choices=STAGES,nargs='+',default=list(STAGES))
    p.add_argument('--converter',type=Path,default=ROOT/'work/a3/tools/phive-converter')
    p.add_argument('--config-dir',type=Path,default=ROOT/'work/a3/tools/PhiveConverter')
    args=p.parse_args()
    for stage in args.stage:extract(stage,args.converter.resolve(),args.config_dir.resolve())
