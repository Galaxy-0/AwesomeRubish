#!/usr/bin/env python3
"""Produce a small, asset-free evidence index from D2's local reductions."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(out):
    m = json.loads((ROOT/'work/d2/measurements.json').read_text())
    layers = json.loads((ROOT/'work/d2/map-analysis-full.json').read_text())
    result = dict(schema='inklab.d2.report.v1', date='2026-10-21', status='partial_blocked', full_d2_passed=False,
        fixture=dict(map='Yunohana', weapon=8000, max_concurrent_rooms=3, players_per_room=2,
                     pixels=True, clock='fixed60', loadout=m['inventory'][0]['loadouts'],
                     special_meter='Only actor0, test_only derivative; infinite except defense-full-v3 and death-long full.',
                     production_and_policy_changes=False),
        parameters=json.loads((ROOT/'work/d2/parameters.json').read_text()),
        native=dict(discovery=[{k:v for k,v in c.items() if k!='movement'} | dict(
                     first_motion_sample=c['movement']['first_motion_native_sample_frame'],
                     peak_segment_speed=c['movement']['max_segment_speed_units_per_second']) for c in m['discovery']],
            range_trials=[dict(case=c['case'],eye_to_intended_surface=c['eye_to_intended_surface'],
                               displacement=c['body_displacement'],peak_segment_speed=c['movement']['max_segment_speed_units_per_second'])for c in m['range_trials']],
            lifecycles=m['lifecycles'],
            main_weapon=dict(grounded_special_charge_frames={20:35,21:70},wall_start_charge36_damage=70,
                             mid_combo=m['mid_combo']['hp_decreases'],
                             mid_combo_charge_start_to_down_first_ack=150,
                             mid_combo_RS_to_down_first_ack=346,mid_combo_full_to_light_damage_observation_gap=95,
                             tested_successes=1,high_target_attempts=2,high_target_hits=0),
            incoming_damage=dict(normal_full=70,startup_full=70,attached_late_full=70,
                                 attached_early_HP_loss=0,early_contact_verified=False,
                                 conclusion='Late attachment and startup can take full70. Early no-HP-loss is unresolved, not invincibility proof.'),
            death=dict(first_dead_frame=4482,special_at_death=.469999999,special_after_respawn=.230000004,
                       return_to_special_origin=False,respawn_position=[-23.9,10.5,71.43],
                       caveat='N=1, full meter fixture; dead coordinates stale, no exact internal meter-loss rule inferred.'),
            wall_jump=dict(attach_y=5.27,peak_y=7.99073124,observed=True),
            flight_input=dict(R_release_25_then_ZR1='No extra main-weapon ink cost or detach; input not demonstrated accepted.',
                R_release_25_then_ZR21='No extra main-weapon ink cost; no full hit demonstrated.',
                R_release_70_then_ZR1='Approx .04 additional ink cost and fall from wall; main attack accepted after arrival.',
                limitations='Timing-specific; flight phase inferred from body motion, no native action enum.'),
            rehook='Second wall-origin launch moved body; intended surface not confirmed. During-flight retry room later RL_STALL.'),
        combos=[dict(id='full-light',damage=105,can_KO_100=True,native_verified='One stationary mid target only',
                     observed_charge_start_to_down=150,earliest_claim=False),
                dict(id='bomb-light',damage=95,can_KO_100=False,native_verified=False,
                     caveat='A6 bomb60 + isolated light35; no hook/contact damage included.'),
                dict(id='bomb-full',damage=130,can_KO_100=True,native_verified=False,
                     frames=None,caveat='Arithmetic only. R becomes hook during special; no alternate bomb input demonstrated.'),
                dict(id='airborne-high',damage=None,can_KO_100=None,native_verified=False,frames=None,
                     caveat='Two high-target attempts missed; do not assign a successful combo duration.')],
        maps=[dict(id=v['id'],wall_samples=v['wall_samples'],candidates=len(v['candidates']),
                   shortlist=v['shortlist'],native_verified_count=0,sources=v['sources']) for v in layers['maps']],
        blockers=[dict(id='native-hook-query-observability',
                       evidence=['Ceiling-solid setup blocked, invalid dependent trial.',
                                 'Fence ceiling, high ceiling, and rehook actual endpoints differ from intended surfaces.',
                                 'Two high-target shots miss despite full ink cost; mid fixture succeeds.'],
                       required='Read-only native hook hitpoint/action/armor state, then repeat ceiling/range and high-target control shots.'),
                  dict(id='paired-native-flight-retry-stall',
                       evidence=['surfaces-v3 player1 RL_STALL frame10784, active wait about120s, game remaining about23.9s.',
                                 'Driver cleanup completed; protection unchanged.'],
                       required='Isolated recorded flight-R2 replay with phase/PIA/frame-barrier instrumentation; no weakening watchdog.')],
        unresolved=['Exact hook muzzle-to-hit max distance and angular cutoff; wall positive/negative bracket only.',
                    'Floor/ceiling bind legality and material flag rule in native query.',
                    'Early travel/arrival armor HP, damage reduction or invulnerability windows.',
                    'Earliest wall-start full charge / attack-ready and control-unlock frames.',
                    'Bomb use during special and airborne high-target successful combos.',
                    'Native validation of three-map top static candidates; native fixture is not a ranked static point.'],
        raw_runs=[dict(name=r['name'],artifacts=r['artifacts'],driver_completed=r['driver_completed'],
                       errors=r['errors'],fixture_failures=r['fixture_failures'],sha256=r['sha256'])for r in m['inventory']],
        outputs={},source_provenance={},limits=m['limits']+layers['limits'])
    for path in [ROOT/'work/d2/measurements.json',ROOT/'work/d2/map-analysis-full.json',
                 ROOT/'showcase/data/zipcaster-layer.json',ROOT/'showcase/data/zipcaster-traces.json']:
        result['outputs'][str(path.relative_to(ROOT))]=dict(bytes=path.stat().st_size,sha256=sha(path))
    # Hash local collision inputs without copying any resource bytes into the report.
    for v in layers['maps']:
        directory=ROOT/f'work/arena/maps/{v["id"]}/sources'
        for path in sorted(directory.rglob('*')):
            if path.suffix in ('.obj','.json'):result['source_provenance'][str(path.relative_to(ROOT))]=sha(path)
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(out,out.stat().st_size)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=ROOT/'notes/d2-20261021.json')
    main(p.parse_args().out)
