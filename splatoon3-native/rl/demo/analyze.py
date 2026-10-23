"""Join owned native display callbacks with input receipt timestamps; no images."""

import argparse
import json
from pathlib import Path
import re
import numpy as np
from .capture import write


def stats(a):
    return (
        {
            k: float(v)
            for k, v in zip(
                ["min", "p50", "p95", "max"], np.percentile(a, [0, 50, 95, 100])
            )
        }
        if len(a)
        else None
    )


def rates(milliseconds):
    a = np.asarray(milliseconds, float)
    a = a[a > 0]
    if not len(a):
        return None
    slow = np.sort(a)[-max(1, int(np.ceil(len(a) * 0.01))) :]
    return dict(
        samples=len(a),
        median_fps=float(1000 / np.median(a)),
        one_percent_low_fps=float(1000 / slow.mean()),
        average_fps=float(1000 / a.mean()),
        definition="1% low = 1000 / mean of slowest1% frame intervals",
    )


def analyze(directory):
    out = Path(directory)
    result = json.loads((out / "result.json").read_text())
    rows = [json.loads(x) for x in (out / "native-barriers.jsonl").open()]
    timing = [json.loads(x) for x in (out / "timing.jsonl").open()]
    origin = rows[0]["infos"]["player_0"]["frame"]
    session = Path(result["session"])
    raw_displayed = {
        int(f): int(t)
        for f, t in re.findall(
            r"DEMO_DISPLAY frame=(\d+) ticket=\d+ presented_ns=(\d+)",
            (session / "player-0/host.log").read_text(),
        )
    }
    displayed = {
        int(f): int(t)
        for f, t in re.findall(
            r"DEMO_DISPLAY frame=(\d+) ticket=\d+ presented_ns=(\d+)",
            (session / "player-0/host.log").read_text(),
        )
        if int(t) > 0
    }
    # gfx enqueue's frame is the previous completed native present, i.e. the
    # input frame (origin + relative ACK - 1). Retain match/negative counts.
    latency = []
    missing = 0
    negative = 0
    ts = []
    for r in timing:
        native = origin + r["frame"] - 1
        if native not in displayed:
            missing += 1
            continue
        delta = (displayed[native] - r["send_ns"]) / 1e6
        if delta < 0:
            negative += 1
        else:
            latency.append(delta)
            ts.append(displayed[native])
    visible_frames = sorted(f for f in displayed if origin <= f < origin + len(timing))

    def visible_intervals(frames):
        # A zero presentedTime is not proof of a slow visible frame (occlusion,
        # foreground changes or a discarded drawable). Never bridge it as FPS.
        return [
            (displayed[b] - displayed[a]) / 1e6
            for a, b in zip(frames, frames[1:])
            if b == a + 1
        ]

    intervals = np.asarray(visible_intervals(visible_frames))
    logic_ms = np.diff([r["ack_ns"] for r in timing]) / 1e6
    warm = [
        r
        for r in timing
        if 600 <= r["frame"] < min(len(rows), 10800)
        and rows[r["frame"]]["infos"]["player_0"]["phase"] == 1
    ]
    profile = {}
    for n in range(2):
        file = session / f"player-{n}/nvn.tsv"
        values = {}
        if file.exists():
            base = rows[0]["infos"][f"player_{n}"]["frame"]
            for line in file.open():
                cells = line.strip().split("\t")
                if len(cells) != 3:
                    continue
                try:
                    f = int(cells[0])
                    v = float(cells[2])
                except ValueError:
                    continue
                if base + 600 <= f < base + min(len(rows), 10800):
                    values.setdefault(cells[1], []).append(v)
            for key in [
                "@cpu_ms",
                "@proc_cpu_ms",
                "@sub_cpu_ms",
                "@sub_wall_ms",
                "@gpu_ms",
                "@wait_ms",
                "@pq_wait_ms",
                "@drawable_ms",
                "@pso_new",
                "@lib_new",
                "@make_ms",
            ]:
                if key in values:
                    profile[f"player_{n}:" + key] = stats(values[key])
    warm_native_frames = {origin + r["frame"] - 1 for r in warm}
    age = []
    for r in rows:
        for i in r["infos"].values():
            if i.get("position_valid"):
                age.append(i["frame"] - i["position_sample_frame"])
    text = (session / "player-0/host.log").read_text()
    readback = re.findall(
        r"R0_INPUT_OPTIONS[^\n]*stick_digital=20 gyro_digital=20 gyro_on=1[^\n]*", text
    )
    report = dict(
        schema="inklab.rl.demo.latency.v1",
        samples=len(latency),
        logic_frame_rates=rates(logic_ms),
        display_frame_rates=rates(intervals),
        warm_logic_frame_rates=rates(np.diff([r["ack_ns"] for r in warm]) / 1e6),
        warm_display_frame_rates=rates(
            visible_intervals([f for f in visible_frames if f in warm_native_frames])
        ),
        warmup_exclusion_frames=600,
        zero_presented_time_frames=sum(
            v == 0
            for f, v in raw_displayed.items()
            if origin <= f < origin + len(timing)
        ),
        display_rate_scope="Only adjacent native frames with positive drawable presentedTime; no FPS inferred across occluded/discarded gaps. These conditional rates do not certify continuous display60.",
        cpu_gpu_profile=profile,
        realtime_60_passed=False,
        realtime_scope="Report measured rates only; fixed60 advances game time per frame and never certifies real-time wall speed.",
        missing_or_dropped=missing,
        negative_clock_or_mapping_mismatch=negative,
        software_input_to_corresponding_drawable_presented_ms=stats(latency),
        display_interval_ms=stats(intervals),
        observed_display_fps=1000 / float(np.mean(intervals))
        if len(intervals)
        else None,
        native_position_sample_age_frames=stats(age),
        plus5_gyro_readback=bool(readback),
        frame_join="gfx frame == input native frame == origin + ACK relative frame - 1",
        scope="Software command send -> actual drawable presentedTime on common mach monotonic clock. Does not include USB polling or physical switch-to-photon latency. Frames without callback remain missing.",
        human_full_render_verified=("A8_CAMERA skipped=" not in text),
        full_render_compile_verified="-DSPL3_A8_CAMERA=1"
        not in json.loads(
            Path(result.get("host", "work/rl-demo/host-r1/dmhost-demo"))
            .with_suffix(".build.json")
            .read_text()
        )["command"],
    )
    write(out / "latency.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("recording")
    analyze(p.parse_args().recording)
