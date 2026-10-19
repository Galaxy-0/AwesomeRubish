#!/usr/bin/env python3
"""Regression for the native late-hit counterexample; this does not accept A6."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from analyze_a6_research import analyze


def fixture():
    # Derived numerical facts from the 2026-10-19 native comparison. A normal
    # released shot takes 19 frames to appear in target HP; the dive holds 18.
    def trial(label, damage, segments, base, submerged=False):
        before = {'player_0': dict(frame=base, ink_valid=1, ink=1.),
                  'player_1': dict(hp_valid=1, hp=1.)}
        motion = dict(form_squid=int(submerged), ground_contact=0)
        samples = [dict(frame=base+60, hp_target=1., motion=dict(form_squid=0, ground_contact=0)),
                   dict(frame=base+78, hp_target=1., motion=motion),
                   dict(frame=base+79, hp_target=1., motion=motion),
                   dict(frame=base+82, hp_target=1.-damage, motion=dict(form_squid=0, ground_contact=0))]
        return dict(label=label, target_hp_loss=damage, before=before, segments=segments,
                    positions=[[0., 3., 0.], [6., 3., 0.]], segment_feedback=samples)
    light = trial('light', .35, [[1, [0]], [1, []]], 0)
    charged = trial('charged-reference', .70, [[60, [0]], [1, []]], 100)
    charged['segment_feedback'][-1]['frame'] = 179
    held = trial('charged-dive-held', .35, [[60, [0]], [18, [0, 1]], [1, [0]], [1, []]], 200, True)
    released = trial('charged-dive-released', .70, [[60, [0]], [18, [1]], [1, []]], 400, True)
    return dict(probe_completed=True, errors=[], trials=[light, charged, held, released])


class ResearchAnalysis(unittest.TestCase):
    def evaluate(self, payload):
        with tempfile.TemporaryDirectory(prefix='a6-analysis-') as folder:
            p = Path(folder) / 'result.json'
            p.write_text(json.dumps(payload))
            return analyze(p)

    def test_late_seventy_damage_is_not_stored_charge_proof(self):
        result = self.evaluate(fixture())
        self.assertTrue(result['native_reference_valid'])
        self.assertEqual(result['reference_release_to_hp_sample_frames'], 19)
        held, released = result['comparisons']
        self.assertTrue(held['submerged'])
        self.assertFalse(held['stored_full_charge_hit_observed'])
        self.assertTrue(released['submerged'])
        self.assertAlmostEqual(released['damage_after_dive'], .70)
        self.assertIsNone(released['stored_full_charge_hit_observed'])
        self.assertEqual(released['status'], 'requires_independent_shot_timing')
        self.assertFalse(result['full_a6_passed'])

    def test_changed_pose_cannot_witness_a_held_charge(self):
        payload = copy.deepcopy(fixture())
        held = payload['trials'][2]
        held['positions'][0][0] = 4.
        held['segment_feedback'][-1]['hp_target'] = .30
        result = self.evaluate(payload)['comparisons'][0]
        self.assertFalse(result['reference_valid'])
        self.assertFalse(result['stored_full_charge_hit_observed'])

    def test_incomplete_native_run_is_rejected(self):
        payload = fixture()
        payload['probe_completed'] = False
        with self.assertRaises(ValueError):
            self.evaluate(payload)


if __name__ == '__main__':
    unittest.main()
