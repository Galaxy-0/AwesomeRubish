"""Replay the LOCAL S1 same-input numeric references on CUDA, no S1 host needed."""

import argparse, tempfile, json
from pathlib import Path
import numpy as np
import torch
from .test_env import flat, fixture_config
from .env import ParallelEnv, HP, INK


def main(a):
    torch.set_num_threads(1)
    with np.load(a.reference, allow_pickle=False) as raw:
        r = {k: raw[k] for k in raw.files}
    names = r["cases"].tolist()
    n = len(names)
    with tempfile.TemporaryDirectory() as temp:
        flat(a.data, temp)
        e = ParallelEnv(
            temp, fixture_config(decision_frames=1), n_envs=n, device="cuda"
        )
        e.state.copy_(
            torch.as_tensor(
                np.concatenate([r[f"{i}_initial_state"] for i in range(n)]),
                device="cuda",
            )
        )
        e.paint.copy_(
            torch.as_tensor(
                np.concatenate([r[f"{i}_initial_paint"] for i in range(n)]),
                device="cuda",
            )
        )
        actions = np.concatenate([r[f"{i}_actions"] for i in range(n)], axis=1)
        actions = torch.as_tensor(actions, device="cuda", dtype=torch.int64)
        states = []
        ratios = []
        for frame in range(len(actions)):
            e.step(actions[frame])
            states.append(e.state.clone())
            ratios.append(
                torch.stack(
                    [(e.paint[:, :-1] == i).sum(-1) / e.paint_count for i in range(2)],
                    -1,
                )
            )
        states = torch.stack(states).cpu().numpy()
        ratios = torch.stack(ratios).cpu().numpy()
    out = dict(
        schema="inklab.rl.stage0.cuda-s1.v1",
        device=torch.cuda.get_device_name(),
        torch=torch.__version__,
        cases=[],
        scope="Identical stored S1 inputs and initial states, synthetic floor with identical scoring domain. Complete partial observations computed every decision. No native-fidelity claim.",
    )
    for i, name in enumerate(names):
        cpu = r[f"{i}_cpu"]
        delta = states[:, i, :, :3] - cpu[:, :2, :3]
        distance = np.linalg.norm(delta, axis=-1)
        out["cases"].append(
            dict(
                case=name,
                frames=len(actions),
                position_rmse_u=float(np.sqrt(np.mean(distance**2))),
                position_max_u=float(distance.max()),
                hp_max_100=float(
                    np.max(np.abs(states[:, i, :, HP] - cpu[:, :2, 3])) * 100
                ),
                ink_max_100=float(
                    np.max(np.abs(states[:, i, :, INK] - cpu[:, :2, 4])) * 100
                ),
                turf_max_percentage_points=float(
                    np.max(np.abs(ratios[:, i] - cpu[:, 2, :2])) * 100
                ),
            )
        )
    Path(a.out).write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--out", required=True)
    main(p.parse_args())
