"""Source-time angle/rate audit checks without games, hardware or assets."""

import unittest
import numpy as np

from .gyro_audit import response_windows
from .controller_recheck import DirectionMonitor


class AuditTests(unittest.TestCase):
    def test_yaw_rate_ratio_wraps_angles_and_excludes_stick_and_reset(self):
        n = 340
        raw = np.zeros((n, 3))
        raw[:, 1] = 1
        camera = np.zeros((n + 1, 2))
        camera[:, 0] = (np.arange(n + 1) * 2.4 / 60 + np.pi) % (2 * np.pi) - np.pi
        sticks = np.zeros((n, 4))
        valid = np.ones(n + 1, bool)
        times = np.arange(n) * 1e9 / 60
        result = response_windows(raw, sticks, camera, valid, times, 0, 1)
        self.assertEqual(result["windows"], 1)
        self.assertAlmostEqual(result["median_abs_gain"], 2.4)
        self.assertAlmostEqual(result["median_wall_abs_gain"], 2.4)
        sticks[300:316, 2] = 0.1
        self.assertEqual(
            response_windows(raw, sticks, camera, valid, times, 0, 1)["windows"], 0
        )
        sticks[:] = 0
        resets = np.zeros(n, bool)
        resets[302] = 1
        self.assertEqual(
            response_windows(raw, sticks, camera, valid, times, 0, 1, resets)[
                "windows"
            ],
            0,
        )

    def test_pitch_uses_actual_eye_at_elevation_not_control_field(self):
        n = 340
        raw = np.zeros((n, 3))
        raw[:, 0] = 0.5
        camera = np.zeros((n + 1, 2))
        sticks = np.zeros((n, 4))
        valid = np.ones(n + 1, bool)
        times = np.arange(n) * 1e9 / 60
        elevation = -1.2 * (np.arange(n + 1) - 300) / 60
        result = response_windows(
            raw, sticks, camera, valid, times, 0, 0, elevations=elevation
        )
        self.assertAlmostEqual(result["slope_camera_per_hand"], -2.4)

    def test_monitor_labels_physical_direction_separately_from_native_slots(self):
        lines = []
        monitor = DirectionMonitor(emit=lambda value, **kw: lines.append(value))
        monitor.update(
            dict(
                gyro=[-0.1, -0.3, -0.2],
                physical_gyro_turns_s=[0.1, 0.2, 0.3],
                gyro_rad_s=[0.6, -1.2, -1.8],
            ),
            {},
            now=0,
        )
        self.assertIn("yaw=右 pitch=抬头 roll=右倾", lines[0])
        self.assertIn("HID turns/s=-0.100,-0.300,-0.200", lines[0])


if __name__ == "__main__":
    unittest.main()
