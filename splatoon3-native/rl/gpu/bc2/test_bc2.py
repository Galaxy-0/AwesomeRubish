"""Causal sensor timing, no-feedback invariance, chunk alignment and event loss."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
from .model import Actor, Ensemble
from .observation import GPUInk, encode
from .train import loss, chunks
from ..bc.test_bc import BCTests


class BC2Tests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        torch.manual_seed(80)

    def encoded(self):
        raw, previous, v = BCTests().observation()
        return encode(raw, v, torch.zeros(1, 2), previous)

    def test_no_previous_action_leak_for_both_horizons(self):
        for horizon in [1, 8, 16]:
            model = Actor(64, horizon, False).eval()
            obs = self.encoded()
            one = model({k: x[None] for k, x in obs.items()}, model.initial(2))[0]
            obs["previous_actions"].fill_(1)
            two = model({k: x[None] for k, x in obs.items()}, model.initial(2))[0]
            torch.testing.assert_close(one, two, rtol=0, atol=0)

    def test_feedback_control_actually_has_feedback(self):
        m = Actor(64, 1, True)
        o = self.encoded()
        a = m.encode(o)
        o["previous_actions"].fill_(1)
        b = m.encode(o)
        self.assertFalse(torch.equal(a, b))

    def test_chunk_temporal_alignment(self):
        class Fake:
            def __init__(self):
                self.calls = 0

            def initial(self, n, d):
                return None

            def __call__(self, obs, h):
                self.calls += 1
                out = torch.full((1, 1, 3, 8, 17), -50.0)
                # Tick0 predicts [1,2,3]; next query predicts [2,3,4].
                for k in range(3):
                    out[0, 0, k, :, self.calls + k] = 50
                return out, None, h, None

        c = Ensemble(Fake(), 1, "cpu")
        self.assertTrue((c.act({"hud": torch.zeros(1, 10)}) == 1).all())
        self.assertTrue((c.act({"hud": torch.zeros(1, 10)}) == 2).all())

    def test_level_mask_does_not_expose_latch(self):
        obs = self.encoded()
        self.assertTrue(obs["action_mask"][:, 3:6, :2].all())
        self.assertFalse(obs["action_mask"][:, 3:6, 2:].any())
        self.assertEqual(obs["quality"].shape[-1], 446)

    def test_distribution_empty_entities_are_unknown_not_zero_shift(self):
        from .distribution import compare

        r = compare({"entities": np.ones((2, 7))}, {"entities": np.empty((0, 7))})
        self.assertIsNone(r["entities"][0]["ks"])
        self.assertIsNone(r["entities"][0]["gpu_mean"])
        self.assertEqual(r["entities"][0]["train_mean"], 1)

    def test_distribution_disjoint_support_and_constant_equality(self):
        from .distribution import compare

        r = compare(
            {"probe": np.array([[0, 2], [1, 2]])}, {"probe": np.array([[3, 2], [4, 2]])}
        )
        self.assertEqual([r["probe"][h]["ks"] for h in range(2)], [1, 0])

    def test_ordinal_camera_decoder_cancels_symmetric_fine_noise(self):
        class Fake:
            def initial(self, n, d):
                return None

            def __call__(self, obs, h):
                out = torch.full((1, 1, 1, 8, 17), -50.0)
                out[:, :, :, :, 0] = 0.0
                for head in (1, 2):
                    out[:, :, :, head, :] = -50.0
                    out[:, :, :, head, 3] = torch.log(torch.tensor(0.45))
                    out[:, :, :, head, 5] = torch.log(torch.tensor(0.44))
                    out[:, :, :, head, 4] = torch.log(torch.tensor(0.11))
                return out, None, h, None

        arg = Ensemble(Fake(), 1, "cpu", "argmax").act({"hud": torch.zeros(1, 10)})
        mean = Ensemble(Fake(), 1, "cpu", "expectation").act(
            {"hud": torch.zeros(1, 10)}
        )
        self.assertEqual(arg[0, 1:3].tolist(), [3, 3])
        self.assertEqual(mean[0, 1:3].tolist(), [4, 4])

    def test_event_weight_increases_gradient_for_changed_target(self):
        logits = torch.zeros(2, 1, 1, 8, 17, requires_grad=True)
        labels = torch.zeros(2, 1, 1, 8, dtype=torch.long)
        weight = torch.ones_like(labels, dtype=torch.float)
        weight[0, :, :, 3] = 5
        objective = loss(logits, labels, weight, torch.ones(8, 17))
        objective.backward()
        self.assertGreater(
            abs(logits.grad[0, 0, 0, 3, 0]), abs(logits.grad[1, 0, 0, 3, 0])
        )

    def test_future_chunks_do_not_cross_missing_native_frames(self):
        f = torch.arange(200) * 2
        f[65:] += 4
        starts = chunks(dict(frame=f), 64, 8)
        self.assertNotIn(0, starts)
        self.assertIn(96, starts)

    def test_gpu_snapshot_not_visible_until_after_capture_tick(self):
        # Avoid geometry: test the clock/cache without running a game or GPU.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            np.savez(
                path / "contract.npz",
                top=np.array([[0]]),
                points=np.array([[0, 0, 0]]),
                map_valid=np.ones((1, 1), bool),
                grid_origin=np.zeros(2),
            )
            np.savez(
                path / "bank.npz",
                packed=np.packbits(np.ones((1, 1), bool), axis=1),
                cells=1,
            )
            env = SimpleNamespace(
                device="cpu",
                paint=torch.tensor([[0.0]]),
                steps=torch.tensor([0]),
                n=1,
                state=torch.zeros(1, 2, 48),
                cfg=None,
            )
            env.state[:, :, 10] = 1
            sensor = GPUInk(path / "contract.npz", env, path / "bank.npz")
            sensor.overlay = lambda raw, state, cfg, color, valid, age: dict(
                color=color.clone(), valid=valid.clone()
            )
            raw = {"hud": torch.zeros(1, 2, 10)}
            _, v, age = sensor.observe(raw)
            self.assertFalse(v["valid"].any())
            env.steps.fill_(2)
            _, v, age = sensor.observe(raw)
            self.assertEqual(v["color"][0, 0, 0, 0], 1)
            env.paint.fill_(1)
            env.steps.fill_(30)
            _, v, age = sensor.observe(raw)
            self.assertEqual(v["color"][0, 0, 0, 0], 1)
            self.assertEqual(int(age[0, 0]), 29)
            env.steps.fill_(32)
            _, v, age = sensor.observe(raw)
            self.assertEqual(v["color"][0, 0, 0, 0], 2)
            self.assertEqual(int(age[0, 0]), 1)

    def test_native_charge_reservation_is_display_only(self):
        from ..env import CHARGE, INK

        # Exercise the same piecewise curve on the sensor without geometry work.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            np.savez(
                path / "contract.npz",
                top=np.array([[0]]),
                points=np.array([[0, 0, 0]]),
                map_valid=np.ones((1, 1), bool),
                grid_origin=np.zeros(2),
            )
            np.savez(
                path / "bank.npz",
                packed=np.packbits(np.ones((1, 1), bool), axis=1),
                cells=1,
            )
            e = SimpleNamespace(
                device="cpu",
                paint=torch.zeros(1, 1),
                steps=torch.tensor([0]),
                n=1,
                state=torch.zeros(1, 2, 48),
                cfg=None,
            )
            e.state[:, :, INK] = 1
            e.state[:, 0, CHARGE] = 21
            sensor = GPUInk(path / "contract.npz", e, path / "bank.npz")
            sensor.overlay = lambda *args: {}
            raw = {"hud": torch.zeros(1, 2, 10)}
            sensor.observe(raw)
            self.assertAlmostEqual(float(raw["hud"][0, 0, 0]), 0.883, places=5)
            self.assertEqual(float(e.state[0, 0, INK]), 1.0)


if __name__ == "__main__":
    unittest.main()
