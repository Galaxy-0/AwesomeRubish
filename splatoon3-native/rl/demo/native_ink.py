"""Native ColPaint panel projection and exact-frame ink overlays, offline only.

No atlas/grid/image is shipped. Runtime matrices/readbacks stay in private work/.
Only unique upward panels and unambiguous neutral/full team channels qualify;
no interpolation through time, no wall/overlap/antialias guesses.
"""

import argparse
import json
import math
from pathlib import Path
import re
import numpy as np
from PIL import Image
import torch
from .capture import safe_out, write
from .build_host import sha
from .state_sync import CausalIndex, read_jsonl


def extract(recording, out):
    recording = Path(recording)
    out = safe_out(out)
    out.mkdir(parents=True, exist_ok=False)
    r = json.loads((recording / "result.json").read_text())
    rows = {}
    group = None
    idx = None
    counts = {}
    for line in (Path(r["session"]) / "player-0/host.log").open():
        m = re.search(r"DEMO_TRUTH_PANELS .*pass=(\d+) after=(\d+).*count=(\d+)", line)
        if m:
            group = (int(m[1]), int(m[2]))
            counts[group] = int(m[3])
        m = re.search(r"DEMO_TRUTH_PANEL .*index=(\d+)", line)
        if m:
            idx = int(m[1])
        m = re.search(
            r"kind=(panel_after|panel_uv_after|panel_context_after) .*data=(\w+)", line
        )
        if m and group and group[1]:
            rows.setdefault(group, {}).setdefault(idx, {})[m[1]] = bytes.fromhex(m[2])
    groups = [
        g
        for g in rows
        if counts[g] == 164 and all(len(x) == 3 for x in rows[g].values())
    ]
    if len(groups) != 1:
        raise ValueError("one complete measured Yunohana 164-panel table required")
    panels = rows[groups[0]]
    low = []
    high = []
    basis = []
    uv = []
    for i in range(164):
        d = panels[i]
        b = d["panel_after"]
        low.append(np.frombuffer(b, "<f4", 3, 0x3C).copy())
        high.append(np.frombuffer(b, "<f4", 3, 0x48).copy())
        basis.append(
            np.frombuffer(d["panel_context_after"], "<f4", 9, 0x3C).reshape(3, 3).copy()
        )
        uv.append(np.frombuffer(d["panel_uv_after"], "<f4", 6).reshape(2, 3).copy())
    np.savez_compressed(out / "panels.npz", low=low, high=high, basis=basis, uv=uv)
    write(
        out / "mapping.json",
        dict(
            schema="inklab.native.ink-panels.v1",
            map="Yunohana",
            build_id="28c4287aee36f7499da60f3e68b54c70",
            panels=164,
            panels_sha256=sha(out / "panels.npz"),
            source=str(recording),
            raw_log_sha256=sha(Path(r["session"]) / "player-0/host.log"),
            qualified_scope="unique upward ground panel only",
            projection_source="native Panel+18 2x3 transform, +3c/+48 bounds, context70+3c basis; consumer main+36c6070",
            full_world_surface_membership_qualified=False,
        ),
    )
    print(out, flush=True)


class PanelMap:
    def __init__(self, path):
        with np.load(path) as z:
            self.low = z["low"]
            self.high = z["high"]
            self.basis = z["basis"]
            self.uv = z["uv"]
        self.qualified_panels = None

    def project(self, points):
        points = np.asarray(points)
        shape = points.shape[:-1]
        points = points.reshape(-1, 3)
        coords = np.zeros((len(points), 2))
        valid = np.zeros(len(points), bool)
        ids = np.full(len(points), -1)
        upward = self.basis[:, 2, 1] > 0.999
        for start in range(0, len(points), 2048):
            p = points[start : start + 2048]
            local = np.einsum("pij,nj->npi", self.basis, p)
            inside = (
                (local >= self.low[None] - 0.05) & (local <= self.high[None] + 0.05)
            ).all(-1) & upward[None]
            count = inside.sum(-1)
            pick = inside.argmax(-1)
            n = np.arange(len(p))
            good = count == 1
            if self.qualified_panels is not None:
                # Count ALL upward overlaps first; excluding untested panels
                # before that test would create false uniqueness.
                good &= np.isin(pick, self.qualified_panels)
            delta = local[n, pick, :2] - (self.low[pick, :2] + self.high[pick, :2]) / 2
            mapped = np.einsum(
                "nij,nj->ni", self.uv[pick], np.c_[delta, np.ones(len(p))]
            )
            xy = np.c_[mapped[:, 0], 1 - mapped[:, 1]] * 1600
            good &= np.isfinite(xy).all(-1) & (xy >= 0).all(-1) & (xy < 1600).all(-1)
            coords[start : start + len(p)] = xy
            valid[start : start + len(p)] = good
            ids[start : start + len(p)] = np.where(good, pick, -1)
        return coords.reshape(*shape, 2), valid.reshape(shape), ids.reshape(shape)


