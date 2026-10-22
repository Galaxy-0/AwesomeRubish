"""Regression: re-aim at forced target motion rather than the original foot."""
import math
import unittest
import numpy as np
from tools.zipcaster_d4.attack_sequence import sequence


class RecordingShots:
    def __init__(self):
        self.targets = []
        self.paths = []

    def best(self, source, target, style):
        self.targets.append(np.asarray(target).copy())
        return dict(yaw=math.atan2(target[0]-source[0], target[2]-source[2]),
                    native_pitch=0., lifetime=26 if style == 'full' else 6)

    def direction(self, yaw, pitch, style):
        return np.array([math.sin(yaw), 0., math.cos(yaw)]), 0.

    def evaluate(self, source, target, style, yaw, pitch, target_positions):
        self.paths.append(np.asarray(target_positions).copy())
        return dict(hit=True, assembly_uncertain=False, player_contact_age=2.,
                    damage=70 if style == 'full' else 35)


class SequenceTests(unittest.TestCase):
    def profiles(self):
        return {s: dict(frames=[0, 8, 48], distance=[0, .4, .7],
                        measured_until=48) for s in ['full', 'light']}

    def test_second_cast_reaims_after_first_forced_displacement(self):
        shots = RecordingShots()
        result = sequence(shots, np.zeros((160, 3)), [3., 0., 4.],
                          [(21, 'full'), (57, 'light')], self.profiles())
        self.assertEqual(result['kill_frame'], 74)
        np.testing.assert_allclose(shots.targets[0], [3, 0, 4])
        self.assertGreater(np.linalg.norm(shots.targets[1] - shots.targets[0]), .4)
        # The path provided to collision is the moving capsule, not a repeated
        # snapshot of either the initial or the re-aimed position.
        self.assertGreater(np.linalg.norm(shots.paths[1][-1] - shots.paths[1][0]), 0)
        self.assertEqual(result['uncertainties'], [])

    def test_unmeasured_recoil_tail_remains_unknown(self):
        result = sequence(RecordingShots(), np.zeros((220, 3)), [3., 0., 4.],
                          [(21, 'full'), (100, 'light')], self.profiles())
        self.assertTrue(any('unmeasured recoil tail' in x for x in result['uncertainties']))
        self.assertFalse(result['native_contact_verified'])


if __name__ == '__main__':
    unittest.main()
