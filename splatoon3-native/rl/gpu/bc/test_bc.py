"""Focused BC contracts: masks, latch labels, splits and recurrent boundaries."""

import unittest
import torch
from .data import sequence_starts
from .model import features, BCPolicy
from .train import baselines, edge_weights, cloning_loss, persistence_baseline


class BCTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)

    def observation(self):
        raw = dict(
            screen=torch.ones(1, 2, 18, 32, 4),
            entities=torch.ones(1, 2, 16, 7),
            entity_mask=torch.ones(1, 2, 16, dtype=torch.bool),
            hud=torch.ones(1, 2, 10),
            minimap=torch.ones(1, 2, 16, 24, dtype=torch.uint8),
            action_mask=torch.ones(1, 2, 8, 17, dtype=torch.bool),
        )
        prev = torch.zeros(1, 2, 8, dtype=torch.long)
        val = dict(
            hud_valid=torch.zeros_like(raw["hud"], dtype=torch.bool),
            screen_channel_valid=torch.zeros_like(raw["screen"], dtype=torch.bool),
            minimap_valid=torch.zeros_like(raw["minimap"], dtype=torch.bool),
            entity_velocity_native_valid=torch.zeros(1, 2, dtype=torch.bool),
            projectiles_native_valid=torch.zeros(1, 2, dtype=torch.bool),
            native_camera_valid=torch.ones(1, 2, dtype=torch.bool),
        )
        return raw, prev, val

    def test_unknown_values_cannot_affect_encoding(self):
        raw, prev, val = self.observation()
        a = features(raw, prev, val)
        raw["hud"] *= 50
        raw["screen"] *= 2
        raw["minimap"] *= 2
        raw["entities"][..., 4:] *= 100
        b = features(raw, prev, val)
        for k in a:
            torch.testing.assert_close(a[k], b[k])
        self.assertEqual(a["quality"].shape[-1], 445)

    def test_validity_distinguishes_unknown_from_neutral(self):
        raw, prev, val = self.observation()
        a = features(raw, prev, val)
        val["minimap_valid"].fill_(True)
        b = features(raw, prev, val)
        self.assertFalse(torch.equal(a["quality"], b["quality"]))

    def test_gaps_never_cross_sequence(self):
        m = dict(frame=torch.tensor([0, 2, 4, 8, 10, 12, 14, 16]))
        self.assertEqual(sequence_starts(m, 4, 2), [4])

    def test_majority_uses_training_only(self):
        train = torch.zeros(10, 8, dtype=torch.long)
        val = train.clone()
        val[:, 0] = 1
        b = baselines(train, val)
        self.assertEqual(b["move"]["majority_class"], 0)
        self.assertEqual(b["move"]["val"]["accuracy"], 0)
        self.assertGreater(b["move"]["val"]["cross_entropy"], 2)

    def test_model_recurrent_shape_and_backward(self):
        raw, prev, val = self.observation()
        encoded = features(raw, prev, val)
        model = BCPolicy(64)
        out, _, hidden = model(
            {k: v[None] for k, v in encoded.items()}, model.initial(2)
        )
        self.assertEqual(tuple(out.shape), (1, 2, 8, 17))
        self.assertEqual(tuple(hidden.shape), (1, 2, 64))
        out.sum().backward()
        self.assertTrue(torch.isfinite(model.quality[0].weight.grad).all())

    def test_edge_balance_is_bounded_and_only_changes_latch_heads(self):
        labels = torch.zeros(100, 8, dtype=torch.long)
        labels[-1, 3:5] = 1
        weights = edge_weights(labels, True)
        self.assertEqual(float(weights[3, 1]), 8)
        self.assertTrue((weights[[0, 1, 2, 5, 6, 7]] == 1).all())
        logits = torch.zeros(100, 8, 17, requires_grad=True)
        loss = cloning_loss(logits, labels, weights)
        loss.backward()
        self.assertTrue(torch.isfinite(logits.grad).all())

    def test_persistence_is_causal_train_fitted(self):
        train = torch.zeros(10, 8, dtype=torch.long)
        previous = torch.zeros_like(train)
        train[5:, 0] = previous[5:, 0] = 9
        val = train.flip(0)
        result = persistence_baseline(train, previous, val, previous)
        self.assertEqual(result["move"]["train"]["accuracy"], 1)
        self.assertEqual(result["move"]["val"]["accuracy"], 0)


if __name__ == "__main__":
    unittest.main()
