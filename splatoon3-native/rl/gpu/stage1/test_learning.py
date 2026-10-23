"""Focused tests for masked actions, recurrent boundaries and PPO correctness."""

import os, tempfile, unittest
import torch
from ..test_env import flat, fixture_config
from ..env import ParallelEnv, GAUGE, PHASE, INK, PREV_R
from .policy import Policy, prepare
from .opponents import D4Defender
from .ppo import gae, update


class LearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        torch.manual_seed(11)
        cls.temp = tempfile.TemporaryDirectory()
        flat(os.environ["RL_STAGE0_DATA"], cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def env(self):
        return ParallelEnv(
            self.temp.name,
            fixture_config(loadout_mode="primary_only", decision_frames=2),
        )

    def test_unassisted_fall_is_not_opponent_kill(self):
        e = self.env()
        e.state[0, 0, 1] = -26.0
        e.state[0, 0, 14] = 0
        a = torch.zeros((1, 2, 8), dtype=torch.int64)
        a[:, :, 1:3] = 4
        _, reward, _, _, info = e.step(a)
        self.assertEqual(float(info["events"][0, 0, 1]), 1.0)
        self.assertEqual(float(info["events"][0, 0, 5]), 0.0)
        torch.testing.assert_close(reward, torch.zeros_like(reward))

    def test_mask_and_environment_defense(self):
        e = self.env()
        e.state[:, :, GAUGE] = 1
        e.state[:, :, PREV_R] = 1
        a = e.random_actions()
        a[:, :, 6:] = 1
        e.step(a)
        self.assertTrue((e.state[:, :, PHASE] == 0).all())
        self.assertTrue((e.state[:, :, INK] > 0.9).all())
        self.assertFalse(e.action_mask[:, :, 6:, 1:].any())
        self.assertTrue(e.action_mask[:, :, 6:, 0].all())

    def test_shapes_memory_and_sizes(self):
        e = self.env()
        p = Policy()
        obs, _ = e.reset()
        view = prepare(obs)
        self.assertEqual(view["hud"].shape, (2, 10))
        self.assertTrue(
            1_000_000 <= sum(v.numel() for v in p.parameters()) <= 3_000_000
        )
        h = p.initial(2)
        for _ in range(4):
            a, log, value, h = p.act(view, h)
            self.assertEqual(a.shape, (2, 8))
            self.assertTrue((a[:, 6:] == 0).all())
            self.assertTrue(torch.isfinite(log).all())
        self.assertTrue(h.abs().sum() > 0)
        # A reset at t1 must erase the effect of t0 for that batch member.
        seq = {k: torch.stack([v, v, v]) for k, v in view.items()}
        done = torch.zeros((3, 2), dtype=torch.bool)
        done[1, 0] = True
        _, v, _ = p(seq, p.initial(2), done)
        short = {k: x[1:, 0:1] for k, x in seq.items()}
        _, expected, _ = p(short, p.initial(1))
        torch.testing.assert_close(v[1:, 0], expected[:, 0], atol=1e-6, rtol=0)

    def test_d4_positive_control_and_fixed_cone(self):
        import math

        e = self.env()
        rear = D4Defender(e, torch.zeros(1))
        self.assertEqual(int(rear.actions()[0, 1, 3]), 0)
        front = D4Defender(e, torch.full((1,), math.pi))
        for _ in range(20):
            a = front.actions()
            e.step(a)
        self.assertEqual(float(e.state[0, 0, 9]), 0.0)
        self.assertGreater(float(front.fired.sum()), 1.0)

    def test_deepsets_entity_permutation(self):
        e = self.env()
        p = Policy()
        obs, _ = e.reset()
        view = prepare(obs)
        view["entities"][:, :2] = torch.randn((2, 2, 7))
        view["entity_mask"][:, :2] = True
        other = {k: v.clone() for k, v in view.items()}
        other["entities"] = other["entities"].flip(1)
        other["entity_mask"] = other["entity_mask"].flip(1)
        torch.testing.assert_close(p.encode(view), p.encode(other), rtol=0, atol=1e-6)

    def test_gae_terminal_no_bootstrap_leak(self):
        r = torch.tensor([[1.0], [2.0]])
        v = torch.tensor([[0.5], [0.25]])
        d = torch.tensor([[False], [True]])
        a, ret = gae(r, v, d, torch.tensor([100.0]), 0.9, 0.8)
        torch.testing.assert_close(a[:, 0], torch.tensor([1.985, 1.75]))
        torch.testing.assert_close(ret[:, 0], torch.tensor([2.485, 2.0]))

    def test_ppo_updates_only_eligible_samples(self):
        e = self.env()
        p = Policy()
        opt = torch.optim.Adam(p.parameters(), lr=1e-3)
        obs, _ = e.reset()
        view = prepare(obs)
        h = p.initial(2)
        data = {k: [] for k in ["hidden", "actions", "logprob", "values"]}
        with torch.no_grad():
            for _ in range(8):
                data["hidden"].append(h.clone())
                a, lp, v, h = p.act(view, h)
                data["actions"].append(a)
                data["logprob"].append(lp)
                data["values"].append(v)
        batch = {k: torch.stack(v) for k, v in data.items()}
        batch["obs"] = {k: torch.stack([v] * 8) for k, v in view.items()}
        batch.update(
            rewards=torch.ones((8, 2)) * 0.03,
            done_before=torch.zeros((8, 2), dtype=torch.bool),
            done_after=torch.zeros((8, 2), dtype=torch.bool),
            learn=torch.ones((8, 2), dtype=torch.bool),
        )
        initial = p.actor.weight.detach().clone()
        result = update(
            p,
            opt,
            batch,
            torch.zeros(2),
            sequence_length=4,
            minibatch_sequences=2,
            epochs=1,
        )
        self.assertTrue(result["finite"])
        self.assertFalse(torch.equal(initial, p.actor.weight))
        batch["learn"].zero_()
        initial = p.actor.weight.detach().clone()
        result = update(
            p,
            opt,
            batch,
            torch.zeros(2),
            sequence_length=4,
            minibatch_sequences=2,
            epochs=1,
        )
        self.assertEqual(result["optimization_steps"], 0)
        self.assertTrue(torch.equal(initial, p.actor.weight))


if __name__ == "__main__":
    unittest.main()
