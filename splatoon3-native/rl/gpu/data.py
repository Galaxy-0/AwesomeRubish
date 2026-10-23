"""Private derived voxel/navigation export. Never distribute generated output."""

import argparse, json, hashlib, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def export(out, resolution=1.0):
    from tools.zipcaster.surfaces import load_surfaces

    directory = ROOT / "work/arena/maps/Yunohana"
    nav = json.loads((directory / "navigation.json").read_text())
    points = np.asarray([n[:3] for n in nav["nodes"]], np.float32)
    valid = np.asarray([n[3] for n in nav["nodes"]], bool)
    xz = np.rint(points[:, [0, 2]]).astype(int)
    lo = xz.min(0) - 2
    shape = xz.max(0) - lo + 3
    counts = {}
    for x, z in xz:
        counts[x, z] = counts.get((x, z), 0) + 1
    layers = max(counts.values())
    floor = np.full((*shape, layers), -100.0, np.float32)
    indices = np.full((*shape, layers), -1, np.int64)
    groups = {}
    for i, (x, z) in enumerate(xz):
        groups.setdefault((x, z), []).append(i)
    for (x, z), ids in groups.items():
        ids = sorted(ids, key=lambda i: points[i, 1])
        floor[x - lo[0], z - lo[1], : len(ids)] = points[ids, 1]
        indices[x - lo[0], z - lo[1], : len(ids)] = ids
    tri, norm, area, attrs = load_surfaces(directory)
    # Keep the same body-domain family, with hook/material metadata separately.
    keep = np.array(["SplPlayer" not in a["col_disable_flags"] for a in attrs])
    tri, norm = tri[keep], norm[keep]
    attrs = [a for a, k in zip(attrs, keep) if k]
    origin = np.floor(tri.min((0, 1)) / resolution) * resolution - 2 * resolution
    dims = np.ceil((tri.max((0, 1)) - origin) / resolution).astype(int) + 3
    vox = np.zeros(tuple(dims), np.uint8)
    normals = np.zeros((*dims, 3), np.float32)
    planes = np.zeros(tuple(dims), np.float32)
    for t, n, att in zip(tri, norm, attrs):
        axis = int(np.abs(n).argmax())
        uv = [i for i in range(3) if i != axis]
        a, b, c = t[:, uv]
        ab = b - a
        ac = c - a
        den = ab[0] * ac[1] - ab[1] * ac[0]
        if abs(den) < 1e-10:
            continue
        low = np.floor((t[:, uv].min(0) - origin[uv]) / resolution).astype(int)
        high = np.ceil((t[:, uv].max(0) - origin[uv]) / resolution).astype(int)
        uu, vv = np.meshgrid(
            np.arange(low[0], high[0] + 1),
            np.arange(low[1], high[1] + 1),
            indexing="ij",
        )
        flat = np.stack([uu.ravel(), vv.ravel()], 1)
        xy = origin[uv] + flat * resolution
        delta = xy - a
        u = (delta[:, 0] * ac[1] - delta[:, 1] * ac[0]) / den
        v = (ab[0] * delta[:, 1] - ab[1] * delta[:, 0]) / den
        good = (u >= -0.02) & (v >= -0.02) & (u + v <= 1.02)
        flat, u, v = flat[good], u[good], v[good]
        xyz = np.zeros((len(flat), 3), int)
        xyz[:, uv] = flat
        h = t[0, axis] + u * (t[1, axis] - t[0, axis]) + v * (t[2, axis] - t[0, axis])
        xyz[:, axis] = np.rint((h - origin[axis]) / resolution).astype(int)
        hook = (
            "SuperHookCantBind" not in att["mat_flags"]
            and "SplPlayerSuperHookCheck" not in att["col_disable_flags"]
            and "Fence" not in att["mat_flags"]
        )
        kind = (1 if abs(n[1]) >= 0.7 else 2) | (4 if hook else 0)
        key = tuple(xyz.T)
        vox[key] = kind
        normals[key] = n
        planes[key] = np.dot(n, t[0])
    out = Path(out).resolve()
    if not out.is_relative_to(ROOT / "work"):
        raise ValueError("private exports must be under work/")
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out / "map.npz",
        points=points,
        paintable=valid,
        floors=floor,
        cell_ids=indices,
        grid_origin=lo,
        voxels=vox,
        normals=normals,
        planes=planes,
        voxel_origin=origin.astype(np.float32),
        voxel_resolution=np.float32(resolution),
        spawn=np.asarray(
            [nav["spawns"][k]["ground"] for k in ["alpha", "bravo"]], np.float32
        ),
    )
    source = [
        "work/sim/parameters.json",
        "work/sim/window-20261021/models-v2/motion.json",
        "work/d3/parameters.json",
        "work/d3/hint-parameters.json",
        "work/sim/advanced/model.json",
        "work/d4/graph-v2-Yunohana/graph.json",
    ]
    saber = json.loads((ROOT / source[0]).read_text())
    motion = json.loads((ROOT / source[1]).read_text())
    gun = json.loads((ROOT / source[2]).read_text())
    sp = json.loads((ROOT / source[3]).read_text())
    params = {
        "schema": "inklab.rl.gpu.private.v1",
        "saber": saber,
        "motion": motion,
        "gun": gun,
        "zipcaster": sp,
        "advanced": json.loads((ROOT / source[4]).read_text()),
        "flight": json.loads((ROOT / source[5]).read_text())["flight_model"],
        "sources": {p: sha(ROOT / p) for p in source},
        "navigation_sha256": sha(directory / "navigation.json"),
        "geometry_sha256": sha(directory / "human.npz"),
        "map_export_sha256": sha(out / "map.npz"),
        "limitations": [
            "1u surface voxelization and nearest navigation support, not native collision",
            "native camera calibration is separate and mandatory",
            "No game render assets included",
        ],
    }
    (out / "parameters.json").write_text(json.dumps(params, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(out),
                "voxel_shape": list(map(int, dims)),
                "navigation": len(points),
                "layers": layers,
                "bytes": (out / "map.npz").stat().st_size,
            }
        )
    )


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--resolution", type=float, default=1.0)
    args = a.parse_args()
    sys.path.insert(0, str(ROOT))
    export(args.out, args.resolution)
