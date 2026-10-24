"""Recheck saved gyro onsets and prepare a strictly scoped in-game direction profile.

No SDL initialization, game launch, or edits to the source recording.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import time

from .controller_check import (
    DEFAULT_BINDINGS,
    NATIVE_GYRO_MATRIX,
    gyro_gesture,
    gyro_mapping,
    load_base_profile,
    validate_profile,
)


def recheck(source, out, threshold=0.35):
    if not 0.05 <= threshold <= 3:
        raise ValueError("onset threshold must be .05–3 rad/s")
    source, out = Path(source).resolve(), Path(out).resolve()
    if "work" not in source.parts or "work" not in out.parts:
        raise ValueError("private work/ source and new output required")
    if out.exists():
        raise FileExistsError(out)
    profile = load_base_profile(source / "profile.json")
    rows = {}
    with (source / "samples.jsonl").open() as stream:
        for line in stream:
            r = json.loads(line)
            stage = r.get("check_stage", "")
            if stage.startswith("gyro_") and ":" not in stage:
                rows.setdefault(stage, []).append(r)
    results = {
        stage: gyro_gesture(
            values,
            profile["gyro_bias_rad_s"],
            threshold=threshold,
            expected_axis=dict(yaw=1, pitch=0, roll=2)[stage.split("_")[1]],
        )
        for stage, values in rows.items()
    }
    mapping = gyro_mapping(results)
    # Retain the already accepted pitch pair; distinguish this basis from the new onset test.
    if not mapping["pitch"]["valid"]:
        mapping["pitch"] = dict(
            profile["gyro_mapping"]["pitch"], basis="previous accepted pitch pair"
        )
    expected = dict(pitch=(0, 1), yaw=(1, -1), roll=(2, -1))
    agreed = {
        name: bool(v["valid"] and (v["axis"], v["sign"]) == expected[name])
        for name, v in mapping.items()
    }
    for name in ("yaw", "roll"):
        if not agreed[name]:
            mapping[name] = dict(
                valid=False,
                axis=expected[name][0],
                sign=expected[name][1],
                basis="SDL convention assumption",
            )
        else:
            mapping[name]["basis"] = "003 first threshold onset agrees with SDL"
    sticks = [
        v
        for k, v in profile.get("stage_evidence", {}).items()
        if k.startswith("stick_")
    ]
    profile.update(
        gyro_mapping=mapping,
        gyro_native_matrix=NATIVE_GYRO_MATRIX,
        gyro_native_basis="11.3.0 camera transfer and direction-check-001; game-view recheck pending",
        complete=all(agreed.values())
        and len(sticks) == 8
        and all(v["valid"] for v in sticks)
        and profile.get("stable", False),
        native_camera_validation="pending user in-game direction check",
        unconfirmed_buttons=sorted(set(DEFAULT_BINDINGS) - profile["bindings"].keys()),
        stop_combo_enabled=False,
        only="offline_recheck",
    )
    if not profile["complete"]:
        profile.update(scope="direction_check_only", usable_for_direction_check=True)
    files = ("profile.json", "summary.json", "report.md", "samples.jsonl")
    audit = dict(
        schema="controller-onset-recheck-v1",
        threshold_rad_s=threshold,
        source_sha256={
            str(source / f): hashlib.sha256((source / f).read_bytes()).hexdigest()
            for f in files
        },
        first_onsets=results,
        agrees_with_SDL=agreed,
        generated_profile_complete=profile["complete"],
        conclusion="confirmed"
        if profile["complete"]
        else "conflict; SDL yaw/roll assumptions for direction check ONLY",
    )
    validate_profile(profile, allow_direction_check=True)
    out.mkdir(parents=True)
    (out / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n"
    )
    (out / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    )
    return audit


class DirectionMonitor:
    """Throttled terminal hints; raw axes, intended direction, and native view deltas."""

    def __init__(self, emit=print):
        self.emit, self.last, self.view = emit, -math.inf, None

    def update(self, row, info, now=None):
        now = time.monotonic() if now is None else now
        if now - self.last < 0.25:
            return
        self.last = now
        pitch, yaw, roll = row.get("physical_gyro_turns_s", row["gyro"])

        def label(v, pos, neg):
            return pos if v > 0.015 else neg if v < -0.015 else "静止"

        msg = (
            f"[方向短测] 手柄 yaw={label(yaw, '右', '左')} pitch={label(pitch, '抬头', '低头')} "
            f"roll={label(roll, '右倾', '左倾')}；SDL rad/s="
            + ",".join(f"{v:+.2f}" for v in row["gyro_rad_s"])
            + "；HID turns/s="
            + ",".join(f"{v:+.3f}" for v in row["gyro"])
        )
        view = info.get("own_view", {})
        if info.get("phase") == 1 and view.get("valid"):
            current = (view["yaw"], view["pitch"])
            if self.view is not None:
                yaw_delta = math.degrees(
                    math.atan2(
                        math.sin(current[0] - self.view[0]),
                        math.cos(current[0] - self.view[0]),
                    )
                )
                msg += f"；原生镜头 Δyaw={yaw_delta:+.1f}° Δpitch_ctl={current[1] - self.view[1]:+.3f}"
            self.view = current
        else:
            self.view = None
        self.emit(msg + "（输入提示不代表画面方向已核验）", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--threshold", type=float, default=0.35)
    a = p.parse_args()
    print(
        json.dumps(recheck(a.source, a.out, a.threshold), ensure_ascii=False, indent=2)
    )
