#!/usr/bin/env python3
"""Join coordinator-only D2B snapshots without promoting stale hit data.

Input is decode_sensors.py output; output is numerical evidence under work/.
No guest memory is accessed here. Native process/frame identities are retained.
"""
import argparse
import json
from pathlib import Path


def transform(matrix, vector, point=True):
    if matrix is None or vector is None:
        return None
    return [sum(matrix[4*i+j]*vector[j] for j in range(3)) +
            (matrix[4*i+3] if point else 0) for i in range(3)]


def reduce_group(rows):
    by_kind={row['kind']:row for row in rows}
    hook=by_kind.get('superhook')
    if hook is None:
        return None
    phase=hook['state_native']
    matrix=by_kind.get('surface_matrix',{}).get('matrix_3x4')
    bound=phase in (2,3) and matrix is not None
    armor=by_kind.get('component_3ae8',{})
    return dict(schema='inklab.d2b.evidence.v1',process=hook['process'],
        native_frame=hook['native_frame'],slot=hook['slot'],readonly=True,
        state_native=phase,state_name=hook['state_name'],
        hook_tip_world=hook['position_98_candidate'] if phase==1 else None,
        bind_witness=bound,
        anchor_world=transform(matrix,hook['position_98_candidate']) if bound else None,
        hit_normal_world=transform(matrix,hook['normal_a4_candidate'],False) if bound else None,
        bound_actor_id=hook['bind_object_id_candidate'] if bound else None,
        bound_actor_id_semantics='Native runtime actor ID, not static mesh face index',
        surface_matrix=matrix if bound else None,
        cached_hit_not_current=not bound,
        native_attachment_byte_396a=hook['phase_flags_candidate'][0],
        armor_flags_native=armor.get('armor_flags_native'),
        armor_hp_native=armor.get('armor_hp_native'),
        body_hp_native=by_kind.get('damage',{}).get('hp_native'),
        collision_mask_21d_native=by_kind.get('component_11cc0',{}).get('raw_mask_21d'),
        uncertainty='4-present sampling. Wait retains old hit fields; no current anchor claimed. '
                    'Armor flags/collision mask are raw native values, not a damage multiplier.')


def main(args):
    args.out.parent.mkdir(parents=True,exist_ok=True)
    key=None;group=[];count=0
    with args.source.open() as source,args.out.open('w') as output:
        def emit():
            nonlocal count
            result=reduce_group(group)
            if result is not None:
                output.write(json.dumps(result,allow_nan=False,separators=(',',':'))+'\n');count+=1
        for line in source:
            row=json.loads(line);newkey=(row['process'],row['native_frame'])
            if key!=newkey:
                emit();group=[];key=newkey
            group.append(row)
        emit()
    print(json.dumps(dict(rows=count,output=str(args.out))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    main(p.parse_args())
