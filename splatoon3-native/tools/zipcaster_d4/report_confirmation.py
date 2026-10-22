"""Compact source-bound report of the finite, predeclared slash confirmation."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha


def report(ablation):
    data = json.loads(ablation.read_text())
    rows = []
    for run in data['runs']:
        path = ROOT/run['artifact']
        native = json.loads(path.read_text())
        assert native['freeze_before'] == native['freeze_after']
        meters=[(int(m[1]),int(m[2])) for m in re.finditer(r'D2B_CANONICAL frame=(\d+) slot=\d+ key=\d+ remaining=(-?\d+)',(Path(native['session'])/'player-0/host.log').read_text())]
        by_index = {r['index']: r for r in native['records']}
        for shot in run['shots']:
            row = by_index[shot['index']]
            edges = shot.get('native_large_hp_edges', [])
            expected = 70 if row['style'] == 'full' else 35
            native_hit = any(abs(e['drop']-expected) <= .15 for e in edges)
            no_birth = shot.get('no_birth', False)
            prior=[value for frame,value in meters if frame<=row['before']['player_0']['frame']]
            counter=row.get('native_counter_before',prior[-1]if prior else None)
            rows.append(dict(
                id=row['id'], artifact=run['artifact'], artifact_sha256=sha(path),
                source_sha256=native['source_sha256'], style=row['style'],
                predicted_hit=row['prediction']['hit'],
                assembly_uncertain=row['prediction']['assembly_uncertain'],
                exact_projectile_hp_edge=native_hit,
                comparison_defined=not no_birth,
                agrees=None if no_birth else row['prediction']['hit'] == native_hit,
                native_large_hp_edges=edges, native_pitch=row['native_pitch'],
                actual_source=shot.get('actual_source'), actual_enemy=shot.get('actual_enemy'),
                requested_pose_errors=row['requested_pose_errors'],
                paired_pose_eligible=row['paired_pose_eligible'],
                native_counter_before=counter,
                same_special_state_validated=bool(row.get('same_special_state_validated')),
                room_driver_completed=native.get('driver_completed',False),room_errors=native['errors'],
                muzzle_error=shot.get('muzzle_error')))
    defined = [r for r in rows if r['comparison_defined']]
    return dict(schema='inklab.d4.attack.confirm.report.v1', rows=rows,
                counts=dict(attempted=len(rows), comparisons=len(defined),
                            agree=sum(r['agrees'] for r in defined),
                            paired_pose_eligible=sum(r['paired_pose_eligible'] for r in rows),
                            same_special_state_validated=sum(r['same_special_state_validated']for r in rows),
                            TP=sum(r['predicted_hit'] and r['exact_projectile_hp_edge'] for r in defined),
                            TN=sum(not r['predicted_hit'] and not r['exact_projectile_hp_edge'] for r in defined)),
                ablation_sha256=sha(ablation), full_d4_passed=False,
                limits=['Finite single-slash mechanism check; not a stable hit rate or216-duel certification.',
                        'Placement failures recomputed at actual pose and excluded from identical-pose pairs.',
                        'Only35/70HP edges count as projectile hits; ink tick damage excluded.',
                        'Infinite only supplies another full gauge: native SuperHook duration still expires. Same-state gate is separate.',
                        'A completed slash in a later-expired room retains its own artifact/HP/source binding; room error remains visible.',
                        'Direct aim/infinite special are test-only; contact140 transform validation separate.'])


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--ablation', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise ValueError('fresh output required')
    a.out.write_text(json.dumps(report(a.ablation), indent=2)+'\n')
