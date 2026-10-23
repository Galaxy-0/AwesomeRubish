"""Private exact-triangle ground bins. Never write derived geometry to git.

Navigation nodes remain the paint/scoring domain. Ground support uses the actual
player-collision triangles at query XZ, retaining stacked surfaces and ramps.
"""

import argparse
import json
from pathlib import Path
import numpy as np
from .data import ROOT, sha


def export(source, out, resolution=0.5, native_opening=False):
    from tools.zipcaster.surfaces import load_surfaces

    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / "work"):
        raise ValueError("fresh private data path required")
    tri, normal, _, attrs = load_surfaces(ROOT / "work/arena/maps/Yunohana")
    keep = (abs(normal[:, 1]) >= 0.7) & np.array(
        ["SplPlayer" not in a["col_disable_flags"] for a in attrs]
    )
    tri = tri[keep].astype(np.float32)
    origin = (
        np.floor(tri[:, :, [0, 2]].min((0, 1)) / resolution) * resolution - resolution
    )
    shape = (
        np.ceil((tri[:, :, [0, 2]].max((0, 1)) - origin) / resolution).astype(int) + 2
    )
    bins = {}
    for i, t in enumerate(tri):
        low = np.floor((t[:, [0, 2]].min(0) - origin) / resolution).astype(int)
        high = np.floor((t[:, [0, 2]].max(0) - origin) / resolution).astype(int)
        # Conservative rectangle binning. Runtime barycentrics reject holes,
        # ledges and out-of-triangle parts; no nearest-nav extrapolation.
        for x in range(low[0], high[0] + 1):
            for z in range(low[1], high[1] + 1):
                center = origin + (np.array([x, z]) + 0.5) * resolution
                corners = t[:, [0, 2]]
                edges = np.roll(corners, -1, axis=0) - corners
                cross = edges[:, 0] * (center[1] - corners[:, 1]) - edges[:, 1] * (
                    center[0] - corners[:, 0]
                )
                sign = np.sign(
                    (corners[1, 0] - corners[0, 0]) * (corners[2, 1] - corners[0, 1])
                    - (corners[1, 1] - corners[0, 1]) * (corners[2, 0] - corners[0, 0])
                )
                radius = 0.5 * resolution * np.abs(edges).sum(-1)
                if np.all(sign * cross + radius >= -1e-5):
                    bins.setdefault((x, z), []).append(i)
    width = max(map(len, bins.values()))
    indices = np.full((*shape, width), -1, np.int32)
    for (x, z), ids in bins.items():
        indices[x, z, : len(ids)] = ids
    with np.load(source / "map.npz") as f:
        arrays = {k: f[k] for k in f.files}
    arrays.update(
        ground_triangles=tri,
        ground_bins=indices,
        ground_origin=origin.astype(np.float32),
        ground_resolution=np.float32(resolution),
    )
    out.mkdir(parents=True)
    np.savez_compressed(out / "map.npz", **arrays)
    parameters = json.loads((source / "parameters.json").read_text())
    parameters["map_export_sha256"] = sha(out / "map.npz")
    parameters["ground_support"] = (
        "exact player triangle barycentrics, conservative .5u bins; old voxel side collisions and paint navigation retained"
    )
    parameters["parent_parameters_sha256"] = sha(source / "parameters.json")
    if native_opening:
        path = ROOT / "work/sim/window-20261021/models-v2/opening.json"
        parameters["opening"] = json.loads(path.read_text())
        parameters["opening_source_sha256"] = sha(path)
    (out / "parameters.json").write_text(json.dumps(parameters, indent=2) + "\n")
    report = dict(
        schema="inklab.ground.triangles.v1",
        source=str(source),
        source_sha256=sha(source / "map.npz"),
        output_sha256=sha(out / "map.npz"),
        resolution=resolution,
        shape=shape.tolist(),
        triangles=len(tri),
        candidates_per_query=width,
        source_geometry_sha256=sha(ROOT / "work/arena/maps/Yunohana/human.npz"),
        limitations=[
            "walkable triangle normals >=.7, XZ point support; capsule side collision remains coarse voxels",
            "navigation/paint cells unchanged; no native dynamic obstacles",
        ],
    )
    (out / "ground-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", default="work/rl-stage0/data-v5")
    p.add_argument("--out", required=True)
    p.add_argument("--resolution", type=float, default=0.5)
    p.add_argument("--native-opening", action="store_true")
    a = p.parse_args()
    export(a.source, a.out, a.resolution, a.native_opening)
