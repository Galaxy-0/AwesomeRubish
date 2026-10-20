"""Offline mechanic/information regression tests; local parameters required."""
from dataclasses import replace
import math
import unittest

import numpy as np

from arena.lib.atlas import MapAtlas
from rl.loadout import uniform_loadout
from .engine import Assumptions, BatchSimulator, Simulator, neutral, segment_distance
from .interfaces import ParallelEnv
from .parameters import Parameters
from .terrain import Mesh, Paint, Terrain


def fixture(wall=False, upper=False):
    triangles = [[[-30, 0, -30], [30, 0, -30], [30, 0, 30]],
                 [[-30, 0, -30], [30, 0, 30], [-30, 0, 30]]]
    if wall:
        triangles += [[[0, 0, 3], [0, 10, 3], [10, 10, 3]],
                      [[0, 0, 3], [10, 10, 3], [10, 0, 3]]]
    nodes = [[x, y, z, True] for y in ([0, 5] if upper else [0])
             for x in range(-25, 26) for z in range(-25, 26)]
    data = dict(schema='arena.map.v1', nodes=nodes, edges=[[] for _ in nodes],
                regions={}, spawns={k: {'ground': p} for k, p in
                [('alpha', [1, 0, 0]), ('bravo', [1, 0, 6])]}, resolution=1.)
    mesh = Mesh(triangles)
    return Terrain(MapAtlas(data), mesh, mesh)


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.params = Parameters.local()
        cls.flat = fixture()

    def env(self, **kwargs):
        return Simulator(parameters=self.params, terrain=kwargs.pop('terrain', self.flat), **kwargs)

    def pair(self, a=None, b=None):
        return {'player_0': a or neutral(), 'player_1': b or neutral()}

    def shoot(self, env, hold=1, settle=30):
        a = neutral()
        a['buttons'][0] = 1
        env.step(self.pair(a), hold, observe=False)
        env.step(self.pair(), settle, observe=False)

    def test_parameter_units_and_capsule(self):
        self.assertAlmostEqual(self.params.swing['InkConsume'], .052, places=6)
        self.assertEqual(self.params.weapon['BulletSaberVerticalParam']['DamageParam']['HitDamage'], 700)
        self.assertAlmostEqual(self.params.target_capsule['Radius'], .35)

    def test_light_full_adjacent_boundary_and_damage(self):
        for hold, expected in ((1, .35), (20, .35), (21, .7)):
            e = self.env()
            e.players[0].yaw = e.players[0].heading = 0.
            self.shoot(e, hold)
            direct = sum(v['amount'] for v in e.events if v['kind'] == 'damage' and v['cause'] == 'ink_blade')
            self.assertAlmostEqual(direct, expected, places=6)
            self.assertEqual(e.events[0]['full'], hold == 21)

    def test_contact_and_ink_blade_sum(self):
        e = self.env()
        e.players[0].yaw = 0.
        e.players[1].position[2] = 1.8
        self.shoot(e)
        self.assertAlmostEqual(e.players[1].hp, .45, places=6)

    def test_no_charge_keep_and_emerge_boundary(self):
        for hold, full in ((25, False), (26, True)):
            e = self.env()
            e.paint.disk(e.players[0].position, 2., 0)
            swim = neutral()
            swim['buttons'][1] = 1
            e.step(self.pair(swim))
            self.shoot(e, hold)
            releases = [v for v in e.events if v['kind'] == 'release']
            self.assertEqual(releases[0]['full'], full)
        e = self.env()
        a = neutral(); a['buttons'][0] = 1
        e.step(self.pair(a), 21)
        a['buttons'][1] = 1
        e.step(self.pair(a))
        e.step(self.pair(), 15)
        self.assertFalse(any(v['kind'] == 'release' for v in e.events))

    def test_wall_stops_motion_blade_contact_and_paint(self):
        e = self.env(terrain=fixture(wall=True))
        e.players[0].yaw = 0.
        self.shoot(e, 21)
        self.assertEqual(e.players[1].hp, 1.)
        a = neutral(); a['sticks'][1] = 1.
        e.step(self.pair(a), 100)
        self.assertLess(e.players[0].position[2], 2.71)
        self.assertEqual(e.paint.at((1, 0, 6)), -1)

    def test_paint_layers_repaint_and_scoring_denominator(self):
        t = fixture(upper=True)
        paint = Paint(t)
        self.assertGreater(paint.disk((1, 0, 0), 2., 0), 0.)
        self.assertEqual(paint.at((1, 5, 0)), -1)
        self.assertEqual(paint.disk((1, 0, 0), 2., 0), 0.)
        self.assertGreater(paint.disk((1, 0, 0), 2., 1), 0.)
        self.assertEqual(paint.ratios()[0], 0.)
        self.assertLess(sum(paint.ratios()), 1.)

    def test_ink_refill_enemy_floor_and_jump(self):
        e = self.env()
        e.players[0].ink = .01
        self.shoot(e, 21)
        self.assertTrue(any(v['kind'] == 'dry' for v in e.events))
        p = e.players[0]
        e.paint.disk(p.position, 4, 0)
        swim = neutral(); swim['buttons'][1] = 1
        before = p.ink
        e.step(self.pair(swim), 30)
        self.assertGreater(p.ink - before, .15)
        e.paint.disk(p.position, 4, 1)
        e.step(self.pair(), 300)
        self.assertAlmostEqual(p.hp, .6)
        self.assertTrue(p.alive)
        jump = neutral(); jump['buttons'][4] = 1
        e.step(self.pair(jump)); e.step(self.pair(), 40)
        self.assertAlmostEqual(p.position[1], 0.)
        self.assertTrue(p.grounded)

    def test_trade_respawn_and_spawn_protection(self):
        e = self.env(assumptions=replace(Assumptions(), respawn_frames=20))
        e.players[0].yaw = 0.; e.players[1].yaw = math.pi
        for p in e.players: p.hp = .3; p.hurt_at = 0
        a = neutral(); a['buttons'][0] = 1
        e.step(self.pair(a, a)); e.step(self.pair(), 15)
        self.assertTrue(all(not p.alive for p in e.players))
        e.step(self.pair(), 20)
        self.assertTrue(all(p.alive and p.hp == 1. for p in e.players))
        e._damage(0, 1., 1, 'test')
        self.assertTrue(e.players[0].alive)

    def test_information_boundary_last_seen_and_copy(self):
        e = self.env()
        e.players[0].heading = 0.
        e._observations = None
        # Reset projector since reset() already issued frame 0.
        e.step(self.pair())
        obs = e.observations()['player_0']
        self.assertTrue(obs['enemies'][0]['visible'])
        self.assertNotIn('hp', obs['enemies'][0])
        self.assertNotIn('paint', obs)
        e.paint.disk(e.players[1].position, 2, 1)
        swim = neutral(); swim['buttons'][1] = 1
        e.step(self.pair(b=swim))
        hidden = e.observations()['player_0']['enemies'][0]
        self.assertFalse(hidden['visible'])
        self.assertIsNone(hidden['position'])
        self.assertIsNotNone(hidden['last_seen_position'])
        obs['own']['position'][0] = 999
        self.assertNotEqual(e.players[0].position[0], 999)

    def test_determinism_batch_and_step_budget(self):
        batch = BatchSimulator(2, parameters=self.params, terrain=self.flat, duration_frames=10)
        a = neutral(); a['sticks'][0] = .6
        batch.step([self.pair(a)] * 2, 10)
        np.testing.assert_array_equal(batch.envs[0].players[0].position, batch.envs[1].players[0].position)
        with self.assertRaises(ValueError): batch.envs[0].step(self.pair())
        with self.assertRaises(ValueError): batch.envs[0].step(self.pair(), 0)
        env = ParallelEnv(parameters=self.params, terrain=self.flat, duration_frames=1)
        env.reset(seed=4)
        _, rewards, terms, truncs, _ = env.step(self.pair())
        self.assertEqual(sum(rewards.values()), 0.)
        self.assertTrue(all(terms.values()))
        self.assertFalse(any(truncs.values()))

    def test_gear_anchors_complete_swings(self):
        base = uniform_loadout()
        tuned = uniform_loadout('ink_saver_main')
        tuned['head'] = dict(main='swim_speed_up', subs=['swim_speed_up'] * 3)
        for loadout, expected in ((base, 19), (tuned, 31)):
            e = self.env(loadouts=[loadout, base])
            p = e.players[0]
            p.pitch = .9  # shoot into air
            # Keep cycle below recovery-stop, stop at first full-cost failure.
            count = 0
            for _ in range(40):
                self.shoot(e, 1, 29)
                if any(v['kind'] == 'dry' for v in e.events): break
                count += 1
            self.assertEqual(count, expected)

    def test_segment_distance_crossing_and_parallel(self):
        v = lambda x: np.array(x, float)
        self.assertAlmostEqual(segment_distance(v([0, 0, 0]), v([2, 0, 0]), v([1, -1, 0]), v([1, 1, 0])), 0.)
        self.assertAlmostEqual(segment_distance(v([0, 0, 0]), v([2, 0, 0]), v([0, 1, 0]), v([2, 1, 0])), 1.)


if __name__ == '__main__':
    unittest.main()
