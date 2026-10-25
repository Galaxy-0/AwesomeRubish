"""Versioned BC sensor: past native ink snapshot, NOT current paint truth.

Keeps the old exact-frame NativeInk contract unchanged. Geometry expansion uses
the same measured native transform on unique upward, paintable floor cells;
it is explicitly inference, not new native per-panel firing qualification.
"""

import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
from rl.demo.native_ink import PanelMap
from rl.demo.build_host import sha


def build_contract(data, recording, out):
    data, recording, out = Path(data), Path(recording), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    ink = json.loads((recording / "native-ink.json").read_text())
    if (
        not ink["scoped_projection_qualified"]
        or sha(ink["panels"]) != ink["panels_sha256"]
    ):
        raise ValueError("immutable, per-recording native panel calibration required")
    with np.load(data / "map.npz") as z:
        points, paintable, ids = z["points"], z["paintable"], z["cell_ids"]
        grid_origin = z["grid_origin"]
    mapper = PanelMap(ink["panels"])
    uv, valid, panel = mapper.project(points)
    valid &= paintable
    # Fail on nonfinite/singular native mappings; unique bounds alone are not enough.
    jacobian = np.linalg.det(mapper.uv[:, :, :2])
    valid &= np.isfinite(jacobian[panel.clip(0)]) & (
        abs(jacobian[panel.clip(0)]) > 1e-8
    )
    # Reject atlas aliases between distant world floors (including stacked floors).
    pixel = np.rint(uv).astype(int).clip(0, 1599)
    tags = pixel[:, 0] + pixel[:, 1] * 1600
    aliases = 0
    for tag in np.unique(tags[valid]):
        hit = np.flatnonzero(valid & (tags == tag))
        if len(hit) > 1 and np.ptp(points[hit], axis=0).max() > 1.5:
            valid[hit] = False
            aliases += len(hit)
    top = np.take_along_axis(ids, np.maximum((ids >= 0).sum(-1) - 1, 0)[..., None], -1)[
        ..., 0
    ]
    cell = top.clip(0, len(points) - 1)
    map_valid = valid[cell] & (top >= 0)
    paintable_map = paintable[cell] & (top >= 0)
    np.savez_compressed(
        out / "contract.npz",
        points=points,
        uv=uv,
        cell_valid=valid,
        panel=panel,
        top=top,
        map_valid=map_valid,
        paintable_map=paintable_map,
        low=mapper.low,
        high=mapper.high,
        basis=mapper.basis,
        panel_uv=mapper.uv,
        grid_origin=grid_origin,
    )
    report = dict(
        schema="inklab.bc.ink-contract.v2",
        snapshot_period_frames=30,
        max_age_frames=29,
        observation_is_last_snapshot=True,
        current_native_truth=False,
        original_control_panels=ink["qualified_panels"],
        expansion="unique upward native bounds + nonsingular native UV + paintable collision cells + no distant UV alias; common-transform geometric inference, not per-panel native firing validation",
        cells=int(valid.sum()),
        paintable_cells=int(paintable.sum()),
        map_valid_fraction=float(map_valid.mean()),
        map_valid_among_paintable=float(map_valid.sum() / max(1, paintable_map.sum())),
        atlas_alias_cells_rejected=aliases,
        panels=sorted(set(panel[valid].tolist())),
        panels_sha256=ink["panels_sha256"],
        source_recording=str(recording),
        original_index_sha256=sha(recording / "native-ink.json"),
        map_sha256=sha(data / "map.npz"),
        contract_sha256=sha(out / "contract.npz"),
    )
    (out / "contract.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


class SnapshotInk:
    def __init__(self, contract, index):
        from rl.demo.state_sync import CausalIndex

        with np.load(contract) as z:
            self.a = {k: z[k].copy() for k in z.files}
        self.mapper = PanelMap.__new__(PanelMap)
        self.mapper.low, self.mapper.high = self.a["low"], self.a["high"]
        self.mapper.basis, self.mapper.uv = self.a["basis"], self.a["panel_uv"]
        self.mapper.qualified_panels = None
        self.index = CausalIndex(index)
        self.last = None
        self.decoded = None

    @staticmethod
    def decode(image, uv, valid):
        xy = np.rint(uv).astype(int).clip(0, 1599)
        rg = image[xy[..., 1], xy[..., 0], :2]
        neutral = (rg == 0).all(-1)
        alpha = (rg[..., 0] == 255) & (rg[..., 1] == 0)
        bravo = (rg[..., 0] == 0) & (rg[..., 1] == 255)
        good = valid & (neutral | alpha | bravo)
        return np.where(alpha, 1, np.where(bravo, 2, 0)).astype(np.uint8), good

    def get(self, frame):
        row = self.index.latest(frame, 29)
        if row is None:
            return None
        if row["frame"] != self.last:
            if row.get("sha256") and sha(row["image"]) != row["sha256"]:
                raise ValueError("native snapshot changed")
            image = np.asarray(Image.open(row["image"]).convert("RGB"))
            colors, good = self.decode(image, self.a["uv"], self.a["cell_valid"])
            top = self.a["top"].clip(0, len(colors) - 1)
            self.decoded = (image, colors[top], good[top] & self.a["map_valid"])
            self.last = row["frame"]
        return (*self.decoded, frame - row["frame"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", default="work/rl-stage0/data-v5")
    p.add_argument("--recording", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    print(json.dumps(build_contract(a.data, a.recording, a.out), indent=2))
