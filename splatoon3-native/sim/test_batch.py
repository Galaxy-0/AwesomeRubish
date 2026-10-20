"""Full-engine differential tests: batch motion must preserve combat semantics."""
import math
import unittest

import numpy as np

from .batch import VectorBatchSimulator
from .engine import BatchSimulator, neutral
from .parameters import Parameters
from .test_core import fixture
from .test_motion import model_fixture
from .weapon import WeaponModel


class BatchTests(unittest.TestCase):
    def test_batch_floor_matches_scalar_on_native_geometry(self):
        from .terrain import Terrain
        terrain = Terrain.load(1)
        points = terrain.points[::71]
        actual = terrain.human.floor_batch(points, points[:, 1]+.205, -30.)
        expected = [terrain.human.floor(p[0], p[2], p[1]+.205) for p in points]
        expected = np.array([np.nan if p is None else p for p in expected])
        np.testing.assert_allclose(actual, expected, atol=1e-9, equal_nan=True)

    def test_multi_game_state_and_damage_matches_scalar(self):
        kwargs = dict(parameters=Parameters.local(), terrain=fixture(wall=True),
                      motion_model=model_fixture(), weapon_model=WeaponModel(dict(
                          schema='sim.weapon.v2', damage_delay=4, contact_muzzle_anchor=True)), duration_frames=100)
        scalar, batch = BatchSimulator(4, **kwargs), VectorBatchSimulator(4, **kwargs)
        for pair in zip(scalar.envs, batch.envs):
            for env in pair:
                env.players[0].yaw = 0.
                env.players[1].position[2] = 1.8  # real contact + projectile opportunity
                env.players[1].yaw = math.pi
        rng = np.random.default_rng(101)
        damage_seen = False
        for frame in range(70):
            actions = []
            for game in range(4):
                a = {f'player_{i}': neutral() for i in range(2)}
                for role in range(2):
                    a[f'player_{role}']['sticks'][:2] = rng.uniform(-.5, .5, 2).tolist() if frame > 30 else [0., 0.]
                    a[f'player_{role}']['buttons'][0] = int(frame in (0, 31))
                    a[f'player_{role}']['buttons'][4] = int(frame == 40)
                actions.append(a)
            for env, action in zip(scalar.envs, actions): env.step(action, observe=False)
            batch.step(actions, observe=False)
            for a, b in zip(scalar.envs, batch.envs):
                self.assertEqual(a.events, b.events)
                damage_seen |= any(e['kind'] == 'damage' for e in a.events)
                for p, q in zip(a.players, b.players):
                    np.testing.assert_allclose(p.position, q.position, atol=1e-9)
                    np.testing.assert_allclose(p.velocity, q.velocity, atol=1e-9)
                    self.assertAlmostEqual(p.hp, q.hp, places=10)
                    self.assertAlmostEqual(p.ink, q.ink, places=10)
                    self.assertEqual((p.squid, p.grounded, p.alive), (q.squid, q.grounded, q.alive))
        self.assertTrue(damage_seen)


if __name__ == '__main__':
    unittest.main()
