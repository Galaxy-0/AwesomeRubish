"""Synthetic multilayer/native UV contract, without any game-derived geometry."""

import tempfile
from pathlib import Path
import unittest
import numpy as np
from .native_ink import PanelMap, NativeInk
from .state_sync import CausalIndex
import torch


class InkTests(unittest.TestCase):
    def test_missing_exact_readback_does_not_use_past_or_future_image(self):
        ink = NativeInk.__new__(NativeInk)
        ink.map = object()
        ink.index = CausalIndex([dict(frame=49, image="/not-a-native-image")])
        obs = dict(
            screen=torch.zeros(1, 2, 18, 32, 4),
            minimap=torch.zeros(1, 2, 3, 3, dtype=torch.uint8),
        )
        for frame in (48, 50):
            screen, minimap = ink.overlay(obs, None, frame)
            self.assertFalse(screen.any())
            self.assertFalse(minimap.any())

    def make_map(self, root, overlap=False):
        basis = np.array([[[1, 0, 0], [0, 0, 1], [0, 1, 0]]] * 2, float)
        low = np.array([[-5, -5, -0.01], [-5, -5, 2.99]])
        high = np.array([[5, 5, 0.01], [5, 5, 3.01]])
        uv = np.array(
            [[[0.005, 0, 0.2], [0, 0.005, 0.3]], [[0.005, 0, 0.6], [0, 0.005, 0.7]]]
        )
        if overlap:
            low[1] = low[0]
            high[1] = high[0]
        path = Path(root) / "panels.npz"
        np.savez(path, basis=basis, low=low, high=high, uv=uv)
        return PanelMap(path)

    def test_same_xz_different_floor_uses_distinct_panel_uv_and_v_flip(self):
        with tempfile.TemporaryDirectory() as d:
            m = self.make_map(d)
            uv, valid, ids = m.project([[0, 0, 0], [0, 3, 0], [9, 0, 0]])
            self.assertEqual(valid.tolist(), [True, True, False])
            self.assertEqual(ids.tolist(), [0, 1, -1])
            np.testing.assert_allclose(uv[:2], [[320, 1120], [960, 480]])

    def test_ambiguous_overlapping_panels_never_pick_arbitrary_first(self):
        with tempfile.TemporaryDirectory() as d:
            m = self.make_map(d, overlap=True)
            m.qualified_panels = [0]
            _, valid, ids = m.project([[0, 0, 0]])
            self.assertFalse(valid[0])
            self.assertEqual(ids[0], -1)

    def test_unmeasured_panel_remains_masked_even_if_unique(self):
        with tempfile.TemporaryDirectory() as d:
            m = self.make_map(d)
            m.qualified_panels = [0]
            _, valid, ids = m.project([[0, 0, 0], [0, 3, 0]])
            self.assertEqual(valid.tolist(), [True, False])
            self.assertEqual(ids.tolist(), [0, -1])

    def test_intermediate_channels_and_invalid_projection_are_not_neutral_truth(self):
        ink = NativeInk.__new__(NativeInk)
        image = np.zeros((1600, 1600, 3), np.uint8)
        image[0, 1] = [255, 0, 0]
        image[0, 2] = [0, 255, 0]
        image[0, 3] = [128, 127, 0]
        uv = np.array([[0, 0], [1, 0], [2, 0], [3, 0], [1, 0]])
        color, valid = ink.sample(image, uv, np.array([True, True, True, True, False]))
        self.assertEqual(color.tolist(), [-1, 0, 1, -1, -1])
        self.assertEqual(valid.tolist(), [True, True, True, False, False])


if __name__ == "__main__":
    unittest.main()
