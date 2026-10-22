"""Read-only search of bounded captured parents for an actual rigid transform.

Identity/local caches are rejected unless their translation matches native
contact origin and their forward axis matches the native creation direction.
Candidates are evidence, not an automatic ownership/semantic certification.
"""
import argparse
import json
import re
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha
from tools.zipcaster_d4.analyze_contact import SNAP


def locate(path):
    d=json.loads(path.read_text())
    assert d['freeze_before']==d['freeze_after']
    log=Path(d['session'])/'player-0/host.log'
    captures={}
    for m in SNAP.finditer(log.read_text()):
        captures.setdefault(int(m[1]),{})[m[2]]=bytes.fromhex(m[3])
    result=[]
    for frame,blobs in sorted(captures.items()):
        if 'd4_params'not in blobs:continue
        param=np.frombuffer(blobs['d4_params'],dtype='<f4')
        origin=param[0x30//4:0x3c//4].astype(float)
        forward=param[0x3c//4:0x48//4].astype(float)
        forward/=np.linalg.norm(forward)
        candidates=[]
        for name in ['d4_engine','d4_physics_owner','d4_body','d4_box','d4_cylinder','d4_component']:
            if name not in blobs:continue
            array=np.frombuffer(blobs[name],dtype='<f4').astype(float)
            for offset in range(len(array)-11):
                row=array[offset:offset+12]
                if not np.isfinite(row).all():continue
                for layout in ['rows3x4','columns4x3','rotation9_translation3']:
                    if layout=='rows3x4':matrix=row.reshape(3,4);rotation=matrix[:,:3];translation=matrix[:,3]
                    elif layout=='columns4x3':matrix=row.reshape(4,3);rotation=matrix[:3,:].T;translation=matrix[3,:]
                    else:rotation=row[:9].reshape(3,3);translation=row[9:]
                    if np.linalg.norm(translation-origin)>.02:continue
                    if np.max(np.abs(rotation.T@rotation-np.eye(3)))>.02:continue
                    if abs(np.linalg.det(rotation)-1)>.02:continue
                    cosine=float(rotation[:,2]@forward)
                    candidates.append(dict(blob=name,offset=hex(offset*4),layout=layout,
                                           translation=translation.tolist(),rotation=rotation.tolist(),
                                           forward_cosine=cosine,direction_matches=cosine>.9998))
        result.append(dict(frame=frame,native_origin=origin.tolist(),native_forward=forward.tolist(),candidates=candidates))
    return dict(artifact=str(path.relative_to(ROOT)),artifact_sha256=sha(path),log_sha256=sha(log),frames=result,
                limits=['Bounded native captures, no new experiments or live memory scan.',
                        'A numeric matrix candidate still requires a static owner/transform-consumer link.'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--result',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('fresh output required')
    a.out.write_text(json.dumps(locate(a.result.resolve()),indent=2)+'\n')
