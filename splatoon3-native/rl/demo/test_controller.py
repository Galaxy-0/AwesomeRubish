"""Controller mapping/calibration regression tests; no USB/game/SDL init needed."""

import ctypes as C
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from rl.demo.controller import Controller
from rl.demo.controller_check import (
    DEFAULT_BINDINGS,
    GuidedCheck,
    active_channels,
    baseline_report,
    gyro_gesture,
    gyro_mapping,
    mapped_buttons,
    radial_sticks,
    resolve_binding,
    validate_profile,
)


def row(us=1000, sticks=None, gyro=None, channels=()):
    value = dict(
        sensor_timestamp_us=us,
        raw_sticks=sticks or [0.116, 0.02, 0.01, -0.103],
        gyro_rad_s=gyro or [0.01, -0.02, 0.03],
        sensor_events=[],
        button_events=[],
        controller_axes=[0] * 6,
        all_buttons=[0] * 21,
        joystick_buttons=[0] * 20,
    )
    for kind, i in channels:
        field = dict(
            axis="controller_axes", button="all_buttons", joy_button="joystick_buttons"
        )[kind]
        value[field][i] = 32767 if kind == "axis" else 1
    return value


class MappingTests(unittest.TestCase):
    def test_both_triggers_are_axes_and_not_in_button_enum(self):
        r = row(channels=[("axis", 4), ("axis", 5)])
        self.assertEqual(mapped_buttons(r, DEFAULT_BINDINGS)["ZR"], 1)
        self.assertEqual(mapped_buttons(r, DEFAULT_BINDINGS)["ZL"], 1)
        self.assertFalse(any(r["all_buttons"]))

    def test_trigger_tap_edge_and_release(self):
        r = row()
        r["button_events"] = [
            dict(type="axis", index=5, value=32767),
            dict(type="axis", index=5, value=0),
        ]
        self.assertEqual(mapped_buttons(r, DEFAULT_BINDINGS)["ZR"], 1)
        r["button_events"] = []
        self.assertEqual(mapped_buttons(r, DEFAULT_BINDINGS)["ZR"], 0)

    def test_printed_label_calibration_overrides_shoulder_and_trigger_order(self):
        bindings = dict(
            DEFAULT_BINDINGS,
            R=["button", 9],
            L=["button", 10],
            ZR=["axis", 4],
            ZL=["axis", 5],
        )
        values = mapped_buttons(row(channels=[("button", 9), ("axis", 4)]), bindings)
        self.assertEqual([values[k] for k in ("R", "L", "ZR", "ZL")], [1, 0, 1, 0])

    def test_extended_capture_button_and_raw_fallback(self):
        r = row(channels=[("button", 15), ("joy_button", 17)])
        self.assertEqual(mapped_buttons(r, DEFAULT_BINDINGS)["Capture"], 1)
        self.assertEqual(resolve_binding(active_channels(r)), ["button", 15])
        self.assertEqual(resolve_binding({("joy_button", 18)}), ["joy_button", 18])
        self.assertIsNone(resolve_binding({("axis", 4), ("axis", 5)}))

    def test_deadzone_is_radial_recenters_and_retains_full_throw(self):
        raw = [0.116, 0.02, 0.01, -0.103]
        self.assertEqual(radial_sticks(raw, raw), [0, 0, 0, 0])
        self.assertEqual(radial_sticks(raw), [0, 0, 0, 0])
        self.assertGreater(radial_sticks([0.12, 0.12, 0, 0])[0], 0)
        self.assertAlmostEqual(radial_sticks([1, 0, 0, 0], [0.116, 0, 0, 0])[0], 1)
        self.assertAlmostEqual(math.hypot(*radial_sticks([1, 1, 0, 0])[:2]), 1)

    def test_baseline_drift_and_invalid_samples(self):
        base = baseline_report([row(i * 5000) for i in range(30)])
        self.assertTrue(base["stable"])
        self.assertEqual(base["centers"], [0.116, 0.02, 0.01, -0.103])
        self.assertGreaterEqual(base["recommended_uncentered_deadzone"], 0.15)
        self.assertGreater(
            base["recommended_uncentered_deadzone"], max(base["raw_radius_p99"])
        )
        self.assertGreaterEqual(base["deadzone"], 0.15)
        with self.assertRaises(ValueError):
            baseline_report([row(0)])

    def test_gyro_unique_timestamps_avoid_poll_rate_inflation(self):
        rows = [row(1000 + i * 5000, gyro=[0, -1, 0]) for i in range(50)]
        result = gyro_gesture(rows, [0, 0, 0])
        repeated = gyro_gesture([r for r in rows for _ in range(20)], [0, 0, 0])
        self.assertTrue(result["valid"])
        self.assertEqual(result, repeated)
        self.assertEqual((result["axis"], result["sign"]), (1, -1))
        self.assertFalse(
            gyro_gesture([row(5000 * i) for i in range(50)], [0.01, -0.02, 0.03])[
                "valid"
            ]
        )

    def test_gyro_opposites_and_axis_conflicts_stay_unknown(self):
        results = {}
        for name, positive, negative, axis in (
            ("yaw", "right", "left", 1),
            ("pitch", "up", "down", 0),
            ("roll", "right", "left", 2),
        ):
            for direction, sign in ((positive, 1), (negative, -1)):
                results[f"gyro_{name}_{direction}"] = dict(
                    valid=True, axis=axis, sign=sign
                )
        self.assertTrue(all(v["valid"] for v in gyro_mapping(results).values()))
        results["gyro_roll_left"]["sign"] = 1
        self.assertFalse(gyro_mapping(results)["roll"]["valid"])
        results["gyro_roll_left"]["sign"] = -1
        results["gyro_roll_left"]["axis"] = results["gyro_roll_right"]["axis"] = 0
        self.assertFalse(any(v["valid"] for v in gyro_mapping(results).values()))

    def test_real_sample_polls_axes_extended_buttons_and_edge_events(self):
        class FakeSDL:
            events = [struct.pack("<III4xh", 0x650, 1, 0, 32767)]

            def SDL_PollEvent(self, buffer):
                if not self.events:
                    return 0
                data = bytearray(self.events.pop())
                data[12] = 5
                C.memmove(buffer, bytes(data), len(data))
                return 1

            def SDL_GameControllerUpdate(self):
                pass

            def SDL_GameControllerGetAttached(self, _):
                return 1

            def SDL_GameControllerGetSensorDataWithTimestamp(
                self, _, sensor, stamp, gyro, size
            ):
                C.cast(stamp, C.POINTER(C.c_uint64))[0] = 1000
                return 0

            def SDL_GameControllerGetAxis(self, _, i):
                return 32767 if i == 4 else 0

            def SDL_GameControllerGetButton(self, _, i):
                return int(i == 15)

            def SDL_JoystickGetButton(self, _, i):
                return 0

        c = Controller.__new__(Controller)
        c.lib, c.handle, c.joystick = FakeSDL(), 1, 1
        c.event, c.calibration, c.deadzone = C.create_string_buffer(128), {}, 0.15
        c.button_names, c.joy_counts = list(range(21)), [0, 0, 0]
        r = c.sample()
        self.assertEqual(r["buttons"][:2], [1, 1])  # ZR edge + held ZL
        self.assertEqual(len(r["all_buttons"]), 21)
        self.assertEqual(r["physical_buttons"]["Capture"], 1)
        c.calibration = dict(
            bindings=dict(DEFAULT_BINDINGS, ZR=["axis", 4], ZL=["axis", 5]),
            gyro_bias_rad_s=[0.1, 0.2, 0.3],
            gyro_mapping=dict(
                pitch=dict(axis=0, sign=1),
                yaw=dict(axis=2, sign=-1),
                roll=dict(axis=1, sign=1),
            ),
        )
        r = c.sample()
        self.assertEqual(r["buttons"][:2], [1, 0])  # profile + expired tap edge
        self.assertAlmostEqual(r["gyro"][1], 0.3 / (2 * math.pi))

    def test_invalid_profile_is_rejected_before_device_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            path.write_text(
                json.dumps(dict(schema="pro-controller-physical-v1", complete=False))
            )
            with patch("rl.demo.controller.C.CDLL") as library:
                with self.assertRaises(ValueError):
                    Controller(profile=path)
                library.assert_not_called()


