"""Numeric present/CPU/GPU attribution; raw records remain under private work/."""

import argparse
import collections
import csv
import json
from pathlib import Path
import re

import numpy as np
from rl.demo.analyze import analyze


def stats(values, milliseconds=False):
    a = np.asarray(values, float)
    result = (
        dict(
            n=len(a),
            mean=float(a.mean()),
            p50=float(np.median(a)),
            p95=float(np.percentile(a, 95)),
            p99=float(np.percentile(a, 99)),
            max=float(a.max()),
        )
        if len(a)
        else None
    )
    if result and milliseconds:
        result["over_16_667_fraction"] = float((a > 1000 / 60).mean())
    return result


def report(out):
    out = Path(out)
    result = json.loads((out / "result.json").read_text())
    latency = analyze(out)
    session = Path(result["session"])
    record = dict(
        source=str(out),
        frames=result["frames"],
        errors=result["errors"],
        complete=result["complete"],
        role={},
        performance={
            k: latency[k]
            for k in [
                "warm_logic_frame_rates",
                "warm_display_frame_rates",
                "software_input_to_corresponding_drawable_presented_ms",
                "zero_presented_time_frames",
                "display_rate_scope",
            ]
        },
        scope="diagnostic instrumentation, short script room; not realtime60 or native-equivalence qualification",
    )
    names = (Path("upstream/dm/gfx/nvn/nvn_obj.h")).read_text()
    names = re.findall(
        r"\bOP_[A-Z0-9_]+\b", names.split("enum {", 1)[1].split("};", 1)[0]
    )
    for role in [0, 1]:
        base = result["origins"][f"player_{role}"]["frame"]
        warm = lambda f: base + 600 <= f < base + result["frames"]
        log = (session / f"player-{role}/host.log").read_text(errors="replace")
        pacing = [
            dict(
                zip(
                    [
                        "frame",
                        "mono_ns",
                        "interval",
                        "latched",
                        "game_fps",
                        "target_fps",
                        "display_mode",
                        "hz",
                    ],
                    map(int, m),
                )
            )
            for m in re.findall(
                r"DEMO_PACING frame=(\d+) mono_ns=(\d+) raw_interval=(-?\d+) latched_interval=(\d+) game_fps=(\d+) target_fps=(\d+) display_mode=(\d+) hz=(\d+)",
                log,
            )
        ]
        changes = [
            r
            for i, r in enumerate(pacing)
            if i == 0
            or any(
                r[k] != pacing[i - 1][k]
                for k in ["interval", "target_fps", "game_fps", "display_mode"]
            )
        ]
        rows = collections.defaultdict(list)
        for f, k, value in csv.reader(
            (session / f"player-{role}/nvn.tsv").read_text().splitlines()[2:],
            delimiter="\t",
        ):
            if warm(int(f)):
                rows[k].append(float(value))
        metrics = [
            "@frame_ms",
            "@rec_ms",
            "@cpu_ms",
            "@proc_cpu_ms",
            "@sub_wall_ms",
            "@sub_cpu_ms",
            "@demo_sub_begin_ms",
            "@demo_sub_index_ms",
            "@demo_sub_replay_ms",
            "@demo_sub_commit_ms",
            "@demo_shader_make_ms",
            "@gpu_ms",
            "@pso_new",
            "@lib_new",
            "@wait_ms",
            "@draws",
            "@passes",
        ]
        ops = collections.defaultdict(lambda: np.zeros(3))
        sampled = set()
        for f, op, count, wall, cpu in re.findall(
            r"DEMO_OP frame=(\d+) op=(\d+) calls=(\d+) wall_ns=(\d+) cpu_ns=(\d+)", log
        ):
            if warm(int(f)):
                ops[int(op)] += np.array([int(count), int(wall), int(cpu)])
                sampled.add(int(f))
        total = sum(v[1] for v in ops.values())
        detail = dict(
            pacing_samples=len(pacing),
            changes=changes,
            intervals=sorted({r["interval"] for r in pacing}),
            target_fps=sorted({r["target_fps"] for r in pacing}),
            metrics={k: stats(rows[k], k.endswith("_ms")) for k in metrics},
            op_sampled_frames=len(sampled),
        )
        detail["operators"] = [
            {
                "op": names[k],
                "calls_per_frame": float(v[0] / len(sampled)),
                "wall_ms_per_frame": float(v[1] / len(sampled) / 1e6),
                "cpu_ms_per_frame": float(v[2] / len(sampled) / 1e6),
                "wall_fraction": float(v[1] / total),
            }
            for k, v in sorted(ops.items(), key=lambda t: -t[1][1])
        ]
        p = session / f"player-{role}/gpu-pass.tsv"
        if p.exists():
            groups = collections.defaultdict(list)
            count = set()
            for r in csv.DictReader(p.read_text().splitlines()[1:], delimiter="\t"):
                if warm(int(r["frame"])):
                    groups[
                        (
                            r["kind"],
                            int(r["w"]),
                            int(r["h"]),
                            int(r["cfmt"]),
                            int(r["dfmt"]),
                        )
                    ].append(float(r["span_ms"]))
                    count.add(int(r["frame"]))
            summed = sum(sum(v) for v in groups.values())
            detail["gpu_encoder_scope"] = (
                "timestamp boundary spans include scheduling/interference, not exclusive GPU work; diagnostic counter frames excluded from any uninstrumented FPS claim"
            )
            detail["gpu_sampled_frames"] = len(count)
            detail["gpu_encoder_groups"] = [
                dict(
                    kind=k[0],
                    width=k[1],
                    height=k[2],
                    color_format=k[3],
                    depth_format=k[4],
                    encoders=len(v),
                    summed_ms=sum(v),
                    fraction=sum(v) / summed,
                )
                for k, v in sorted(groups.items(), key=lambda t: -sum(t[1]))
            ]
            groups = collections.defaultdict(lambda: np.zeros(4))
            e = p.with_name(p.name + ".events.tsv")
            for r in csv.DictReader(e.read_text().splitlines(), delimiter="\t"):
                if warm(int(r["frame"])):
                    groups[(r["origin"], r["action"])] += np.array(
                        [
                            int(r["ops"]),
                            int(r["bytes"]),
                            int(r["cpu_ns"]),
                            int(r["blocked"]),
                        ]
                    )
            detail["events"] = [
                dict(
                    origin=k[0],
                    action=k[1],
                    count=int(v[0]),
                    bytes=int(v[1]),
                    wall_ms=v[2] / 1e6,
                    blocked=int(v[3]),
                )
                for k, v in groups.items()
            ]
        record["role"][str(role)] = detail
    (out / "profile-summary.json").write_text(json.dumps(record, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                source=str(out),
                performance=record["performance"],
                pacing=record["role"]["0"]["changes"],
            ),
            indent=2,
        )
    )
    return record


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory")
    report(p.parse_args().directory)
