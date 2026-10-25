"""No game launch: actor identity, KL, causal eligibility, caps and PPO grads."""

import copy
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
import torch
from ..bc.test_bc import BCTests
from ..bc2.observation import encode
from ..bc2.model import Actor
from ..env import HP
from .model import WarmActor, bc_kl, distributions
from .rewards import Guidance, schedule
from .ppo import update
from .opponents import Opponent
from ..test_env import fixture_config


class WarmTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        torch.manual_seed(81)

    def observation(self):
        raw, prev, valid = BCTests().observation()
        return encode(raw, valid, torch.zeros(1, 2), prev)

    def test_adapter_exact_bc_logits_and_recurrence(self):
        old = Actor(32, 1, False)
        new = WarmActor(32)
        new.load_state_dict(old.state_dict())
        obs = {k: x[None].expand(4, *x.shape) for k, x in self.observation().items()}
        a, va, ha, _ = old(obs, old.initial(2))
        b, vb, hb = new(obs, new.initial(2))
        torch.testing.assert_close(a[:, :, 0], b, rtol=0, atol=0)
        torch.testing.assert_close(ha, hb, rtol=0, atol=0)
        torch.testing.assert_close(va, vb, rtol=0, atol=0)

    def test_critic_only_fitting_preserves_actor_exactly(self):
        model = WarmActor(32)
        original = copy.deepcopy(model)
        x = torch.randn(64, 32)
        target = torch.randn(64)
        opt = torch.optim.Adam(model.value.parameters(), lr=0.01)
        for _ in range(3):
            loss = (model.value(x).squeeze(-1) - target).square().mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
        for k, x in model.state_dict().items():
            if not k.startswith("value."):
                self.assertTrue(torch.equal(x, original.state_dict()[k]))
        self.assertFalse(torch.equal(model.value.weight, original.value.weight))

    def test_kl_identity_and_corrective_gradient(self):
        logits = torch.randn(3, 6, 8, 17, requires_grad=True)
        p = logits.detach().softmax(-1)
        self.assertLess(abs(float(bc_kl(logits, p).mean().detach())), 1e-6)
        altered = logits + torch.randn_like(logits) * 0.4
        value = bc_kl(altered, p).mean()
        value.backward()
        self.assertGreater(float(value.detach()), 0)
        self.assertTrue(torch.isfinite(logits.grad).all())
        self.assertGreater(float(logits.grad.abs().sum()), 0)

    def test_guidance_never_uses_unseen_enemy_and_memory_expires(self):
        s = torch.zeros(1, 2, 48)
        s[:, :, HP] = 1
        s[:, 1, 2] = 10
        t = s.clone()
        t[:, 0, 2] = 1
        g = Guidance(1, "cpu", memory_frames=2)
        events = torch.zeros(1, 2, 6)
        r, _ = g.step(s, t, torch.tensor([False]), events)
        self.assertEqual(float(r), 0)
        r, _ = g.step(s, t, torch.tensor([True]), events)
        self.assertGreater(float(r), 0)
        r, _ = g.step(s, t, torch.tensor([False]), events, df=4)
        self.assertEqual(float(r), 0)

    def test_reacquisition_cannot_reset_farming_cap(self):
        s = torch.zeros(1, 2, 48)
        s[:, :, HP] = 1
        s[:, 1, 2] = 10
        t = s.clone()
        t[:, 0, 2] = 1
        g = Guidance(1, "cpu")
        total = 0.0
        for i in range(1200):
            if i % 10 == 0:
                g.life.zero_()  # many deaths do not reset match budget
            r, _ = g.step(s, t, torch.tensor([i % 2 == 0]), torch.zeros(1, 2, 6))
            total += float(r)
        self.assertLessEqual(total, float(g.match_cap.sum()) + 1e-5)
        self.assertLessEqual(float(g.match[0, 0]), 0.80001)

    def test_annealing_finishes_at_quarter_budget(self):
        for name in ["auxiliary", "bc_kl", "near_fraction"]:
            self.assertGreater(schedule(0)[name], 0)
            self.assertEqual(schedule(21600)[name], 0)
            self.assertEqual(schedule(86400)[name], 0)
        self.assertGreater(schedule(86400)["entropy"], 0)

    def test_easy_uses_public_visibility_without_pose_writes(self):
        state = torch.zeros(2, 2, 48)
        state[:, :, HP] = 1
        state[:, :, 10] = 1
        fake = SimpleNamespace(
            n=2,
            device="cpu",
            state=state,
            cfg=fixture_config(camera_codebook="native_plus5"),
        )
        opp = Opponent(fake, "easy")
        raw = dict(
            entities=torch.zeros(2, 2, 16, 7),
            entity_mask=torch.zeros(2, 2, 16, dtype=torch.bool),
        )
        raw["entities"][:, 1, 0, 3] = 1
        raw["entities"][:, 1, 0, 2] = 6
        initial = state.clone()
        for _ in range(20):
            a = opp.actions(raw)
        self.assertEqual(int(a[:, 1, 3].sum()), 0)
        raw["entity_mask"][:, 1, 0] = True
        for _ in range(20):
            a = opp.actions(raw)
        self.assertEqual(int(a[:, 1, 3].sum()), 2)
        self.assertTrue(torch.equal(initial, state))

    def test_recurrent_ppo_updates_without_latch_or_nan(self):
        model = WarmActor(32).train()
        base = self.observation()
        obs = {k: x[None].repeat(8, *([1] * x.ndim)) for k, x in base.items()}
        with torch.no_grad():
            logits, value, _ = model(obs, model.initial(2))
            dist = distributions(logits)
            a = dist.sample()
            heads = dist.log_prob(a)
        batch = dict(
            obs=obs,
            hidden=torch.zeros(8, 1, 2, 32),
            before=torch.zeros(8, 2, dtype=torch.bool),
            after=torch.zeros(8, 2, dtype=torch.bool),
            actions=a,
            logprob=heads.sum(-1),
            heads=heads,
            values=value,
            teacher=logits.softmax(-1),
            rewards=torch.randn(8, 2) * 0.01,
        )
        old = model.actor.weight.detach().clone()
        result = update(
            model,
            torch.optim.Adam(model.parameters(), lr=1e-4),
            batch,
            torch.zeros(2),
            bc_coef=1.0,
            entropy_coef=0.01,
            sequence=4,
            minibatch=2,
            epochs=1,
        )
        self.assertGreater(result["optimization_steps"], 0)
        self.assertTrue(torch.isfinite(torch.tensor(result["value_loss"])))
        self.assertFalse(torch.equal(old, model.actor.weight))

    def test_native_actor_export_and_resume_have_separate_schemas(self):
        from .train import export
        from ..bc2.model import load

        model = WarmActor(32)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "actor.pt"
            export(
                p,
                model,
                torch.optim.Adam(model.parameters()),
                update=7,
                frames=100,
                elapsed=90,
                bc_sha256="fixture",
                phase="easy",
            )
            old, meta = load(p, "cpu")
            self.assertEqual(meta["schema"], "inklab.bc2.checkpoint.v1")
            obs = {k: x[None] for k, x in self.observation().items()}
            torch.testing.assert_close(
                old(obs, old.initial(2))[0][:, :, 0], model(obs, model.initial(2))[0]
            )
            resume = torch.load(Path(tmp) / "actor-resume.pt", weights_only=False)
            self.assertEqual(resume["schema"], "inklab.bcppo.resume.v1")
            self.assertEqual(resume["elapsed"], 90)


if __name__ == "__main__":
    unittest.main()
