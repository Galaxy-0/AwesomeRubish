"""Decode only derived shape numbers from closed read-only contact logs."""
import argparse
import json
import re
import struct
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha
from tools.zipcaster_d4.attack_geometry import basis, contact_overlap
from tools.zipcaster_d4.contact_shape import native_shape

SNAP = re.compile(r'D2B_SNAPSHOT frame=(\d+) kind=(d4_\w+) [^\n]*data=([0-9a-f]+)')


def analyze(path):
    d = json.loads(path.read_text())
    assert d['freeze_before'] == d['freeze_after']
    log = Path(d['session'])/'player-0/host.log'
    captures = {}
    for m in SNAP.finditer(log.read_text()):
        captures.setdefault(int(m[1]), {})[m[2]] = bytes.fromhex(m[3])
    r = d['records'][0]
    target = r['before']['player_1']['position']
    parameter = json.loads((ROOT/'work/a6/parameters.json').read_text())['vertical_contact']['ShapeParam']
    shifted = native_shape(parameter)
    frames = []
    for f, blobs in sorted(captures.items()):
        row = dict(frame=f)
        if 'd4_params' in blobs:
            b = blobs['d4_params']
            origin = np.array(struct.unpack_from('<3f', b, 0x30))
            direction = np.array(struct.unpack_from('<3f', b, 0x3c))
            yaw = float(np.arctan2(direction[0], direction[2]))
            elevation = float(np.arctan2(direction[1], np.linalg.norm(direction[[0,2]])))
            row.update(origin=origin.tolist(), direction=direction.tolist(),
                       origin_kind='native creation parameters',
                       candidate_overlaps={str(angle): contact_overlap(origin,basis(yaw,angle),shifted,target)
                                           for angle in [0.,elevation]})
        else:
            row['origin'] = list(struct.unpack_from('<3f', blobs['d4_slash'], 0x110))
        if 'd4_box' in blobs:
            box, cylinder = blobs['d4_box'], blobs['d4_cylinder']
            row.update(box_half=list(struct.unpack_from('<3f',box,0xd8)),
                       box_center=list(struct.unpack_from('<3f',box,0xe8)),
                       cylinder_a=list(struct.unpack_from('<3f',cylinder,0xd8)),
                       cylinder_b=list(struct.unpack_from('<3f',cylinder,0xe8)),
                       cylinder_radius=struct.unpack_from('<f',cylinder,0xe4)[0])
            np.testing.assert_allclose(row['box_center'],[shifted['BoxCenter'][k] for k in 'XYZ'],atol=1e-6)
            np.testing.assert_allclose(row['cylinder_a'],[shifted['CylinderCenterA'][k] for k in 'XYZ'],atol=1e-6)
            np.testing.assert_allclose(row['cylinder_b'],[shifted['CylinderCenterB'][k] for k in 'XYZ'],atol=1e-6)
        frames.append(row)
    hp_edges=[]
    last = r['before']['player_1']['hp']
    for h in r['history']:
        value = h['infos']['player_1']['hp']
        if last-value > .19:
            hp_edges.append(dict(source_clock=h['infos']['player_0']['frame'],drop=round((last-value)*100,4)))
        last = value
    return dict(artifact=str(path.relative_to(ROOT)), artifact_sha256=sha(path),log_sha256=sha(log),
                case=r['id'], actual_source=r['before']['player_0']['position'],actual_enemy=target,
                requested_pose_errors=r['requested_pose_errors'],paired_pose_eligible=r['paired_pose_eligible'],
                hp_edges=hp_edges,native_ko=not r['after']['player_1']['alive'],frames=frames,
                world_transform_verified=False,
                limits=['Creation direction is observed; yaw-only vs direction-aligned world rotation are hypotheses.',
                        'Matrix at actor+d8 rejected: pointer region. Body local identity cache is not a world transform.',
                        '100HP KO is censored damage, consistent with contact140 parameter, not a direct measurement of140HP.',
                        'All records are calc entry; not claimed to be post-physics event timestamps.'])


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--results',type=Path,nargs='+',required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise ValueError('fresh output required')
    a.out.write_text(json.dumps(dict(schema='inklab.d4.contact.readback.v1',runs=[analyze(p.resolve())for p in a.results],full_d4_passed=False),indent=2)+'\n')
