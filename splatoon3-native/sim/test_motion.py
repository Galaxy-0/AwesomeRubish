"""Equation parity and support-plane regressions, independent of fitted data."""
import copy
import unittest

import numpy as np

from .identify import MODES
from .motion import MotionModel
from .terrain import Mesh, Terrain
from .test_core import fixture


def model_fixture():
    return MotionModel(dict(schema='sim.motion.v2', modes={name: dict(
        speed=.1 + index*.01, deadzone=.2, exponent=1.4, acceleration=.01, braking=.02)
        for index, name in enumerate(MODES)}, camera=dict(stick_deadzone=.2, stick_gain=.03,
        gyro_gain=.25, pitch_gain=.12, heading_rate=.15), jump=dict(gravity=.008, jump_speed=.12)))


class MotionTests(unittest.TestCase):
    def test_scalar_batch_equations_match_all_modes(self):
        model = model_fixture()
        rng = np.random.default_rng(13)
        velocity = rng.uniform(-.2, .2, (120, 2))
        sticks = rng.uniform(-1, 1, (120, 2))
        yaw = rng.uniform(-np.pi, np.pi, 120)
        modes = np.arange(120) % 6
        multipliers = rng.uniform(.8, 1.3, 120)
        actual, targets = model.batch_advance(velocity, sticks, yaw, modes, multipliers)
        for i in range(120):
            v = np.array([velocity[i, 0], 0., velocity[i, 1]])
            expected, target = model.advance(v, sticks[i], yaw[i], MODES[modes[i]], multipliers[i])
            np.testing.assert_allclose(actual[i], expected, atol=1e-15)
            np.testing.assert_allclose(targets[i], target, atol=1e-15)

    def test_support_plane_is_not_a_wall_and_wall_still_blocks(self):
        base = fixture()
        tri = [[[-5, 0, 0], [5, 5, 10], [5, 0, 0]],
               [[-5, 0, 0], [-5, 5, 10], [5, 5, 10]]]
        mesh = Mesh(tri)
        terrain = Terrain(base.atlas, mesh, mesh)
        p = np.array([1., 1., 2.])
        q = terrain.move(p, [0., 0., .1], support_aware=True)
        self.assertGreater(q[2], p[2])
        self.assertAlmostEqual(q[1], q[2]*.5)
        wall = fixture(wall=True)
        q = wall.move([1., 0., 2.68], [0., 0., .1], support_aware=True)
        self.assertLess(q[2], 2.71)

    def test_coefficients_reject_invalid_deadzone(self):
        data = copy.deepcopy(model_fixture().data)
        data['modes']['human']['deadzone'] = 1.
        with self.assertRaises(ValueError): MotionModel(data)


if __name__ == '__main__':
    unittest.main()
