"""Offline acceptance units with a synthetic floor, not distributed game data.

RL_STAGE0_DATA points to a private export for numerical parameter loading.
Synthetic geometry is created in a TemporaryDirectory; no native process runs.
"""

import os, unittest, tempfile, shutil
from pathlib import Path
import numpy as np
import torch
from .contract import Config
from .env import (
    AGE,
    CHARGE,
    CREDIT,
    GAUGE,
    GROUND,
    HEADING,
    HP,
    HURT,
    INK,
    PHASE,
    PITCH,
    ParallelEnv,
    SUB,
    Y,
    YAW,
)


def flat(data, out):
    """Known geometry permits numerical tests independent of map raster errors."""
    pts = np.array(
        [(x, 0, z) for x in range(-25, 26) for z in range(-25, 26)], np.float32
    )
    ids = np.arange(len(pts)).reshape(51, 51, 1)
    vox = np.zeros((65, 25, 65), np.uint8)
    vox[:, 2, :] = 5
    normal = np.zeros((*vox.shape, 3), np.float16)
    normal[:, 2, :, 1] = 1
    np.savez_compressed(
        Path(out) / "map.npz",
        points=pts,
        paintable=np.ones(len(pts), bool),
        floors=np.zeros((51, 51, 1), np.float32),
        cell_ids=ids,
        grid_origin=np.array([-25, -25]),
        voxels=vox,
        normals=normal,
        planes=np.zeros(vox.shape, np.float32),
        voxel_origin=np.array([-32, -2, -32], np.float32),
        voxel_resolution=np.float32(1),
        spawn=np.array([[1, 0, 0], [1, 0, 6]], np.float32),
    )
    shutil.copyfile(Path(data) / "parameters.json", Path(out) / "parameters.json")


def fixture_config(**kw):
    # Explicitly synthetic calibration. Never written into native calibration.
    return Config(
        stick_plus5_radians_per_frame=0.04,
        camera_horizontal_fov_degrees=90,
        camera_vertical_fov_degrees=60,
        camera_distance=6.0,
        camera_target_height=2.2,
        camera_pitch_offset_radians=0.0,
        **kw,
    )


class EnvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        cls.temp = tempfile.TemporaryDirectory()
        data = os.environ.get("RL_STAGE0_DATA")
        if not data:
            raise ValueError(
                "Set RL_STAGE0_DATA to the current private export; no implicit stale work data"
            )
        flat(data, cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def env(self, **kw):
        e = ParallelEnv(
            self.temp.name,
            fixture_config(decision_frames=1, **kw),
            device=os.environ.get("RL_STAGE0_DEVICE", "cpu"),
        )
        e.state[..., YAW] = 0
        e.state[..., HEADING] = 0
        return e

    def neutral(self, e):
        a = torch.zeros((e.n, 2, 8), dtype=torch.int64, device=e.device)
        a[..., 1:3] = 4
        return a

    def frames(self, e, a, n):
        for _ in range(n):
            e.step(a)

    def shoot(self, e, n):
        a = self.neutral(e)
        a[:, 0, 3] = 1
        self.frames(e, a, n)
        a[:, 0, 3] = 0
        self.frames(e, a, 40)

    def test_compact_paint_matches_int64(self):
        reference = self.env()
        compact = self.env()
        reference.paint = reference.paint.long()
        reference.reset(seed=12)
        compact.reset(seed=12)
        for _ in range(24):
            a = reference.random_actions()
            left, right = reference.step(a), compact.step(a)
            torch.testing.assert_close(reference.state, compact.state, rtol=0, atol=0)
            torch.testing.assert_close(
                reference.paint, compact.paint.long(), rtol=0, atol=0
            )
            for key in left[0]:
                torch.testing.assert_close(left[0][key], right[0][key], rtol=0, atol=0)
            torch.testing.assert_close(left[1], right[1], rtol=0, atol=0)

    def test_52_two_shots(self):
        e = self.env()
        e.state[0, 1, :3] = torch.tensor([1.0, 0.0, 0.0])
        e.state[0, 0, :3] = torch.tensor([1.0, 0.0, 6.0])
        e.state[..., PITCH] = 0.0
        a = self.neutral(e)
        a[:, 1, 3] = 1
        self.frames(e, a, 7)
        self.assertAlmostEqual(e.state[0, 0, HP].item(), 0.48, places=5)
        self.frames(e, a, 9)
        self.assertEqual(e.state[0, 0, HP].item(), 0.0)

    def test_full70_light35(self):
        e = self.env()
        self.shoot(e, 21)
        self.assertAlmostEqual(e.state[0, 1, HP].item(), 0.3, places=5)
        self.shoot(e, 1)
        self.assertEqual(e.state[0, 1, HP].item(), 0.0)

    def test_charge_boundary(self):
        e = self.env()
        self.shoot(e, 20)
        self.assertGreaterEqual(e.state[0, 1, HP].item(), 0.60)
        self.assertLessEqual(e.state[0, 1, HP].item(), 0.65)

    def test_swim_heal_and_ink(self):
        e = self.env()
        e.paint[0] = 0
        e.state[0, 0, HP] = 0.2
        e.state[0, 0, INK] = 0
        e.state[..., HURT] = 0
        a = self.neutral(e)
        a[:, 0, 4] = 1
        self.frames(e, a, 90)
        self.assertAlmostEqual(e.state[0, 0, INK].item(), 0.5, places=5)
        self.assertAlmostEqual(e.state[0, 0, HP].item(), 0.45, places=5)
        self.assertEqual(e.state[0, 0, SUB].item(), 1)

    def test_zip_drain_charge_and_forced_return(self):
        e = self.env()
        e.state[0, 0, PHASE] = 2
        e.state[0, 0, AGE] = 31
        e.state[0, 0, GAUGE] = 1
        a = self.neutral(e)
        self.frames(e, a, 60)
        self.assertAlmostEqual(e.state[0, 0, GAUGE].item(), 0.9, places=5)
        a[:, 0, 3] = 1
        self.frames(e, a, 21)
        self.assertAlmostEqual(
            e.state[0, 0, GAUGE].item(), 0.9 - 0.035 - 0.078, places=5
        )
        a[:, 0, 3] = 0
        self.frames(e, a, 1)
        self.assertAlmostEqual(
            e.state[0, 0, GAUGE].item(), 0.9 - 22 / 600 - 0.078, places=5
        )
        e.state[0, 0, GAUGE] = 0.0001
        self.frames(e, a, 1)
        self.assertEqual(e.state[0, 0, PHASE].item(), 5)
        self.frames(e, a, 99)
        self.assertEqual(e.state[0, 0, PHASE].item(), 0)

    def test_attached_requires_b(self):
        e = self.env()
        e.state[0, 0, PHASE] = 4
        e.state[0, 0, GAUGE] = 1
        e.state[0, 0, Y] = 5
        e.state[0, 0, GROUND] = 0
        a = self.neutral(e)
        a[:, 0, 3] = 1
        self.frames(e, a, 21)
        self.assertEqual(e.state[0, 0, CHARGE].item(), 0)
        a[:, 0, 5] = 1
        self.frames(e, a, 1)
        a[:, 0, 5] = 0
        self.frames(e, a, 21)
        self.assertGreater(e.state[0, 0, CHARGE].item(), 0)

    def test_hook_flight_and_detach(self):
        e = self.env()
        e.state[0, 0, PHASE] = 2
        e.state[0, 0, AGE] = 31
        e.state[0, 0, GAUGE] = 1
        vox = e.geo.arrays["voxels"]
        vox[:, 3:12, 42] = 6
        e.geo.normal.reshape(*vox.shape, 3)[:, 3:12, 42, :] = torch.tensor(
            [0.0, 0.0, -1.0], device=e.device
        )
        e.geo.planes.reshape(vox.shape)[:, 3:12, 42] = -10.0
        a = self.neutral(e)
        a[:, 0, 6] = 1
        self.frames(e, a, 1)
        a[:, 0, 6] = 0
        self.frames(e, a, 1)
        self.assertEqual(e.state[0, 0, PHASE].item(), 3)
        self.assertAlmostEqual(
            e.state[0, 0, GAUGE].item(), 1 - 2 / 600 - 0.026666666, places=5
        )
        self.frames(e, a, 80)
        self.assertEqual(e.state[0, 0, PHASE].item(), 4)
        self.assertAlmostEqual(e.state[0, 0, 2].item(), 9.2, places=4)
        a[:, 0, 5] = 1
        self.frames(e, a, 1)
        self.assertEqual(e.state[0, 0, PHASE].item(), 2)
        self.assertGreater(e.state[0, 0, Y].item(), 1.3)

    def test_light_contact_and_second_attack(self):
        e = self.env()
        e.state[0, 1, 2] = 1.8
        self.shoot(e, 1)
        self.assertAlmostEqual(e.state[0, 1, HP].item(), 0.45, places=5)
        self.shoot(e, 1)
        self.assertEqual(e.state[0, 1, HP].item(), 0.0)

    def test_full_contact140_before_wave(self):
        e = self.env()
        e.state[0, 1, 2] = 1.8
        a = self.neutral(e)
        a[:, 0, 3] = 1
        self.frames(e, a, 21)
        a[:, 0, 3] = 0
        received = 0.0
        for _ in range(4):
            received += e.step(a)[4]["events"][0, 1, 0].item()
        self.assertAlmostEqual(received, 1.4, places=5)
        self.assertEqual(e.state[0, 1, HP].item(), 0.0)

    def test_expiry_cancels_unemitted_wave(self):
        from .env import DELAY

        e = self.env()
        e.state[0, 0, PHASE] = 2
        e.state[0, 0, AGE] = 31
        e.state[0, 0, GAUGE] = 0.00001
        e.state[0, 0, DELAY] = 1
        self.frames(e, self.neutral(e), 2)
        self.assertEqual(e.state[0, 0, PHASE].item(), 5)
        self.assertEqual(e.shots[0, 0, :, 10].sum().item(), 0)

    def test_obs_no_hidden_enemy(self):
        e = self.env()
        e.state[0, 1, SUB] = 1
        obs = e._observe(e.state, e.shots, e.paint, e.steps)
        self.assertFalse(
            bool(((obs["entities"][0, 0, :, 3] == 1) & obs["entity_mask"][0, 0]).any())
        )
        self.assertFalse(bool((obs["screen"][0, 0, :, :, 1] == 3).any()))
        self.assertEqual(
            set(obs), {"screen", "entities", "entity_mask", "hud", "minimap", "audio"}
        )

    def test_zero_sum_and_finish_freeze(self):
        e = self.env(duration_frames=4)
        a = self.neutral(e)
        self.frames(e, a, 4)
        s = e.state.clone()
        p = e.paint.clone()
        _, r, term, _, info = e.step(a)
        self.assertTrue(bool(term.all()))
        self.assertEqual(r.sum().item(), 0)
        torch.testing.assert_close(e.state, s)
        torch.testing.assert_close(e.paint, p)
        self.assertEqual(info["frame"].item(), 4)

    def test_damage_credit_not_reset_by_healing(self):
        e = self.env()
        e.state[0, 1, CREDIT] = 1.0
        self.shoot(e, 1)
        self.assertEqual(e.state[0, 1, CREDIT].item(), 1.0)


if __name__ == "__main__":
    unittest.main()
