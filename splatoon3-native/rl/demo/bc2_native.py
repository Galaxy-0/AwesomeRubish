"""BC2 one-room native fixture. Ordinary input, causal read-only sensor only."""

import json
from pathlib import Path
import numpy as np
from PIL import Image
import torch
from .bc_native import NativeBC, native_action
from .bc_ink import SnapshotInk
from .native_ink import extract
from rl.gpu.bc2.model import load, Ensemble
from rl.gpu.bc2.observation import FloorSensor, encode


class NativeBC2(NativeBC):
    def __init__(
        self,
        checkpoint,
        out,
        session,
        origins,
        data,
        calibration,
        camera,
        *,
        contract,
        stochastic=False,
        camera_decode="argmax",
    ):
        super().__init__(
            checkpoint,
            out,
            session,
            origins,
            data,
            calibration,
            camera,
            model_loader=load,
        )
        self.actor = Ensemble(self.policy, 2, "cpu", camera_decode)
        self.sensor = FloorSensor(contract)
        self.reader = SnapshotInk(contract, [])
        self.root = Path(session) / "player-0/ink-targets"
        self.tag = None
        self.last_poll = -100
        self.cached = None
        self.sample_frame = -100
        self.stochastic = stochastic
        # Match THIS scene's arrays to the contract before ever unmasking ink.
        measured = Path(out) / "live-ink-panel-map"
        extract(out, measured)
        with np.load(measured / "panels.npz") as z:
            for field, key in [
                ("low", "low"),
                ("high", "high"),
                ("basis", "basis"),
                ("uv", "panel_uv"),
            ]:
                if not np.array_equal(z[field], self.reader.a[key]):
                    raise ValueError(
                        "current native panel table differs from BC2 contract"
                    )

    def snapshot(self, cutoff):
        absolute_base = self.origins["player_0"]["frame"]
        tick = cutoff // 30 * 30
        if tick >= 0 and tick != self.last_poll:
            candidates = list(
                self.root.glob(f"frame-{absolute_base + tick}-target-*.png")
            )
            if self.tag is None:
                active = []
                loaded = []
                for p in candidates:
                    try:
                        image = np.asarray(Image.open(p).convert("RGB"))
                    except OSError:
                        continue  # async PNG write not complete yet
                    loaded.append(image)
                    if image[..., :2].any():
                        active.append((p, image))
                if len(active) == 1:
                    self.tag = active[0][0].stem.split("target-")[1]
                elif len(loaded) == 2:
                    # Before either target is painted, both agree on neutral.
                    # Use only per-cell consensus; no future target selection.
                    decoded = [
                        self.reader.decode(
                            im, self.reader.a["uv"], self.reader.a["cell_valid"]
                        )
                        for im in loaded
                    ]
                    colors = decoded[0][0]
                    valid = decoded[0][1] & decoded[1][1] & (colors == decoded[1][0])
                    top = self.reader.a["top"].clip(0, len(colors) - 1)
                    self.cached = (colors[top], valid[top] & self.reader.a["map_valid"])
                    self.sample_frame = tick
                    self.last_poll = tick
            picked = [
                p for p in candidates if p.stem.endswith("target-" + str(self.tag))
            ]
            if picked:
                try:
                    image = np.asarray(Image.open(picked[0]).convert("RGB"))
                except OSError:
                    return (
                        np.zeros(self.sensor.shape, np.uint8),
                        np.zeros(self.sensor.shape, bool),
                        30,
                    )
                colors, valid = self.reader.decode(
                    image, self.reader.a["uv"], self.reader.a["cell_valid"]
                )
                top = self.reader.a["top"].clip(0, len(colors) - 1)
                self.cached = (colors[top], valid[top] & self.reader.a["map_valid"])
                self.sample_frame = tick
                self.last_poll = tick
        if self.cached is None or not 0 <= cutoff - self.sample_frame <= 29:
            return (
                np.zeros(self.sensor.shape, np.uint8),
                np.zeros(self.sensor.shape, bool),
                30,
            )
        return (*self.cached, cutoff - self.sample_frame)

    @torch.no_grad()
    def act(self, frame, infos):
        self.read_cameras()
        q, cam = self.rebuilder.sync(dict(frame=frame, infos=infos))
        raw = self.env._observe(
            self.env.state,
            self.env.shots,
            self.env.paint,
            self.env.steps,
            camera_override=cam,
        )
        for n in range(2):
            info = infos[f"player_{n}"]
            if info.get("time_valid"):
                raw["hud"][0, n, 6] = info["remaining_time"]
        color, valid, age = self.snapshot(frame - 1)
        cm = torch.as_tensor(
            np.stack([color, np.where(color == 1, 2, np.where(color == 2, 1, 0))])[
                None
            ].copy()
        )
        vm = torch.as_tensor(np.stack([valid, valid])[None].copy())
        ages = torch.full((1, 2), age)
        v = self.sensor.overlay(raw, self.env.state, self.cfg, cm, vm, ages, cam)
        v["native_camera_valid"] = torch.tensor([q["camera_native_valid"]])
        observation = encode(raw, v, ages, self.previous)
        levels = self.actor.act(observation, not self.stochastic).reshape(1, 2, 8)
        self.previous = levels.clone()
        action = levels[0, 0].tolist()
        self.history.write(
            json.dumps(
                dict(
                    frame=frame,
                    actions=action,
                    ink_age=age,
                    ink_map_available=float(valid.mean()),
                    state_valid=q["state_valid"],
                    camera_native_valid=q["camera_native_valid"],
                )
            )
            + "\n"
        )
        return native_action(action, self.cfg, self.camera_model)
