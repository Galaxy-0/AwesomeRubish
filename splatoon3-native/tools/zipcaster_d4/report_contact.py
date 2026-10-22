"""Read actual four-frame local shapes and physics-fed world transforms."""
import argparse
import bisect
import json
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha
from tools.zipcaster_d4.analyze_contact import SNAP
from tools.zipcaster_d4.attack_geometry import contact_overlap,basis,xyz
from tools.zipcaster_d4.contact_shape import native_shape
from tools.zipcaster_d4.inspect_contact import inspect


def decode(path):
    d=json.loads(path.read_text())
    assert d['freeze_before']==d['freeze_after']
    log=Path(d['session'])/'player-0/host.log'
    captures={}
    for m in SNAP.finditer(log.read_text()):captures.setdefault(int(m[1]),{})[m[2]]=bytes.fromhex(m[3])
    parameters=json.loads((ROOT/'work/a6/parameters.json').read_text())
    cases=[]
    for r in d['records']:
        hist=r['history'];source_frames=[x['infos']['player_0']['frame']for x in hist]
        frames=[];style=r['style'];key='vertical'if style=='full'else'horizontal'
        shape=native_shape(parameters[key+'_contact']['ShapeParam'])
        offset=xyz(parameters['swing']['ShotSlashOffset_Vertical'if style=='full'else'ShotSlashOffset_L'])
        for f,blobs in sorted(captures.items()):
            if not r['before']['player_0']['frame']<f<=source_frames[-1]or'd4_engine'not in blobs:continue
            # Bound to this actor's native creation direction and engine parent,
            # not an arbitrary numeric matrix search.
            param=np.frombuffer(blobs['d4_params'],dtype='<f4').astype(float)
            engine=np.frombuffer(blobs['d4_engine'],dtype='<f4').astype(float)
            position=engine[0x25c//4:0x268//4]
            rotation=engine[0x268//4:0x28c//4].reshape(3,3)
            direction=param[0x3c//4:0x48//4];direction/=np.linalg.norm(direction)
            origin=param[0x30//4:0x3c//4]
            np.testing.assert_allclose(rotation.T@rotation,np.eye(3),atol=1e-5)
            np.testing.assert_allclose(rotation[:,2],direction,atol=1e-5)
            np.testing.assert_allclose(position,origin,atol=1e-5)
            i=max(0,bisect.bisect_right(source_frames,f)-1)
            info=hist[i]['infos'];enemy=info['player_1']['position'];source=np.array(info['player_0']['position'])
            yaw=float(np.arctan2(direction[0],direction[2]));elevation=float(np.arcsin(direction[1]))
            expected=basis(yaw,elevation)
            np.testing.assert_allclose(rotation,expected,atol=1e-5)
            box=np.frombuffer(blobs['d4_box'],dtype='<f4').astype(float)
            half=box[0xd8//4:0xe4//4];center=box[0xe8//4:0xf4//4]
            np.testing.assert_allclose(half,xyz(shape['BoxHalfExtents']),atol=1e-5)
            np.testing.assert_allclose(center,xyz(shape['BoxCenter']),atol=1e-5)
            if shape['HasCylinderShape']:
                cylinder=np.frombuffer(blobs['d4_cylinder'],dtype='<f4').astype(float)
                np.testing.assert_allclose(cylinder[0xd8//4:0xe4//4],xyz(shape['CylinderCenterA']),atol=1e-5)
                np.testing.assert_allclose(cylinder[0xe8//4:0xf4//4],xyz(shape['CylinderCenterB']),atol=1e-5)
                assert abs(cylinder[0xe4//4]-shape['CylinderRadius'])<1e-5
            frames.append(dict(frame=f,position=position.tolist(),rotation=rotation.tolist(),direction=direction.tolist(),
                               shape_kind='box+finite-cylinder'if shape['HasCylinderShape']else'box',
                               box_center=center.tolist(),box_half=half.tolist(),
                               cylinder_enabled=shape['HasCylinderShape'],
                               source=source.tolist(),enemy=enemy,
                               origin_errors=dict(yaw_only=float(np.linalg.norm(position-source-basis(yaw,0)@offset)),
                                                  direction_aligned=float(np.linalg.norm(position-source-rotation@offset))),
                               overlap={name:contact_overlap(position,rotation,shape,enemy,*body)
                                        for name,body in [('ColBullet',(.35,.35,1.30)),('Body-candidate',(.6,.6,1.30))]}))
        hp=[];last=r['before']['player_1']['hp']
        for h in hist:
            value=h['infos']['player_1']['hp']
            if last-value>.19:hp.append(dict(frame=h['infos']['player_0']['frame'],drop=round((last-value)*100,4)))
            last=value
        cases.append(dict(id=r['id'],style=style,requested_pose_errors=r['requested_pose_errors'],
                          paired_pose_eligible=r['paired_pose_eligible'],frames=frames,hp_edges=hp,
                          native_ko=not r['after']['player_1']['alive'],
                          measured_world_transform=bool(frames),contact_hit=any(x['overlap']['ColBullet']['hit']for x in frames)))
    return dict(artifact=str(path.relative_to(ROOT)),artifact_sha256=sha(path),log_sha256=sha(log),cases=cases)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,nargs='+',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('fresh output required')
    evidence=inspect(ROOT/'work/d2b/main.bin')
    a.out.write_text(json.dumps(dict(schema='inklab.d4.contact.world.readback.v1',static=evidence,
                   runs=[decode(p.resolve())for p in a.results],full_d4_passed=False,
                   limits=['Four-frame calc-entry transform; no post-physics collision callback claimed.',
                           'Native KO from100HP censors the damage magnitude;140 is the parameter value.',
                           'Target Body receiver is still an explicit candidate, not silently substituted.',
                           'Contact/projectile overlap and duplicate suppression must be resolved before universal combo credit.']),indent=2)+'\n')
