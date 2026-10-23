"""Truth gaps must fail closed, including the measured light/cancel counterexamples."""

import unittest
import json
from pathlib import Path
import struct
import tempfile
from .weapon_truth import decode_saber
from .projectile_truth import reduce


class WeaponTruthTests(unittest.TestCase):
    def test_light_swing_is_not_wait(self):
        swing = decode_saber(1, 0, 9, 36)
        self.assertEqual(swing["weapon_stage"], "light_swing")
        self.assertEqual(swing["charge_progress"], 0)
        self.assertEqual(swing["animation_deadline_remaining_frames"], 27)
        self.assertEqual(decode_saber(1, 0, -1, 0)["weapon_stage"], "wait")

    def test_charge_cancel_does_not_leave_phantom_charge(self):
        before = decode_saber(5, 0.0677999854, -1, 0)
        after = decode_saber(5, 0, -1, 0)
        self.assertAlmostEqual(before["charge_native_frames"], 11, places=4)
        self.assertEqual(after["charge_progress"], 0)
        self.assertEqual(after["weapon_stage"], "charge_cancel_exit")

    def test_native_twenty_is_hud_full_not_twenty_over_twenty_one(self):
        d = decode_saber(5, 0.116999745, -1, 0)
        self.assertAlmostEqual(d["charge_progress"], 1, places=4)
        self.assertAlmostEqual(d["charge_frames"], 21, places=4)

    def test_timing_deadline_is_not_claimed_input_lock(self):
        d = decode_saber(6, 0, 22, 30)
        self.assertEqual(d["weapon_stage"], "recovery")
        self.assertEqual(d["animation_deadline_remaining_frames"], 8)
        self.assertFalse(d["cooldown_lock_qualified"])
        self.assertEqual(d["cooldown_frames"], 0)

    def test_unknown_variants_and_nonfinite_stay_masked(self):
        for args in [
            (2, 0, 4, 36),
            (8, 0, 22, 48),
            (5, float("nan"), -1, 0),
            (5, 0.5, -1, 0),
        ]:
            self.assertIsNone(decode_saber(*args))


class ProjectileTruthTests(unittest.TestCase):
    def make(self, root, events):
        root = Path(root)
        (root / "session/player-0").mkdir(parents=True)
        (root / "result.json").write_text(
            json.dumps(dict(weapons=[8000, 50], session=str(root / "session")))
        )
        (root / "native-barriers.jsonl").write_text(
            json.dumps(dict(frame=0, infos={"player_0": {"frame": 100}})) + "\n"
        )
        text = (
            "".join(f"DEMO_TRUTH_ACTION frame={f}\n" for f in range(100, 105)) + events
        )
        (root / "session/player-0/host.log").write_text(text)
        return root

    def test_no_lifecycle_sensor_never_qualifies_empty_set(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.make(d, "")
            report = reduce(root)
            self.assertFalse(report["sensor_attested"])
            self.assertEqual(report["qualified_frames"], 0)

    def test_release_and_pool_reuse_keep_native_owner_not_observer(self):
        data = bytearray(0x100)
        struct.pack_into("<I", data, 0xC, 50)

        def life(f, event):
            return f"DEMO_TRUTH_LIFE frame={f} event={event} object=0xaaa vtable=5c79398 valid=1 position=0,1,4 velocity=0,0,3.06 linger=-1 params=0xbbb readonly=1\n"

        def param(f):
            return f"DEMO_NATIVE_RAW frame={f} kind=lifecycle_params object=0xbbb size=256 data={data.hex()} readonly=1\n"

        events = (
            life(100, 0)
            + param(100)
            + life(100, 2)
            + life(101, 3)
            + life(103, 0)
            + param(103)
            + life(103, 2)
            + life(104, 3)
        )
        with tempfile.TemporaryDirectory() as d:
            root = self.make(d, events)
            report = reduce(root)
            rows = [
                json.loads(x)
                for x in (root / "native-projectiles.jsonl").read_text().splitlines()
            ]
            self.assertEqual(rows[0]["projectiles"][0]["owner"], 1)
            self.assertEqual(rows[0]["projectiles"][0]["kind"], 3)
            self.assertEqual(rows[1]["projectiles"], [])
            self.assertEqual(rows[2]["projectiles"], [])
            self.assertEqual(rows[3]["projectiles"][0]["generation"], 2)
            self.assertEqual(len(report["lifetimes"]), 2)


if __name__ == "__main__":
    unittest.main()
