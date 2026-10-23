"""Reduce isolated native probe evidence; maintain measured/assumed boundaries."""

import argparse, json, re, math, statistics, hashlib
from pathlib import Path


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(a):
    root = Path(a.probe)
    result = json.loads((root / "result.json").read_text())
    if result["errors"] or not result.get("probe_completed"):
        raise ValueError("incomplete native probe")
    rows = [json.loads(l) for l in (root / "steps.jsonl").open()]
    log = Path(result["session"]) / "player-0/host.log"
    text = log.read_text()
    command = re.findall(
        r"R0_INPUT_OPTIONS[^\n]*stick_digital=20 gyro_digital=20 gyro_on=1 normalized_by_native=1[^\n]*",
        text,
    )
    live = re.findall(
        r"R0_INPUT_LIVE frame=(\d+) gyro_normalized=([-+\d.e]+) stick_normalized=([-+\d.e]+)",
        text,
    )
    assert (
        command
        and len(live) > 30
        and all(float(g) == 1 and float(s) == 1 for _, g, s in live[-30:])
    )
    states = []
    pattern = r"D3R_STATE frame=(\d+)[^\n]*? yaw=([-+\d.e]+) pitch=([-+\d.e]+) v17b8=([-+\d.e,]+) v17c4=([-+\d.e,]+)"
    for m in re.finditer(pattern, text):
        states.append(
            (
                int(m[1]),
                float(m[2]),
                float(m[3]),
                list(map(float, m[4].split(","))),
                list(map(float, m[5].split(","))),
            )
        )
    rates = {}
    for label in ["right", "left"]:
        window = [
            r["infos"]["player_0"]["frame"]
            for r in rows
            if r["label"] == "rl0-" + label
        ]
        values = [s for s in states if min(window) + 30 < s[0] <= max(window)]
        delta = []
        for old, new in zip(values, values[1:]):
            d = new[1] - old[1]
            delta.append(math.atan2(math.sin(d), math.cos(d)) / (new[0] - old[0]))
        rates[label] = dict(
            n=len(delta),
            mean_radians_per_frame=statistics.mean(delta),
            std=statistics.pstdev(delta),
            min=min(delta),
            max=max(delta),
        )
    idle = [r["infos"]["player_0"] for r in rows if r["label"] == "rl0-idle3"]
    foot = idle[-1]["position"]
    samples = [s for s in states if s[0] >= idle[-8]["frame"]]
    distance = []
    height = []
    forward = []
    pitch = []
    for frame, yaw, logical, eye, at in samples:
        d = [at[i] - eye[i] for i in range(3)]
        distance.append(math.sqrt(sum(x * x for x in d)))
        height.append(at[1] - foot[1])
        forward.append(
            (at[0] - foot[0]) * math.sin(yaw) + (at[2] - foot[2]) * math.cos(yaw)
        )
        pitch.append(math.atan2(d[1], math.hypot(d[0], d[2])) - logical)
    fovs = [
        float(s) for s in re.findall(r"R0_CAMERA[^\n]*fov_candidate=([-+\d.e]+)", text)
    ]
    fov = statistics.median(fovs[-30:])
    config = dict(
        stick_plus5_radians_per_frame=sum(
            abs(r["mean_radians_per_frame"]) for r in rates.values()
        )
        / 2,
        camera_vertical_fov_degrees=fov,
        camera_horizontal_fov_degrees=math.degrees(
            2 * math.atan(math.tan(math.radians(fov / 2)) * 16 / 9)
        ),
        camera_distance=statistics.median(distance),
        camera_target_height=statistics.median(height),
        camera_target_forward=statistics.median(forward),
        camera_pitch_offset_radians=statistics.median(pitch),
    )
    out = dict(
        schema="inklab.rl.stage0.camera.v1",
        config=config,
        measured_option="volatile native control copy digital20/20 gyro1, native normalized1/1. Original/cloned save contents not written by fixture.",
        rates=rates,
        camera_scope="Stationary human, neutral native pitch. Current camera+7c and base+17e4 both55; interpreted as vertical degrees. Eye/at positions measured after settling. Linear pitch/orbit response away from this pose is an approximation, not a full dynamic camera reconstruction.",
        evidence_sha256={
            str(p): digest(p) for p in [root / "result.json", root / "steps.jsonl", log]
        },
        native_plus5_readback_verified=True,
        fov_axis_projection_validation=False,
        accepted=False,
    )
    Path(a.out).write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--probe", required=True)
    p.add_argument("--out", required=True)
    main(p.parse_args())
