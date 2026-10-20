"""Causality, contact semantics and metric angle regression checks."""
import unittest

import numpy as np

from .corpus import Trace
from .engine import Simulator
from .horizon import angle_error, reset_native
from .parameters import Parameters
from .test_core import fixture


class HorizonTests(unittest.TestCase):
    def trace(self):
        trace = object.__new__(Trace)
        trace.states = np.full((21, 2, 12), np.nan)
        trace.available = np.full((21, 2), 99)
        for t in (0, 4, 8, 12, 16, 20):
            for role in range(2):
                trace.states[t, role] = [role+1., 0., t*.1, 0., 0., 0., 1., 1., 1., 0., 1., 0.]
                trace.available[t, role] = t+1
        trace.actions = np.zeros((20, 2, 13))
        trace.actions[:, :, 8] = 1
        trace.samples = [np.arange(0, 21, 4)]*2
        return trace

    def test_future_sample_not_used_for_velocity_or_position(self):
        trace = self.trace()
        # Sample at t=8 is not available to the reset until ACK=9.
        self.assertEqual(trace.past(8, 0).tolist(), [0, 4])
        env = Simulator(parameters=Parameters.local(), terrain=fixture())
        reset_native(env, trace, 8)
        expected = env.players[0].position.copy()
        trace.states[8:, :, :3] += 1000
        reset_native(env, trace, 8)
        np.testing.assert_array_equal(env.players[0].position, expected)
        self.assertAlmostEqual(expected[2], .8)

    def test_contact_zero_submerged_four_not_submerged(self):
        trace = self.trace()
        env = Simulator(parameters=Parameters.local(), terrain=fixture())
        reset_native(env, trace, 8)
        self.assertTrue(env.players[0].submerged)
        trace.states[4, 0, 9] = 4
        reset_native(env, trace, 8)
        self.assertFalse(env.players[0].submerged)

    def test_angular_difference_wraps_at_pi(self):
        self.assertAlmostEqual(angle_error(np.pi-.01, -np.pi+.01), .02)


if __name__ == '__main__':
    unittest.main()
