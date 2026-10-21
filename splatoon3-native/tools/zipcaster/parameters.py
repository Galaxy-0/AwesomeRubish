#!/usr/bin/env python3
"""Selected local 11.3.0 values, with raw parameter entries kept in ignored work/."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.stage_collision import unpack
from tools.byml import read


def extract(out):
    source=ROOT/'work/data/v720896/RomFS/Pack/Params.pack.zs';entries=unpack(source)
    entry='Component/GameParameterTable/WeaponSpSuperHook.game__GameParameterTable.bgyml'
    raw=read(entries[entry])['GameParameters'];wp=raw['WeaponParam']
    result=dict(schema='inklab.d2.parameters.v1',build='11.3.0',
        special_id=3,weapon_id=8000,parameter_values=dict(
            duration_counter_frames=wp['SpecialTotalFrame'],hook_max_length=wp['MaxLengthHook'],
            hook_min_length_floor=wp['MinLengthHook_Floor'],hook_min_length_wall=wp['MinLengthHook_Wall'],
            shot_to_attack_wait_frames=wp['WaitFrameShot2Attack'],failed_shot_interval_frames=wp['ShotFailedIntervalFrm'],
            ink_capacity_ratio=wp['InkCapacityRt'],ink_per_hook=wp['InkConsume_Hook'],ink_per_second=wp['InkConsume_PerSec'],
            attack_initial_speed=wp['MoveSpeedAttack_Init'],attack_acceleration=wp['MoveAccAttack'],
            hook_projectile_speed=raw['BulletBombMoveParam']['SpawnSpeedZSpecUp'],
            hook_field_collision_radius=raw['HookCollisionParam']['InitRadiusForField'],
            hook_travel_player_radius=raw['BulletParam']['CollisionRadiusForPlayer'],
            hook_blast_distance_damage=raw['HookBlastParam']['DistanceDamage']),
        provenance=dict(path=str(source.relative_to(ROOT)),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            entry=entry,entry_sha256=hashlib.sha256(entries[entry]).hexdigest()),
        caveats=['Sparse parameter overrides; omitted values are unknown until native/default-code verification.',
                 'Internal counters are not measured input-to-action or return animation durations.',
                 'Raw damage units are not yet divided or presented as native damage evidence.',
                 'No assumption that paintability or swim material implies hook bind eligibility.'])
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=ROOT/'work/d2/parameters.json');args=p.parse_args();print(json.dumps(extract(args.out),ensure_ascii=False,indent=2))
