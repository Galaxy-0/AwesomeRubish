"""Private fixed-native-state CPU/CUDA observation parity fixture export."""

import argparse
import json
from pathlib import Path
import numpy as np
import torch
from rl.gpu.env import ParallelEnv
from rl.gpu.contract import Config
from rl.gpu.bc2.train import dataset, OBS
from rl.demo.state_sync import NativeRebuilder, read_jsonl
from rl.demo.bc_ink import SnapshotInk


def main(a):
    torch.set_num_threads(1)
    values = {}
    reference = {k: [] for k in OBS}
    poses = []
    cameras = [[], [], [], []]
    colors = []
    masks = []
    ages = []
    conf = json.loads(Path(a.calibration).read_text())["config"]
    env = ParallelEnv(
        a.data,
        Config(
            **conf,
            decision_frames=2,
            loadout_mode="primary_only",
            camera_codebook="native_plus5",
        ),
    )
    for i in (2, 3, 4, 5):
        source = Path(f"work/rl-demo/my-demo-{i:03}")
        rows = read_jsonl(source / "native-barriers.jsonl")
        rebuild = NativeRebuilder(env, source, rows[0]["infos"])
        d = dataset(Path(a.root) / f"data-{i:03}")
        ink = SnapshotInk(
            a.contract,
            json.loads((source / "native-ink.json").read_text())["snapshots"],
        )
        eligible = torch.where(d["quality"][:, 444] > 0)[0]
        for desired in [600, 1800, 3600, 6000, 9000]:
            j = int(eligible[(d["frame"][eligible] - desired).abs().argmin()])
            frame = int(d["frame"][j])
            q, cam = rebuild.sync(rows[frame])
            if cam is None:
                continue
            sample = ink.get(frame - 1)
            if sample is None:
                continue
            _, color, valid, age = sample
            poses.append(env.state[0].numpy().copy())
            for k in range(4):
                cameras[k].append(cam[k][0].numpy())
            colors.append(np.stack([color, color]))
            masks.append(np.stack([valid, valid]))
            ages.append([age, age])
            for k in OBS:
                reference[k].append(d[k][j].numpy())
            values.setdefault("native_time", []).append(
                rows[frame]["infos"]["player_0"]["remaining_time"]
            )
            values.setdefault("frame", []).append(frame)
    arrays = {k: np.array(v) for k, v in values.items()}
    arrays.update(
        state=np.array(poses),
        color=np.array(colors),
        valid=np.array(masks),
        age=np.array(ages),
    )
    arrays.update({f"camera{k}": np.array(v) for k, v in enumerate(cameras)})
    arrays.update({"reference_" + k: np.array(v) for k, v in reference.items()})
    np.savez_compressed(a.out, **arrays)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--contract", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--data", default="work/rl-stage0/data-v5")
    p.add_argument(
        "--calibration", default="work/rl-stage0/native-camera-calibration-v1.json"
    )
    main(p.parse_args())
