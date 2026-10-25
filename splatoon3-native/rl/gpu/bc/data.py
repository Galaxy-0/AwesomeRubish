"""Whole-match splits, masked public observations and causal recurrent chunks."""

import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from .model import features

HEADS = ("move", "yaw", "pitch", "ZR", "ZL", "B", "R", "RS")
VALIDITY = (
    "hud_valid",
    "screen_channel_valid",
    "minimap_valid",
    "entity_velocity_native_valid",
    "projectiles_native_valid",
    "native_camera_valid",
)
RAW = ("screen", "entities", "entity_mask", "hud", "minimap", "action_mask")


def prepare_shard(z):
    # A dummy second role only satisfies the shared Stage1 encoder's role layout.
    # Select role0 immediately; it supplies no .52 labels or hidden state.
    def pair(v):
        t = torch.as_tensor(v.copy())
        return torch.stack([t, t], 1)

    obs = {k: pair(z[k]) for k in RAW}
    val = {k: pair(z[k]) for k in VALIDITY}
    previous = pair(z["previous_physical_actions"])
    out = {k: v[::2].contiguous() for k, v in features(obs, previous, val).items()}
    # Exporter already stored command (toggle), not physical, masks.
    out["action_mask"] = torch.as_tensor(z["action_mask"].copy())
    return out


def load_match(path):
    path = Path(path)
    report = json.loads((path / "report.json").read_text())
    if (
        report["observation_mode"] != "native_state_sync_only"
        or report["source"] != "human_USB"
    ):
        raise ValueError("human native-state-sync corpus required")
    columns = {}
    counts = {k: np.zeros(17, dtype=np.int64) for k in HEADS}
    physical = {k: np.zeros(17, dtype=np.int64) for k in HEADS}
    masks = {}
    rejected = 0
    files = {}
    for p in sorted(path.glob("bc-*.npz")):
        files[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
        with np.load(p, allow_pickle=False) as z:
            valid = z["state_valid"] & z["action_labels_trainable"]
            # Native action masks can reject human inputs during death/animation;
            # do not train an impossible category or relabel it as idle.
            valid &= np.take_along_axis(
                z["action_mask"], z["actions"][..., None], -1
            ).all((1, 2))
            rejected += int((~valid).sum())
            if not valid.any():
                continue
            d = {k: v[valid] for k, v in z.items()}
            ready = prepare_shard(d)
            ready.update(
                labels=torch.from_numpy(d["actions"]),
                frame=torch.from_numpy(d["frame"]),
            )
            for k, v in ready.items():
                columns.setdefault(k, []).append(v)
            for h, k in enumerate(HEADS):
                counts[k] += np.bincount(d["actions"][:, h], minlength=17)
                physical[k] += np.bincount(d["physical_actions"][:, h], minlength=17)
            for k in VALIDITY + ("weapon_native_valid", "entities_complete"):
                if k in d:
                    old = masks.setdefault(k, [0, 0])
                    old[0] += int(d[k].sum())
                    old[1] += d[k].size
    packed = {k: torch.cat(v) for k, v in columns.items()}
    if not columns:
        raise ValueError("no usable human samples")
    return packed, dict(
        samples=len(packed["frame"]),
        rejected_samples=rejected,
        masked_fraction={k: 1 - a / b for k, (a, b) in masks.items()},
        actions={k: v.tolist() for k, v in counts.items()},
        physical_actions={k: v.tolist() for k, v in physical.items()},
        source_report=report,
        shards_sha256=files,
    )


def sequence_starts(match, length, stride):
    # No chunks spanning missing frames, death packet gaps, or match boundaries.
    frame = match["frame"]
    good = torch.cat(
        [torch.ones(1, dtype=torch.bool), frame[1:] - frame[:-1] == stride]
    )
    bad = (~good).long().cumsum(0)
    return [
        s
        for s in range(0, len(frame) - length + 1, length)
        if bad[s] == bad[s + length - 1]
    ]


def metric(logits, labels):
    result = {}
    for h, name in enumerate(HEADS):
        y = labels[:, h]
        pred = logits[:, h].argmax(-1)
        present = y.unique()
        result[name] = dict(
            accuracy=float((pred == y).float().mean()),
            cross_entropy=float(torch.nn.functional.cross_entropy(logits[:, h], y)),
            macro_recall=float(
                torch.stack(
                    [(pred[y == c] == c).float().mean() for c in present]
                ).mean()
            ),
            nonmajority_accuracy=None,
        )
    return result
