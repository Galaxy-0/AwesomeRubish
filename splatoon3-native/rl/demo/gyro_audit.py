"""Offline USB -> injected HID -> native view audit; never opens SDL or a game."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

from .controller_check import NATIVE_GYRO_MATRIX, validate_profile


def load_lines(path):
    with path.open() as stream:
        return [json.loads(line) for line in stream]


def response_windows(
    raw, sticks, cameras, valid, times, lag, axis, resets=None, elevations=None
):
    """Fixed nonoverlapping 16f bins; exclude sticks, clipping, mixed/reversing motion.

    Use explicitly stamped D3R_STATE, not repeated ACK view snapshots. Sweep
    causal lag rather than claiming an exact latency from a human free-motion run.
    """
    output, rows = (0 if axis == 1 else 1), []
    for start in range(300, len(raw) - 24, 16):
        end = start + 16
        rr = raw[start - lag : end - lag]
        mean, rms = rr.mean(0), np.sqrt(np.mean(rr**2, axis=0))
        if (
            not valid[start : end + 1].all()
            or not np.isfinite(cameras[start : end + 1]).all()
        ):
            continue
        if abs(sticks[start - lag : end - lag, 2:]).max() > 0.01:
            continue
        if resets is not None and resets[max(0, start - lag - 15) : end + 15].any():
            continue
        if rms[axis] < 0.3 or rms[axis] < 3 * max(
            rms[i] for i in range(3) if i != axis
        ):
            continue
        if abs(mean[axis]) < 0.85 * rms[axis]:
            continue
        if abs(cameras[start : end + 1, 1]).max() > (0.3 if axis == 1 else 0.85):
            continue
        delta = cameras[end] - cameras[start]
        delta[0] = math.atan2(math.sin(delta[0]), math.cos(delta[0]))
        if axis == 0 and elevations is not None:
            delta[1] = elevations[end] - elevations[start]
        elapsed = (times[end - lag] - times[start - lag]) / 1e9
        camera_rate = delta[output] * 60 / 16
        rows.append(
            dict(
                frames=[start, end],
                hand_rad_s=float(mean[axis]),
                camera_rad_s=float(camera_rate),
                camera_wall_rad_s=float(delta[output] / elapsed),
                gain_abs=float(abs(camera_rate / mean[axis])),
                gain_wall_abs=float(abs(delta[output] / elapsed / mean[axis])),
            )
        )
    if not rows:
        return dict(windows=0, rows=[])
    x, y = np.array([[r["hand_rad_s"], r["camera_rad_s"]] for r in rows]).T
    return dict(
        windows=len(rows),
        median_abs_gain=float(np.median([r["gain_abs"] for r in rows])),
        median_wall_abs_gain=float(np.median([r["gain_wall_abs"] for r in rows])),
        slope_camera_per_hand=float(x @ y / (x @ x)),
        camera_hand_same_sign_fraction=float(np.mean(x * y > 0)),
        rows=rows,
    )


def analyze(source, out, calibration):
    source, out, calibration = (
        Path(source).resolve(),
        Path(out).resolve(),
        Path(calibration).resolve(),
    )
    if "work" not in source.parts or "work" not in out.parts or out.exists():
        raise ValueError("private work/ source and NEW output required")
    result = json.loads((source / "result.json").read_text())
    usb = load_lines(source / "usb-inputs.jsonl")
    actions = load_lines(source / "inputs-per-present.jsonl")
    barriers = load_lines(source / "native-barriers.jsonl")
    if len(usb) != len(actions) or len(barriers) != len(actions) + 1:
        raise ValueError("input/USB/barrier counts disagree")
    if [r["frame"] for r in usb] != list(range(len(usb))):
        raise ValueError("USB frames not consecutive")
    profile_path = Path(result["controller"]["calibration_file"]).resolve()
    profile = json.loads(profile_path.read_text())
    raw = np.array([r["gyro_rad_s"] for r in usb]) - profile["gyro_bias_rad_s"]
    logged = np.array([r["gyro"] for r in usb])
    injected = np.array([r["actions"]["player_0"]["gyro"] for r in actions])
    old_mapping = [profile["gyro_mapping"][k] for k in ("pitch", "yaw", "roll")]
    expected = np.stack(
        [raw[:, v["axis"]] * v["sign"] / (2 * np.pi) for v in old_mapping], axis=1
    )
    if "gyro_native_matrix" in profile:
        expected = raw @ np.asarray(profile["gyro_native_matrix"]).T / (2 * np.pi)
    sticks = np.array([r["actions"]["player_0"]["sticks"] for r in actions])
    resets = np.array([r["actions"]["player_0"]["buttons"][5] for r in actions], bool)
    times = np.array([r["sample_monotonic_ns"] for r in usb])
    base = barriers[0]["infos"]["player_0"]["frame"]
    log = Path(result["session"]) / "player-0/host.log"
    text = log.read_text()
    cameras = np.full((len(barriers), 2), np.nan)
    elevation_pairs = []
    actual_elevations = np.full(len(barriers), np.nan)
    for m in re.finditer(
        r"D3R_STATE frame=(\d+)[^\n]*? yaw=([^ ]+) pitch=([^ ]+) v17b8=([^ ]+) v17c4=([^ ]+)",
        text,
    ):
        frame = int(m[1]) - base
        if not 0 <= frame < len(cameras):
            continue
        cameras[frame] = [float(m[2]), float(m[3])]
        eye, at = (np.array(list(map(float, m[k].split(",")))) for k in (4, 5))
        vector = at - eye
        elevation = math.atan2(vector[1], math.hypot(vector[0], vector[2]))
        actual_elevations[frame] = elevation
        if abs(float(m[3])) < 0.9:
            elevation_pairs.append([float(m[3]), elevation])
    if np.isfinite(cameras[:, 0]).sum() < len(actions) * 0.95:
        raise ValueError("insufficient source-stamped native camera truth")
    valid = np.array(
        [
            r["infos"]["player_0"]["alive"]
            and r["infos"]["player_0"]["position_valid"]
            and r["infos"]["player_0"]["position"][1] < 20
            for r in barriers
        ],
        bool,
    )
    old = json.loads(calibration.read_text())
    response = np.asarray(old["gyro_matrix"]) * 60 / (2 * np.pi)
    coefficients = np.linalg.lstsq(
        np.column_stack(
            [np.array(elevation_pairs)[:, 0], np.ones(len(elevation_pairs))]
        ),
        np.array(elevation_pairs)[:, 1],
        rcond=None,
    )[0]
    options = re.findall(r"R0_INPUT_OPTIONS[^\n]+", text)
    if not any(
        "stick_digital=20 gyro_digital=20 gyro_on=1" in line for line in options
    ):
        raise ValueError("missing native +5/gyro-on evidence")
    paths = [
        source / f
        for f in (
            "usb-inputs.jsonl",
            "inputs-per-present.jsonl",
            "native-barriers.jsonl",
            "result.json",
        )
    ]
    paths += [profile_path, calibration, log]
    audit = dict(
        schema="gyro-native-transfer-audit-v1",
        source=str(source),
        source_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
        frames=len(actions),
        controlled_fps=result["controlled_presents_per_second"],
        raw_bias_corrected_peak_rad_s=abs(raw).max(0).tolist(),
        injected_peak_turns_s=abs(injected).max(0).tolist(),
        conversion_max_abs_error=float(abs(expected - logged).max()),
        injection_max_abs_error=float(abs(injected - logged).max()),
        clipped_components=int((abs(logged) >= 8).sum()),
        gyro_software_deadzone=0,
        native_options=options,
        native_single_axis_transfer=response.tolist(),
        native_single_axis_units="yaw rad/s and pitch CONTROL-value/s per HID axis rad/s; pitch field is not identical to eye->at elevation",
        eye_at_elevation_vs_pitch=dict(
            slope=float(coefficients[0]),
            intercept_rad=float(coefficients[1]),
            correlation=float(np.corrcoef(np.array(elevation_pairs).T)[0, 1]),
        ),
        motion_windows={
            str(lag): {
                name: response_windows(
                    raw,
                    sticks,
                    cameras,
                    valid,
                    times,
                    lag,
                    axis,
                    resets,
                    actual_elevations,
                )
                for name, axis in (("yaw", 1), ("pitch", 0))
            }
            for lag in (0, 2, 4, 6, 8)
        },
        corrected_native_matrix=NATIVE_GYRO_MATRIX,
        predicted_corrected_gain=dict(
            yaw=float(response[0, 2]), pitch_control=float(-response[1, 0])
        ),
        limitations=[
            "human free motion, mixed axes and native camera transients; not an independent Switch hardware gain measurement",
            "single-axis calibration predicts corrected response; direction-check-002 not yet run",
            "native Y/roll projection at large pose changes remains unqualified",
        ],
    )
    fixed = dict(
        profile,
        gyro_native_matrix=NATIVE_GYRO_MATRIX,
        gyro_native_basis="001 raw/injection/native log audit + existing independent single-axis calibration",
        native_camera_validation="pitch inverted and yaw wrong HID axis diagnosed; 002 visual confirmation pending",
        scope="direction_check_only",
        complete=False,
        usable_for_direction_check=True,
        supersedes_profile=str(profile_path),
    )
    validate_profile(fixed, allow_direction_check=True)
    out.mkdir(parents=True)
    (out / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    )
    (out / "profile.json").write_text(
        json.dumps(fixed, ensure_ascii=False, indent=2) + "\n"
    )
    return audit


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument(
        "--calibration",
        type=Path,
        default="work/rl-demo/run70/bc-periodic-full-r1/camera-response.json",
    )
    a = p.parse_args()
    report = analyze(a.source, a.out, a.calibration)
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("source_sha256", "motion_windows")
            },
            indent=2,
        )
    )
