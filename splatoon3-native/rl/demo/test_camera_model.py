import unittest
import numpy as np
from dataclasses import replace
from .camera_model import predict
from .convert import quantize
from rl.gpu.test_env import fixture_config
from rl.gpu.contract import camera_levels


class CameraTests(unittest.TestCase):
    def model(self):
        return dict(
            kind="native_plus5_power_v1",
            stick_full_yaw_rate=0.064,
            stick_yaw_exponent=2.0,
            gyro_matrix=[[0, 0, 0.25], [-0.25, 0, 0]],
        )

    def test_half_stick_is_not_half_full_native_turn(self):
        model = self.model()
        out = predict([[1, 0, 0, 0, 0], [0.5, 0, 0, 0, 0], [-0.5, 0, 0, 0, 0]], model)
        np.testing.assert_allclose(out[:, 0], [-0.064, -0.016, 0.016])

    def test_gyro_is_physical_turns_per_second(self):
        out = predict([0, 0, 0.04, 0, -0.04], self.model())
        np.testing.assert_allclose(out, [-0.01, -0.01])

    def test_codebook_version_is_explicit_and_fine_center_is_representable(self):
        cfg = replace(fixture_config(), camera_codebook="native_plus5")
        action = dict(sticks=[0, 0, 0.12, 0], gyro=[0, 0, 0], buttons=[0] * 6)
        lv, _, _ = quantize(action, cfg, self.model(), [0, 4, 4, 0, 0, 0, 0, 0])
        self.assertEqual(lv[1], 3)
        self.assertEqual(camera_levels(fixture_config())[3], -0.03)
        self.assertEqual(camera_levels(cfg)[3], -0.0014)


if __name__ == "__main__":
    unittest.main()
