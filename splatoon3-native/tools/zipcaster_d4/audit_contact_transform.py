"""Bind gate52 physics-consumer calls to a captured SaberSlash engine pointer.

No call is attributed merely because it lies in the diagnostic spatial box.
Only exact source-pointer(engine+0x25c) and rotation-pointer(engine+0x268)
matches supply a runtime transform-consumer witness.
"""
import argparse
import json
import re
import struct
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.zipcaster_d4.analyze_contact import SNAP
from tools.zipcaster_d3r.analyze_direction import sha

HEADER=re.compile(r'D4_TRANSFORM frame=(\d+) destination=(0x[0-9a-f]+) source=(0x[0-9a-f]+) rotation=(0x[0-9a-f]+) lr=([0-9a-f]+)')


def bind_calls(calls,engines):
    rows=[]
    for call in calls:
        engine=call['source']-0x25c
        if engine not in engines or call['rotation']!=engine+0x268:continue
        blobs=call['blobs']
        if not all(k in blobs for k in ['d4_transform_source','d4_transform_rotation']):continue
        p=np.frombuffer(blobs['d4_transform_source'],dtype='<f4').astype(float)
        r=np.frombuffer(blobs['d4_transform_rotation'],dtype='<f4').astype(float).reshape(3,3)
        contact=min(engines[engine],key=lambda c:abs(c['frame']-call['frame']))
        rows.append(dict(frame=call['frame'],nearest_contact_frame=contact['frame'],
            same_engine_source_and_rotation_pointers=True,position=p.tolist(),rotation=r.tolist(),
            position_error=float(np.linalg.norm(p-contact['position'])),
            rotation_max_error=float(np.max(np.abs(r-contact['rotation']))),
            scope='Function entry observes arguments before original setter. Exact pointer binding, not spatial proximity.'))
    return rows


def audit(path):
    d=json.loads(path.read_text()); log=Path(d['session'])/'player-0/host.log'
    calls=[]; active=None; contacts={}
    for line in log.read_text().splitlines():
        header=HEADER.search(line)
        if header:
            active=dict(frame=int(header[1]),destination=int(header[2],16),source=int(header[3],16),rotation=int(header[4],16),lr=int(header[5],16),blobs={})
            calls.append(active)
        snap=SNAP.search(line)
        if snap:
            if snap[2].startswith('d4_transform_'):
                if active is not None and active['frame']==int(snap[1]):active['blobs'][snap[2]]=bytes.fromhex(snap[3])
            else:contacts.setdefault(int(snap[1]),{})[snap[2]]=bytes.fromhex(snap[3])
    engines={}
    for frame, blobs in contacts.items():
        if 'd4_slash'not in blobs or'd4_engine'not in blobs:continue
        ptr=struct.unpack_from('<Q',blobs['d4_slash'],0x10)[0]
        a=np.frombuffer(blobs['d4_engine'],dtype='<f4').astype(float)
        engines.setdefault(ptr,[]).append(dict(frame=frame,position=a[0x25c//4:0x268//4],rotation=a[0x268//4:0x28c//4].reshape(3,3)))
    rows=bind_calls(calls,engines)
    return dict(artifact=str(path.relative_to(ROOT)),sha256=sha(path),log_sha256=sha(log),
        errors=d['errors'],events=[r['event']for r in d['events']],outcome=d['outcome'],
        all_bounded_calls=len(calls),contact_engines=len(engines),bound_consumer_calls=rows,
        limits=['No receiver/field-veto callback is observed by this gate.',
                'No call in a bounded diagnostic region is an absence of a transform globally.',
                'An entry witness does not itself certify final physics contact/damage acceptance.'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,nargs='+',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('fresh output required')
    a.out.write_text(json.dumps(dict(schema='inklab.d4.transform.consumer.audit.v1',runs=[audit(p.resolve())for p in a.results],source_sha256=sha(__file__)),indent=2)+'\n')
