#!/usr/bin/env python3
"""Summarize native research without treating input or missing state as success."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def analyze(path):
    result = json.loads(path.read_text())
    if not result['probe_completed'] or result['errors']:
        raise ValueError('native research did not complete cleanly')
    trials = {t['label']: t for t in result['trials']}
    light = trials['light']
    charged = trials['charged-reference']
    reference_valid = (abs(light['target_hp_loss'] - .35) < .02 and
                       abs(charged['target_hp_loss'] - .70) < .02)
    first_charge_hit = next((s['frame'] for s in charged['segment_feedback']
                             if s['hp_target'] < charged['before']['player_1']['hp'] - .1), None)
    reference_hit_latency = (None if first_charge_hit is None else
                             first_charge_hit - charged['segment_feedback'][0]['frame'])
    comparisons = []
    for label in ('charged-dive-held', 'charged-dive-released'):
        trial = trials[label]
        feedback = trial['segment_feedback']
        underwater = feedback[1]
        motion = underwater.get('motion') or {}
        submerged = motion.get('form_squid') == 1 and motion.get('ground_contact') == 0
        poses_match = all(math.dist(p, q) < .3 for p, q in
                          zip(charged['positions'], trial['positions']))
        own = trial['before']['player_0']
        target = trial['before']['player_1']
        valid = (reference_valid and poses_match and own['ink_valid'] and own['ink'] >= .117
                 and target['hp_valid'] and target['hp'] > .999)
        hp_after_dive = underwater['hp_target']
        # A shot which landed during the dive is not a stored-charge hit on
        # resurfacing. Read post-dive HP separately instead of whole-trial loss.
        post_dive_loss = max(0., hp_after_dive - min(s['hp_target'] for s in feedback[2:]))
        release_on_dive = 0 not in trial['segments'][1][1]
        # HP belongs to the target's later sample, not to the projectile's
        # spawn time. Releasing ZR while entering squid form may already shoot
        # before the transformation completes. An in-flight hit after exit
        # cannot witness a stored charge; it needs independent shot timing.
        storage_witness = (None if release_on_dive else
                           bool(valid and submerged and abs(post_dive_loss - .70) < .02))
        comparisons.append(dict(label=label, reference_valid=valid, submerged=submerged,
                                native_dive_motion=motion,
                                zr_released_on_dive=release_on_dive,
                                pre_dive_shot_may_still_be_in_flight=bool(release_on_dive),
                                damage_before_or_during_dive=target['hp'] - hp_after_dive,
                                damage_after_dive=post_dive_loss,
                                total_damage=trial['target_hp_loss'],
                                stored_full_charge_hit_observed=storage_witness,
                                status=('requires_independent_shot_timing' if release_on_dive else
                                        'full_charge_hit' if storage_witness else 'no_full_charge_hit')))
    return dict(full_a6_passed=False, native_reference_valid=reference_valid,
                light_damage=light['target_hp_loss'] * 100,
                charged_damage=charged['target_hp_loss'] * 100,
                reference_release_to_hp_sample_frames=reference_hit_latency,
                comparisons=comparisons, evidence=str(path.resolve()),
                evidence_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                caveat='This controlled input comparison alone is not proof about every possible native sequence.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path)
    args = parser.parse_args()
    output = analyze(args.result)
    target = args.result.with_name('analysis.json')
    target.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output, indent=2))
