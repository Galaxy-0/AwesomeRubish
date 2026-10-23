"""Controlled paint UV audit. Fits hypotheses; never promotes them to dense truth."""

import argparse
import json
from pathlib import Path
import re
import numpy as np
from PIL import Image
from .capture import write


def audit(source):
    source = Path(source)
    r = json.loads((source / "result.json").read_text())
    if r.get("paint_native_pitch", 1) > -0.5:
        raise ValueError(
            "downward-control corpus required; earlier upward wall tests are not floor controls"
        )
    controls = {x["label"]: x for x in r["ink_controls"]}
    life = []
    for line in (Path(r["session"]) / "player-0/host.log").open():
        m = re.search(
            r"DEMO_TRUTH_LIFE frame=(\d+) event=3 object=\w+ vtable=5c75510 valid=1 position=([^ ]+)",
            line,
        )
        if m:
            life.append((int(m[1]), list(map(float, m[2].split(",")))))
    pairs = [
        ("before-paint", "after-paint-0"),
        *[(f"floor-anchor-{n}-before", f"floor-anchor-{n}-after") for n in range(3)],
        ("high-spawn-before", "high-spawn-after"),
    ]
    points = []
    for before, after in pairs:
        a, b = controls[before], controls[after]
        stops = [p for f, p in life if a["absolute_frame"] < f <= b["absolute_frame"]]
        if not stops:
            continue
        for file in (source / "ink-targets").glob(
            f"frame-{b['absolute_frame']}-target-*.png"
        ):
            tag = file.stem.split("target-")[1]
            old = source / f"ink-targets/frame-{a['absolute_frame']}-target-{tag}.png"
            if not old.exists():
                continue
            x = np.array(Image.open(file).convert("RGB"), np.int16)
            y = np.array(Image.open(old).convert("RGB"), np.int16)
            weight = np.maximum(x[..., 0] - y[..., 0], 0).astype(float)
            if weight.sum() < 1:
                continue
            yy, xx = np.indices(weight.shape)
            uv = [
                float((xx * weight).sum() / weight.sum()),
                float((yy * weight).sum() / weight.sum()),
            ]
            points.append(
                dict(
                    label=after,
                    world_stop=np.median(stops, axis=0).tolist(),
                    uv_centroid=uv,
                    positive_r_pixels=int((weight > 0).sum()),
                    method="positive native R increment centroid vs actual native release stop",
                )
            )
    floor = [x for x in points if abs(x["world_stop"][1] - 3) < 0.1]
    high = [x for x in points if x not in floor]
    if len(floor) < 4:
        raise ValueError("four non-collinear floor controls required")
    world = np.array([p["world_stop"] for p in floor])
    uv = np.array([p["uv_centroid"] for p in floor])
    design = np.c_[world[:, [0, 2]], np.ones(len(world))]
    train = np.arange(3)
    fit = np.linalg.lstsq(design[train], uv[train], rcond=None)[0]
    error = np.linalg.norm(design @ fit - uv, axis=1)
    high_errors = [
        float(
            np.linalg.norm(
                np.r_[np.array(p["world_stop"])[[0, 2]], 1] @ fit - p["uv_centroid"]
            )
        )
        for p in high
    ]
    report = dict(
        schema="inklab.rl.demo.ink-uv-audit.v1",
        source=str(source),
        points=points,
        floor_affine_coefficients=fit.tolist(),
        floor_fit_rank=int(np.linalg.matrix_rank(design[train])),
        fit_point_errors_pixels=error[:3].tolist(),
        held_out_floor_error_pixels=float(error[3]),
        high_platform_xz_affine_errors_pixels=high_errors,
        world_dense_paint_qualified=False,
        team_channels_scoped="native role0 R; role1 G, this two-team setup only",
        conclusion="Local floor affine hypothesis can be tested, but is not a verified full-world/multilayer projection. Do not unmask minimap/ray ink.",
        remaining=[
            "Recover ColPaint panel/triangle ownership and UV mapping or a native world-surface ink query.",
            "Require held-out high platforms, walls, overlapped levels, both-team overwrite and native paintability thresholds.",
            "Sparse snapshots do not certify the dense map between painting events; cadence must also be addressed.",
        ],
    )
    write(source / "ink-mapping-audit.json", report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("recording")
    audit(p.parse_args().recording)
