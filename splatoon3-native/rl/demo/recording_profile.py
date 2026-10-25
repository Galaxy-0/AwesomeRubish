"""Issue a Stage1 control profile from guided evidence + user visual acceptance.

Offline only: no SDL initialization, controller access, game launch or training.
"""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .controller_check import DEFAULT_BINDINGS, validate_profile


def issue(base, direction_check, out, feedback):
    base, direction_check, out = (
        Path(p).resolve() for p in (base, direction_check, out)
    )
    if any("work" not in p.parts for p in (base, direction_check, out)) or out.exists():
        raise ValueError("private work/ evidence and NEW output required")
    if not feedback.strip():
        raise ValueError("explicit user direction acceptance required")
    source = json.loads(base.read_text())
    result_path = direction_check / "result.json"
    result = json.loads(result_path.read_text())
    if (
        result.get("source") != "human_USB"
        or not result.get("direction_check_only")
        or result.get("frames", 0) <= 0
        or Path(result["controller"]["calibration_file"]).resolve() != base
        or result["controller"]["sdl_mapping"] != source["device"]["sdl_mapping"]
    ):
        raise ValueError("direction check does not match this controller/profile")
    paths = [base, result_path]
    # Verify what reached the recorder, not just the command's profile filename.
    usb = direction_check / "usb-inputs.jsonl"
    count = 0
    with usb.open() as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("gyro_native_matrix") != source.get("gyro_native_matrix"):
                raise ValueError("direction check used another gyro matrix")
            count += 1
    if count < result["frames"]:
        raise ValueError("direction evidence shorter than recorded frames")
    paths += [
        usb,
        direction_check / "inputs-per-present.jsonl",
        direction_check / "native-barriers.jsonl",
    ]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    profile = deepcopy(source)
    stages = profile.get("stage_evidence", {})
    profile["bindings"] = {
        k: v
        for k, v in profile["bindings"].items()
        if stages.get("button_" + k, {}).get("valid")
        and stages["button_" + k].get("binding") == v
    }
    missing = sorted(set(DEFAULT_BINDINGS) - profile["bindings"].keys())
    profile.update(
        scope="primary_only_recording",
        complete=True,
        unconfirmed_buttons=missing,
        disabled_buttons=sorted(set(missing) | {"R", "RS"}),
        stop_combo_enabled=False,
        native_camera_validation="user accepted Stage1 in-game directions in direction-check-002",
        in_game_direction_validation=dict(
            accepted=True,
            user_feedback=feedback,
            evidence=str(direction_check),
            frames=result["frames"],
            run_completed=result.get("complete", False),
            end_errors=result.get("errors", []),
            gyro_native_matrix=deepcopy(source["gyro_native_matrix"]),
            source_sha256=hashes,
        ),
        qualification="Stage1 controls only; not full equipment or BC ready_for_training",
    )
    profile.pop("usable_for_direction_check", None)
    for item in profile["gyro_mapping"].values():
        item["isolated_physical_axis_confirmed"] = item.get("valid", False)
        item["previous_basis"] = item.get("basis")
        item.update(
            valid=True,
            basis="user accepted end-to-end Stage1 gyro path; isolated roll not retested",
        )
    validate_profile(profile, loadout="primary_only")
    out.mkdir(parents=True)
    (out / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n"
    )
    report = dict(
        complete=True,
        scope=profile["scope"],
        profile=str(out / "profile.json"),
        source_sha256=hashes,
        disabled_buttons=profile["disabled_buttons"],
        required_buttons=["ZR", "ZL", "B"],
        user_feedback=feedback,
        direction_run_completed=result.get("complete", False),
        controller_opened=False,
        game_processes_started=False,
    )
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", required=True, type=Path)
    p.add_argument("--direction-check", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument(
        "--feedback",
        required=True,
        help="explicit user visual acceptance, never inferred from completion",
    )
    a = p.parse_args()
    print(
        json.dumps(
            issue(a.base, a.direction_check, a.out, a.feedback),
            ensure_ascii=False,
            indent=2,
        )
    )
