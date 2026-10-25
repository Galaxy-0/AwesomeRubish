"""BC fixture cannot widen human/formal entrypoints; calibrated input roundtrip."""

from argparse import Namespace
import unittest
import numpy as np
from rl.demo.bc_native import native_action
from rl.demo.camera_model import predict
from rl.demo.capture import run
from rl.gpu.contract import Config, camera_levels


class NativeBCTests(unittest.TestCase):
    def test_primary_script_only_guard_precedes_host_or_controller(self):
        for extra in [
            dict(source="controller"),
            dict(loadout="full"),
            dict(opponent="policy"),
            dict(fixture_inputs="x"),
            dict(fixture_player_policy="x"),
        ]:
            values = dict(
                fixture_bc_checkpoint="owned.pt",
                source="script",
                loadout="primary_only",
                opponent="52",
            )
            values.update(extra)
            with self.assertRaisesRegex(ValueError, "script-only"):
                run(Namespace(**values))

    def test_ordinary_gyro_roundtrip_all_nine_bins(self):
        camera = dict(
            kind="native_plus5_power_v1",
            gyro_matrix=[[0, 0, 0.25], [-0.25, 0, 0]],
            stick_yaw_exponent=2.34,
            stick_full_yaw_rate=0.064,
        )
        cfg = Config(
            stick_plus5_radians_per_frame=0.064, camera_codebook="native_plus5"
        )
        for y in range(9):
            for p in range(9):
                action = native_action([0, y, p, 1, 0, 1, 0, 0], cfg, camera)
                delta = predict([*action["sticks"][2:], *action["gyro"]], camera)
                expected = np.array(camera_levels(cfg))[[y, p]] * (
                    cfg.gyro_max_radians_per_frame + 0.064
                )
                np.testing.assert_allclose(delta, expected, atol=1e-7)
                self.assertEqual(action["buttons"], [1, 0, 0, 0, 1, 0])


if __name__ == "__main__":
    unittest.main()
