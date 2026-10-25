"""Rebuild version2 BC sensor/labels from preserved native recordings + v1 shards."""

import argparse
import json
from pathlib import Path
import numpy as np
import torch
from rl.gpu.env import ParallelEnv
from rl.gpu.contract import Config
from rl.demo.state_sync import NativeRebuilder, read_jsonl
from rl.demo.bc_ink import SnapshotInk
from rl.gpu.bc2.observation import FloorSensor, encode


def attack_events(source):
    # The same pooled object is repeatedly observed during flight. A new run
    # after>4f absence is a birth proxy, not each setter/getter call an attack.
    rows = read_jsonl(Path(source) / "projectiles.jsonl")
    seen = {}
    events = []
    for row in sorted(rows, key=lambda r: r["frame"]):
        if (
            row["player"] != 0
            or row["kind"] != "setter_input"
            or row["vtable"] not in ("5c75510", "5c76df0")
        ):
            continue
        key = (row["object"], row["vtable"])
        f = row["frame"]
        if f - seen.get(key, -100) > 4:
            events.append((f, 2 if row["vtable"] == "5c75510" else 3))
        seen[key] = f
    final = []
    for f, k in sorted(set(events)):
        if not final or k != final[-1][1] or f - final[-1][0] > 3:
            final.append((f, k))
    return [r for r in final if 0 <= r[0] < 10800]


def main(a):
    torch.set_num_threads(1)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    source = Path(a.recording)
    old = Path(a.bc)
    result = json.loads((source / "result.json").read_text())
    if (
        not result["passed"]
        or not result["complete"]
        or result["source"] != "human_USB"
    ):
        raise ValueError("complete human recordings only")
    conf = json.loads(Path(a.calibration).read_text())["config"]
    env = ParallelEnv(
        a.data,
        Config(
            **conf,
            decision_frames=1,
            loadout_mode="primary_only",
            camera_codebook="native_plus5",
        ),
    )
    rows = read_jsonl(source / "native-barriers.jsonl")
    rebuilder = NativeRebuilder(env, source, rows[0]["infos"])
    index = json.loads((source / "native-ink.json").read_text())
    ink = SnapshotInk(a.contract, index["snapshots"])
    sensor = FloorSensor(a.contract)
    exported = {}
    masks = []
    ages = []
    valid_counts = []
    frames = []
    labels = []
    previous = []
    entity = []
    for path in sorted(old.glob("bc-*.npz")):
        with np.load(path) as z:
            for j, f in enumerate(z["frame"]):
                f = int(f)
                q, cam = rebuilder.sync(rows[f])
                if not z["state_valid"][j] or not z["action_labels_trainable"][j]:
                    continue
                raw = {
                    k: torch.as_tensor(np.stack([z[k][j], z[k][j]])[None].copy())
                    for k in (
                        "screen",
                        "entities",
                        "entity_mask",
                        "hud",
                        "minimap",
                        "action_mask",
                    )
                }
                sample = ink.get(f - 1)
                age = 30
                color = np.zeros(sensor.shape, np.uint8)
                valid = np.zeros(sensor.shape, bool)
                if sample is not None:
                    _, color, valid, age = sample
                cm = torch.as_tensor(np.stack([color, color])[None].copy())
                vm = torch.as_tensor(np.stack([valid, valid])[None].copy())
                age_tensor = torch.full((1, 2), age)
                override = cam if z["native_camera_valid"][j] else None
                v = sensor.overlay(
                    raw, env.state, env.cfg, cm, vm, age_tensor, override
                )
                v["hud_valid"] = torch.as_tensor(
                    np.stack([z["hud_valid"][j]] * 2)[None].copy()
                )
                v["native_camera_valid"] = torch.full(
                    (1, 2), bool(z["native_camera_valid"][j])
                )
                prev = torch.as_tensor(
                    np.stack([z["previous_physical_actions"][j]] * 2)[None].copy()
                )
                prepared = encode(raw, v, age_tensor, prev)
                for k, value in prepared.items():
                    exported.setdefault(k, []).append(
                        value[0].numpy().astype(np.float16)
                        if value.is_floating_point()
                        else value[0].numpy()
                    )
                frames.append(f)
                labels.append(z["physical_actions"][j])
                previous.append(z["previous_physical_actions"][j])
                masks.append(valid)
                ages.append(age)
                valid_counts.append(
                    [
                        valid.mean(),
                        float(v["screen_channel_valid"][0, 0, :, :, 2].float().mean()),
                    ]
                )
                entity.append(bool(raw["entity_mask"][0, 0].any()))
        print(json.dumps(dict(shard=path.name, samples=len(frames))), flush=True)
    arrays = {k: np.stack(v) for k, v in exported.items()}
    frame = np.array(frames)
    label = np.array(labels)
    events = attack_events(source)
    eventweight = np.ones((len(frame), 8), np.float32)
    # Intent labels come from observed raw inputs/spawn proxies, never actor inputs.
    aux = (label[:, 3] > 0).astype(np.int64)
    for h in (3, 4, 5):
        edges = np.flatnonzero(label[1:, h] != label[:-1, h]) + 1
        for at in edges:
            eventweight[np.abs(frame - frame[at]) <= 8, h] = 5
    for f, kind in events:
        near = np.abs(frame - f) <= 12
        eventweight[near, :6] = np.maximum(eventweight[near, :6], 3)
        aux[np.abs(frame - f) <= 2] = kind
    arrays.update(
        frame=frame,
        labels=label,
        attack=aux,
        event_weights=eventweight,
        encounter=np.array(entity),
        ink_age=np.array(ages),
    )
    np.savez_compressed(out / "prepared.npz", **arrays)
    bank = np.array(masks)[::15]
    np.savez_compressed(
        out / "masks.npz",
        packed=np.packbits(bank.reshape(len(bank), -1), axis=1),
        cells=np.prod(sensor.shape),
    )
    report = dict(
        schema="inklab.bc2.dataset.v1",
        samples=len(frame),
        source=str(source),
        source_bc=str(old),
        observation="past ink snapshot max29f; geometry-expanded floors, no current-truth promotion",
        ink_map_available_fraction=float(np.mean(valid_counts, axis=0)[0]),
        screen_ink_available_fraction=float(np.mean(valid_counts, axis=0)[1]),
        ink_age_mean=float(np.mean(ages)),
        ink_age_max=int(max(ages)),
        attack_events=events,
        attack_birth_proxy_count=len(events),
        attacks_per_minute=len(events) / 3,
        light=sum(k == 2 for _, k in events),
        full=sum(k == 3 for _, k in events),
        event_semantics="local-world0 pooled-object setter runs separated>4f, same-kind births clustered3f; observed Stamper projectile birth proxy, not complete lifecycle truth",
        ready_for_current_native_truth=False,
    )
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recording", required=True)
    p.add_argument("--bc", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--contract", required=True)
    p.add_argument("--data", default="work/rl-stage0/data-v5")
    p.add_argument(
        "--calibration", default="work/rl-stage0/native-camera-calibration-v1.json"
    )
    main(p.parse_args())
