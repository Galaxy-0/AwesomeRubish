"""Same native pose/camera/past-ink inputs on GPU; not native pixel validation."""

import argparse
import json
from dataclasses import replace
import numpy as np
import torch
from .observation import FloorSensor, encode
from ..stage1.common import configuration
from ..env import ParallelEnv


def main(a):
    torch.set_num_threads(1)
    z = np.load(a.input)
    n = len(z["frame"])
    cfg, _ = configuration(a.calibration)
    cfg = replace(cfg, camera_codebook="native_plus5")
    e = ParallelEnv(
        a.data, cfg, n_envs=n, device=a.device, fast_rays=a.device.startswith("cuda")
    )
    state = torch.as_tensor(z["state"], device=a.device)
    cam = tuple(torch.as_tensor(z[f"camera{k}"], device=a.device) for k in range(4))
    raw = e._observe(
        state,
        e.shots,
        e.paint,
        torch.as_tensor(z["frame"], device=a.device),
        camera_override=cam,
    )
    raw["hud"][:, 0, 6] = torch.as_tensor(z["native_time"], device=a.device)
    sensor = FloorSensor(a.contract, a.device)
    color = torch.as_tensor(z["color"], device=a.device)
    valid = torch.as_tensor(z["valid"], device=a.device)
    age = torch.as_tensor(z["age"], device=a.device)
    v = sensor.overlay(raw, state, cfg, color, valid, age, cam)
    previous = torch.as_tensor(z["reference_previous_actions"], device=a.device)[
        :, None
    ].repeat(1, 2, 1)
    obs = encode(raw, v, age, previous)
    report = dict(
        samples=n,
        fields={},
        scope="Identical native poses/cameras/past ink: CPU-prepared float16 versus GPU rebuild; does not validate native pixels or free dynamics",
    )
    for k in ["screen", "entities", "entity_mask", "hud", "minimap", "quality"]:
        ref = z["reference_" + k]
        value = obs[k][::2].cpu().numpy()
        delta = np.abs(value.astype(float) - ref.astype(float))
        report["fields"][k] = dict(
            max_abs=float(delta.max()),
            mean_abs=float(delta.mean()),
            not_equal_fraction=float((delta > 1e-4).mean()),
        )
    open(a.out, "w").write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["input", "data", "calibration", "contract", "out"]:
        p.add_argument("--" + name, required=True)
    p.add_argument("--device", default="cuda")
    main(p.parse_args())
