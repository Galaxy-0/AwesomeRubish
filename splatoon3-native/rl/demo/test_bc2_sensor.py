"""Causal native snapshot selection with synthetic images, no game process."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PIL import Image
from .bc2_native import NativeBC2
from .bc_ink import SnapshotInk


class NativeSensorTests(unittest.TestCase):
    def test_cold_neutral_consensus_future_exclusion_and_stale_mask(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zero = np.zeros((1600, 1600, 3), np.uint8)
            painted = zero.copy()
            painted[1, 1, 0] = 255
            for tick, image in [(100, zero), (130, painted)]:
                Image.fromarray(image).save(root / f"frame-{tick}-target-a.png")
                Image.fromarray(zero).save(root / f"frame-{tick}-target-b.png")
            sensor = NativeBC2.__new__(NativeBC2)
            sensor.origins = {"player_0": {"frame": 100}}
            sensor.root = root
            sensor.tag = None
            sensor.last_poll = -100
            sensor.cached = None
            sensor.sample_frame = -100
            sensor.sensor = SimpleNamespace(shape=(1, 2))
            sensor.reader = SimpleNamespace(
                a=dict(
                    uv=np.array([[1, 1], [2, 2]]),
                    cell_valid=np.ones(2, bool),
                    top=np.array([[0, 1]]),
                    map_valid=np.ones((1, 2), bool),
                ),
                decode=SnapshotInk.decode,
            )
            colors, valid, age = sensor.snapshot(29)
            self.assertTrue(valid.all())
            self.assertFalse(colors.any())
            self.assertEqual(age, 29)
            colors, valid, age = sensor.snapshot(30)
            self.assertEqual(colors.tolist(), [[1, 0]])
            self.assertTrue(valid.all())
            self.assertEqual(age, 0)
            colors, valid, age = sensor.snapshot(60)
            self.assertFalse(valid.any())
            self.assertEqual(age, 30)


if __name__ == "__main__":
    unittest.main()
