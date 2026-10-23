"""Mechanism regressions, synthetic data only; no trajectory fitting or training."""

import os
import tempfile
import unittest
import torch
from .test_env import flat, fixture_config
from .env import ParallelEnv, HP, INK, SUB, ARM, RESPAWN, PREV_ZR, GROUND, CREDIT
from .launch import LaunchModel


def opening():
    return dict(
        steer_start=1,
        steer_speed=0.02,
        respawn=dict(ready_delay=3, unlock_delay=5),
        stages={
            "1": dict(
                end_frame=4,
                ground_frame=3,
                squid_start=1,
                squid_end=3,
                knots=[[0, 0, 3, 0], [4, 0, 0, 0]],
            )
        },
    )


class DynamicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        cls.tmp = tempfile.TemporaryDirectory()
        flat(os.environ["RL_STAGE0_DATA"], cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def env(self):
        return ParallelEnv(
            self.tmp.name,
            fixture_config(decision_frames=1, loadout_mode="primary_only"),
        )

    def test_gun_zr_does_not_slow_submerged_movement(self):
        a, b = self.env(), self.env()
        for e in (a, b):
            e.paint[:] = 1
            e._observation = lambda *args: None
        x = torch.zeros((1, 2, 8), dtype=torch.int64)
        x[..., 1:3] = 4
        x[:, 1, 0] = 9
        x[:, 1, 4] = 1
        y = x.clone()
        y[:, 1, 3] = 1
        for _ in range(10):
            a.step(x)
            b.step(y)
        torch.testing.assert_close(a.state[..., :6], b.state[..., :6])
        self.assertEqual(b.state[0, 1, SUB].item(), 1)

    def test_jump_exits_submerged_before_ink_regeneration(self):
        e = self.env()
        e.paint[:] = 0
        e.state[0, 0, INK] = 0.5
        e.state[0, 0, SUB] = 1
        x = torch.zeros((1, 2, 8), dtype=torch.int64)
        x[..., 1:3] = 4
        x[0, 0, 4] = 1
        x[0, 0, 5] = 1
        e.step(x)
        self.assertEqual(e.state[0, 0, SUB].item(), 0)
        self.assertEqual(e.state[0, 0, GROUND].item(), 0)
        self.assertAlmostEqual(e.state[0, 0, INK].item(), 0.5 + 1 / 600, places=6)

    def test_ready_launcher_waits_for_fresh_zr_not_held_zr(self):
        e = self.env()
        model = LaunchModel(opening(), e.device)
        s = e.state.clone()
        s[..., ARM] = -2
        s[..., RESPAWN] = 0
        s[..., HP] = 0
        s[..., PREV_ZR] = 1
        t = s.clone()
        a = torch.zeros((1, 2, 8), dtype=torch.int64)
        a[..., 3] = 1
        age, active, launch = model.apply(
            s, t, a, torch.zeros((1, 2), dtype=torch.bool)
        )
        self.assertFalse(active.any())
        self.assertFalse(launch.any())
        self.assertTrue((t[..., HP] == 1).all())
        torch.testing.assert_close(t[..., :3], model.path[0] * model.side[None])
        s[..., PREV_ZR] = 0
        t[..., CREDIT] = 0.8
        age, active, launch = model.apply(
            s, t, a, torch.zeros((1, 2), dtype=torch.bool)
        )
        self.assertTrue(launch.all())
        self.assertTrue(active.all())
        self.assertTrue((age == 0).all())
        self.assertTrue((t[..., CREDIT] == 0).all())

    def test_native_launcher_configuration_is_explicit(self):
        e = self.env()
        self.assertIsNone(e.launch)
        self.assertTrue((e.state[..., ARM] == -1).all())


if __name__ == "__main__":
    unittest.main()