def validate_controls(recording, mapping):
    source = Path(recording)
    mapping = Path(mapping)
    audit = json.loads((source / "ink-mapping-audit.json").read_text())
    result = json.loads((source / "result.json").read_text())
    controls = {x["label"]: x for x in result["ink_controls"]}
    mapper = PanelMap(mapping / "panels.npz")
    samples = []
    for point in audit["points"]:
        uv, valid, panel = mapper.project([point["world_stop"]])
        control = controls[point["label"]]
        images = [
            p
            for p in (source / "ink-targets").glob(
                f"frame-{control['absolute_frame']}-target-*.png"
            )
            if np.asarray(Image.open(p)).any()
        ]
        if len(images) != 1:
            raise ValueError("ambiguous native control target")
        image = np.asarray(Image.open(images[0]).convert("RGB"))
        x, y = np.rint(uv[0]).astype(int).clip(0, 1599)
        rgb = image[y, x].tolist()
        samples.append(
            dict(
                label=point["label"],
                panel=int(panel[0]),
                unique_upward_panel=bool(valid[0]),
                native_pixel_rgb=rgb,
                centroid_error_pixels=float(
                    np.linalg.norm(uv[0] - point["uv_centroid"])
                ),
            )
        )
    control = controls["after-paint-1"]
    g = 0
    for p in (source / "ink-targets").glob(
        f"frame-{control['absolute_frame']}-target-*.png"
    ):
        image = np.asarray(Image.open(p).convert("RGB"))
        g += int(((image[..., 0] == 0) & (image[..., 1] == 255)).sum())
    passed = (
        len(samples) >= 5
        and any(x["label"] == "high-spawn-after" for x in samples)
        and all(
            x["unique_upward_panel"] and x["native_pixel_rgb"] == [255, 0, 0]
            for x in samples
        )
        and g > 0
    )
    report = dict(
        schema="inklab.native.ink-controls.v1",
        passed=passed,
        source=str(source),
        samples=samples,
        role1_pure_g_pixels=g,
        panels_sha256=sha(mapping / "panels.npz"),
        projection_fitted_to_controls=False,
        scope="finite native controls validate transform/vertical layer/V flip and role0-R/role1-G; unique upward panels only, no global surface membership proof",
    )
    write(mapping / "controls-validation.json", report)
    print(json.dumps(report, indent=2))
    if not passed:
        raise ValueError("native ink controls failed")


def attach(recording, mapping):
    source = Path(recording)
    mapping = Path(mapping).resolve()
    r = json.loads((source / "result.json").read_text())
    validation = json.loads((mapping / "controls-validation.json").read_text())
    if not validation.get("passed") or validation["panels_sha256"] != sha(
        mapping / "panels.npz"
    ):
        raise ValueError("native control evidence required before unmasking any ink")
    base = read_jsonl(source / "native-barriers.jsonl")[0]["infos"]["player_0"]["frame"]
    groups = {}
    image_dir = source / "ink-targets"
    if not image_dir.exists():
        image_dir = Path(r["session"]) / "player-0/ink-targets"
    for p in image_dir.glob("frame-*-target-*.png"):
        m = re.fullmatch(r"frame-(\d+)-target-(\w+)\.png", p.name)
        if m:
            groups.setdefault(m[2], []).append((int(m[1]), p))
    active = []
    for tag, files in groups.items():
        if any(
            np.asarray(Image.open(p).convert("RGB"))[..., :2].any() for _, p in files
        ):
            active.append(tag)
    if len(active) != 1:
        raise ValueError("cannot identify a single measured native R/G paint target")
    snapshots = [
        dict(frame=f - base, image=str(p.resolve()), sha256=sha(p))
        for f, p in sorted(groups[active[0]])
    ]
    write(
        source / "native-ink.json",
        dict(
            schema="inklab.native.ink-snapshots.v1",
            observer=0,
            map="Yunohana",
            panels=str((mapping / "panels.npz").resolve()),
            panels_sha256=sha(mapping / "panels.npz"),
            snapshots=snapshots,
            target=active[0],
            scoped_projection_qualified=True,
            qualified_panels=sorted({s["panel"] for s in validation["samples"]}),
            controls_validation_sha256=sha(mapping / "controls-validation.json"),
            mask_contract="Exact snapshot tick only, unique upward panel, R/G exactly (0,0)/(255,0)/(0,255), stage0 paintable floor. All other pixels unknown.",
            controlled_fixture=r.get("ideal_operation_fixture", False),
        ),
    )
    print(source / "native-ink.json", flush=True)


