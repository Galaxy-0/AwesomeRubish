"""Explain closed duel contacts using native transforms, without granting HP.

A volume intersection is only a collision candidate. Field-ray checks here
are competing hypotheses, not a newly asserted native damage rule.
"""
import argparse
import bisect
import json
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.zipcaster_d4.analyze_contact import SNAP
from tools.zipcaster_d4.attack_geometry import contact_overlap,xyz
from tools.zipcaster_d4.contact_shape import native_shape
from tools.zipcaster_d4.query_model import World
from tools.zipcaster_d3r.analyze_direction import sha


def audit(path, worlds):
    d=json.loads(path.read_text())
    assert d['freeze_before']==d['freeze_after']
    graph=d['point']['graph']
    if graph not in worlds:worlds[graph]=World(ROOT/graph)
    w=worlds[graph]
    log=Path(d['session'])/'player-0/host.log'
    captures={}
    for m in SNAP.finditer(log.read_text()):
        captures.setdefault(int(m[1]),{})[m[2]]=bytes.fromhex(m[3])
    steps=[json.loads(line)for line in (path.parent/'steps.jsonl').read_text().splitlines()]
    history=[dict(frame=row['infos']['player_0']['frame'],source=row['infos']['player_0']['position'],enemy=row['infos']['player_1']['position'])for row in steps]
    times=[r['frame']for r in history]
    frames=[]
    for frame, blobs in sorted(captures.items()):
        if 'd4_engine'not in blobs:continue
        engine=np.frombuffer(blobs['d4_engine'],dtype='<f4').astype(float)
        param=np.frombuffer(blobs['d4_params'],dtype='<f4').astype(float)
        rotation=engine[0x268//4:0x28c//4].reshape(3,3)
        origin=engine[0x25c//4:0x268//4]
        direction=param[0x3c//4:0x48//4]
        np.testing.assert_allclose(rotation.T@rotation,np.eye(3),atol=1e-5)
        np.testing.assert_allclose(rotation[:,2],direction,atol=1e-5)
        np.testing.assert_allclose(origin,param[0x30//4:0x3c//4],atol=1e-5)
        record=history[max(0,bisect.bisect_right(times,frame)-1)]
        enemy=np.array(record['enemy'])
        box=np.frombuffer(blobs['d4_box'],dtype='<f4').astype(float)
        # Match the actual box dimensions rather than assuming the combo style.
        key=min(['vertical','horizontal'],key=lambda key:np.linalg.norm(box[0xd8//4:0xe4//4]-xyz(w.shots.parameters[key+'_contact']['ShapeParam']['BoxHalfExtents'])))
        shape=native_shape(w.shots.parameters[key+'_contact']['ShapeParam'])
        np.testing.assert_allclose(box[0xe8//4:0xf4//4],xyz(shape['BoxCenter']),atol=1e-5)
        overlaps={label:contact_overlap(origin,rotation,shape,enemy,*body)for label,body in [('ColBullet',(.35,.35,1.30)),('Body-candidate',(.6,.6,1.30))]}
        heights=[.35,.8,1.3]
        clear=w.field.clear_pairs(origin,enemy+np.array([[0,h,0]for h in heights]))
        frames.append(dict(frame=frame,style=key,source=record['source'],enemy=enemy.tolist(),
            origin=origin.tolist(),rotation=rotation.tolist(),direction=direction.tolist(),
            overlap=overlaps,field_ray_heights=heights,field_ray_clear=clear.tolist(),
            scope='Native engine transform/shape at calc entry; target from adjacent readback. Field rays are diagnostic only.'))
    health=[]
    for row in steps:
        if row.get('label','').startswith('d4-combo'):
            info=row['infos']; health.append(dict(frame=info['player_0']['frame'],enemy_hp=info['player_1']['hp'],enemy_alive=info['player_1']['alive']))
    return dict(artifact=str(path.relative_to(ROOT)),sha256=sha(path),log_sha256=sha(log),
                point=d['point']['id'],frames=frames,health=health,outcome=d.get('outcome'),
                ideal_operation_fixture=d['ideal_operation_fixture'],full_d4_passed=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,nargs='+',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('fresh output required')
    worlds={};runs=[audit(path.resolve(),worlds)for path in a.results]
    a.out.write_text(json.dumps(dict(schema='inklab.d4.contact.duel.audit.v1',runs=runs,
        source_sha256=sha(__file__),limits=['Native volume intersection does not prove receiver acceptance or damage.',
        'An obstructed origin-to-target ray suggests filtering, but does not locate a native veto or prove a universal LOS rule.',
        'These are diagnostic cases, not a completed216 cohort or native probability estimate.']),indent=2)+'\n')
