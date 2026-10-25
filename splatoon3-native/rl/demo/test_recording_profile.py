"""Stage1 profile gates and fixture dry-run, without SDL/controller/game access."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import capture
from .controller_check import DEFAULT_BINDINGS, NATIVE_GYRO_MATRIX, validate_profile
from .recording_profile import issue


def profile():
    bindings = {
        k: v for k, v in DEFAULT_BINDINGS.items() if k not in ("Minus", "Plus", "Up")
    }
    stages = {"button_" + k: dict(valid=True, binding=v) for k, v in bindings.items()}
    stages.update({"stick_" + str(i): dict(valid=True) for i in range(8)})
    return dict(
        schema="pro-controller-physical-v1",
        scope="primary_only_recording",
        complete=True,
        device=dict(sdl_mapping="test"),
        bindings=bindings,
        stage_evidence=stages,
        centers=[0] * 4,
        gyro_bias_rad_s=[0] * 3,
        deadzone=0.15,
        gyro_mapping={
            k: dict(valid=True, axis=i, sign=s)
            for k, i, s in (("pitch", 0, 1), ("yaw", 1, -1), ("roll", 2, -1))
        },
        gyro_native_matrix=deepcopy(NATIVE_GYRO_MATRIX),
        disabled_buttons=["Minus", "Plus", "Up", "R", "RS"],
        in_game_direction_validation=dict(
            accepted=True,
            user_feedback="正常",
            gyro_native_matrix=deepcopy(NATIVE_GYRO_MATRIX),
        ),
    )


class RecordingProfileTests(unittest.TestCase):
    def test_primary_requires_every_stage1_button_and_stick_and_accepted_gyro(self):
        good = profile()
        validate_profile(good, loadout="primary_only")
        for label in ("ZR", "ZL", "B"):
            for kind in ("missing", "unconfirmed", "disabled"):
                p = deepcopy(good)
                if kind == "missing":
                    p["bindings"].pop(label)
                elif kind == "unconfirmed":
                    p["stage_evidence"]["button_" + label]["valid"] = False
                else:
                    p["disabled_buttons"].append(label)
                with self.assertRaises(ValueError):
                    validate_profile(p, loadout="primary_only")
        for key in ("stick_0", "stick_7"):
            p = deepcopy(good)
            p["stage_evidence"][key]["valid"] = False
            with self.assertRaises(ValueError):
                validate_profile(p, loadout="primary_only")
        p = deepcopy(good)
        p["in_game_direction_validation"]["accepted"] = False
        with self.assertRaises(ValueError):
            validate_profile(p, loadout="primary_only")

    def test_primary_does_not_require_R_RS_but_full_does(self):
        p = profile()
        for key in ("R", "RS"):
            p["bindings"].pop(key)
            p["stage_evidence"]["button_" + key]["valid"] = False
        validate_profile(p, loadout="primary_only")
        with self.assertRaises(ValueError):
            validate_profile(profile(), loadout="full")
        full = profile()
        full["scope"] = "full_recording"
        full["disabled_buttons"] = ["Minus", "Plus", "Up"]
        validate_profile(full, loadout="full")
        for key in ("R", "RS"):
            bad = deepcopy(full)
            bad["stage_evidence"]["button_" + key]["valid"] = False
            with self.assertRaises(ValueError):
                validate_profile(bad, loadout="full")

    def test_offline_issue_keeps_interrupted_run_and_unconfirmed_buttons_honest(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            base = work / "base.json"
            src = profile()
            src.update(complete=False, scope="direction_check_only")
            src["gyro_mapping"]["roll"]["valid"] = False
            base.write_text(json.dumps(src))
            check = work / "check"
            check.mkdir()
            result = dict(
                source="human_USB",
                direction_check_only=True,
                frames=2,
                complete=False,
                errors=["interrupted"],
                controller=dict(calibration_file=str(base), sdl_mapping="test"),
            )
            (check / "result.json").write_text(json.dumps(result))
            (check / "usb-inputs.jsonl").write_text(
                3 * (json.dumps(dict(gyro_native_matrix=NATIVE_GYRO_MATRIX)) + "\n")
            )
            for name in ("inputs-per-present.jsonl", "native-barriers.jsonl"):
                (check / name).write_text("{}\n")
            issued = issue(base, check, work / "issued", "正常")
            p = json.loads(Path(issued["profile"]).read_text())
            self.assertTrue(p["complete"])
            self.assertFalse(p["stop_combo_enabled"])
            self.assertEqual(p["unconfirmed_buttons"], ["Minus", "Plus", "Up"])
            self.assertFalse(p["in_game_direction_validation"]["run_completed"])
            self.assertFalse(
                p["gyro_mapping"]["roll"]["isolated_physical_axis_confirmed"]
            )
            self.assertIn(
                "interrupted", p["in_game_direction_validation"]["end_errors"]
            )
            self.assertEqual(json.loads(base.read_text()), src)

    def test_fixture_dry_run_does_not_construct_controller_or_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            p = work / "profile.json"
            p.write_text(json.dumps(profile()))
            host = work / "host"
            host.write_text("mock")
            host.with_suffix(".build.json").write_text(
                json.dumps(
                    dict(
                        test_feature="demonstration_capture",
                        render_mode="none",
                        direct_aim=False,
                    )
                )
            )
            args = argparse.Namespace(
                fixture=True,
                host=host,
                modules=work,
                source="controller",
                controller_profile=p,
                allow_unqualified=True,
                loadout="primary_only",
                dry_run=True,
                out=work / "dry",
            )
            with (
                patch.object(capture, "validate_runtime", return_value=(host, work)),
                patch.object(capture, "safe_out", side_effect=lambda x: Path(x)),
                patch("rl.demo.controller.Controller") as controller,
                patch("rl.demo.controller.C.CDLL") as sdl,
                patch.object(capture, "DemoEnv") as game,
            ):
                self.assertEqual(capture.run(args), 0)
                controller.assert_not_called()
                sdl.assert_not_called()
                game.assert_not_called()
            self.assertTrue(
                json.loads((args.out / "result.json").read_text())["passed"]
            )


if __name__ == "__main__":
    unittest.main()