class GuidedTests(unittest.TestCase):
    def test_complete_guided_check_and_profile_no_hardware(self):
        class Clock:
            t = 1.0

            def now(self):
                return self.t

            def sleep(self, delta):
                self.t += delta

        clock = Clock()

        class FakeController:
            device = dict(vendor=0x057E, product=0x2009)

        class FakeCheck(GuidedCheck):
            def read(self, stage):
                us = int(clock.t * 1e6)
                r = row(us)
                if ":settle" not in stage:
                    if stage.startswith("button_"):
                        r = row(us, channels=[DEFAULT_BINDINGS[stage[7:]]])
                    elif stage.startswith("stick_"):
                        axis = (0 if "左摇杆" in stage else 2) + int(
                            stage.endswith(("上", "下"))
                        )
                        r["raw_sticks"][axis] = (
                            1 if stage.endswith(("上", "右")) else -1
                        )
                    elif stage.startswith("gyro_"):
                        _, name, direction = stage.split("_")
                        axis = dict(yaw=1, pitch=0, roll=2)[name]
                        r["gyro_rad_s"][axis] += (
                            1 if direction in ("right", "up") else -1
                        )
                self.stream.write(json.dumps(dict(r, check_stage=stage)) + "\n")
                return r

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("rl.demo.controller_check.time.monotonic", clock.now),
            patch("rl.demo.controller_check.time.sleep", clock.sleep),
        ):
            out = Path(tmp) / "work" / "guided"
            summary = FakeCheck(FakeController(), out, emit=lambda *a, **kw: None).run()
            profile = json.loads((out / "profile.json").read_text())
            self.assertTrue(summary["profile"]["complete"])
            self.assertEqual(validate_profile(profile), profile)
            self.assertIn("ZR", (out / "report.md").read_text())
            self.assertEqual(len(summary["stages"]), 32)
            profile["complete"] = False
            with self.assertRaises(ValueError):
                validate_profile(profile)
            with self.assertRaises(FileExistsError):
                FakeCheck(FakeController(), out).run()

    def test_timeout_and_neutral_release_are_explicit(self):
        clock = [1.0]

        def sleep(delta):
            clock[0] += delta

        class Quiet(GuidedCheck):
            def read(self, stage):
                return row(int(clock[0] * 1e6))

        c = Quiet(None, "unused", timeout=0.8, emit=lambda *a, **kw: None)
        c.base = baseline_report([row(5000 * i) for i in range(30)])
        with (
            patch("rl.demo.controller_check.time.monotonic", lambda: clock[0]),
            patch("rl.demo.controller_check.time.sleep", sleep),
        ):
            result = c.measure("button_ZR", "请按 ZR", lambda rows: None)
        self.assertEqual(result, dict(valid=False, reason="input_timeout"))


if __name__ == "__main__":
    unittest.main()