class NativeInk:
    def __init__(self, source, geo):
        self.index = CausalIndex([])
        self.map = None
        self.geo = geo
        self.image_cache = {}
        path = Path(source) / "native-ink.json"
        if not path.exists():
            return
        self.manifest = json.loads(path.read_text())
        if (
            not self.manifest.get("scoped_projection_qualified")
            or self.manifest.get("observer") != 0
        ):
            return
        if sha(self.manifest["panels"]) != self.manifest["panels_sha256"]:
            raise ValueError("native panel mapping changed")
        self.map = PanelMap(self.manifest["panels"])
        self.map.qualified_panels = self.manifest.get("qualified_panels", [])
        self.index = CausalIndex(self.manifest["snapshots"])
        self.cell_uv, self.cell_valid, _ = self.map.project(geo.points.cpu().numpy())
        self.cell_valid &= geo.paintable.cpu().numpy()

    def sample(self, image, uv, valid):
        pixels = np.rint(uv).astype(int).clip(0, 1599)
        rgb = image[pixels[..., 1], pixels[..., 0], :2]
        neutral = (rgb == 0).all(-1)
        a = (rgb[..., 0] == 255) & (rgb[..., 1] == 0)
        b = (rgb[..., 0] == 0) & (rgb[..., 1] == 255)
        good = valid & (neutral | a | b)
        return np.where(good, np.where(a, 0, np.where(b, 1, -1)), -1), good

    def overlay(self, obs, camera, frame):
        device = obs["screen"].device
        screen_valid = torch.zeros((2, 18, 32), dtype=torch.bool, device=device)
        minimap_valid = torch.zeros_like(obs["minimap"][0], dtype=torch.bool)
        row = self.index.latest(frame, 0)
        if self.map is None or row is None:
            return screen_valid, minimap_valid
        if frame not in self.image_cache:
            if sha(row["image"]) != row["sha256"]:
                raise ValueError("native ink image changed")
            self.image_cache = {
                frame: np.asarray(Image.open(row["image"]).convert("RGB"))
            }
        image = self.image_cache[frame]
        colors, valid = self.sample(image, self.cell_uv, self.cell_valid)
        top = self.geo.map_top.cpu().numpy()
        t = top.clip(0, len(colors) - 1)
        mm = np.where(colors[t] == 0, 1, np.where(colors[t] == 1, 2, 0))
        obs["minimap"][0, 0] = torch.as_tensor(mm, device=device, dtype=torch.uint8)
        minimap_valid[0] = torch.as_tensor(valid[t] & (top >= 0), device=device)
        if camera is not None:
            eye, forward, right, up = [x[0, 0].cpu().numpy() for x in camera]
            # Exact same lattice as ParallelEnv._observe; only floor hits qualify.
            xs = np.linspace(-1, 1, 32) * math.tan(math.radians(self.horizontal / 2))
            ys = np.linspace(1, -1, 18) * math.tan(math.radians(self.vertical / 2))
            xx, yy = np.meshgrid(xs, ys)
            direction = forward + xx[..., None] * right + yy[..., None] * up
            direction /= np.linalg.norm(direction, axis=-1, keepdims=True)
            s = obs["screen"][0, 0].cpu().numpy()
            hit = eye + direction * s[..., 0, None]
            uv, ok, _ = self.map.project(hit)
            color, ok = self.sample(image, uv, ok & (s[..., 1] == 1))
            obs["screen"][0, 0, :, :, 2] = torch.as_tensor(
                color, device=device, dtype=torch.float32
            )
            screen_valid[0] = torch.as_tensor(ok, device=device)
        return screen_valid, minimap_valid


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="op", required=True)
    e = sub.add_parser("extract")
    e.add_argument("recording")
    e.add_argument("--out", required=True)
    a = sub.add_parser("attach")
    a.add_argument("recording")
    a.add_argument("--mapping", required=True)
    v = sub.add_parser("validate")
    v.add_argument("recording")
    v.add_argument("--mapping", required=True)
    args = p.parse_args()
    if args.op == "extract":
        extract(args.recording, args.out)
    elif args.op == "validate":
        validate_controls(args.recording, args.mapping)
    else:
        attach(args.recording, args.mapping)
