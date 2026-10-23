"""Real Yunohana same-input S1 comparison, with explicit coarse-terrain errors."""

import argparse, json
from pathlib import Path
import numpy as np
import torch
from .env import ParallelEnv, HP
from .contract import Config, MOVE_DIRECTIONS


def main(a):
    from sim.engine import Simulator, neutral
    from sim.parameters import Parameters
    from sim.motion import MotionModel
    from sim.terrain import Terrain

    torch.set_num_threads(1)
    p = json.loads((Path(a.data) / "parameters.json").read_text())
    terrain = Terrain.load(1)
    conf = json.loads(Path(a.calibration).read_text())["config"]
    config = Config(**conf, decision_frames=1)
    out = dict(
        schema="inklab.rl.stage0.s1-map.v1",
        cases=[],
        scope="Native-derived1u coarse navigation/voxels vs S1 continuous triangle geometry. Same initial poses and movement inputs; no native game or policy run.",
    )
    sources = [
        terrain.spawn[0],
        terrain.points[np.argmin(np.linalg.norm(terrain.points - [0, 3, 0], axis=-1))],
        terrain.points[
            np.argmin(np.linalg.norm(terrain.points - [-18, 3, 0], axis=-1))
        ],
    ]
    for source_id, source in enumerate(sources):
        for move in range(9, 17):
            cpu = Simulator(
                parameters=Parameters(p["saber"]),
                terrain=terrain,
                motion_model=MotionModel(p["motion"]),
            )
            gpu = ParallelEnv(a.data, config)
            cpu.players[0].position = source.copy()
            gpu.state[0, 0, :3] = torch.as_tensor(source, dtype=torch.float32)
            ctrl = neutral()
            ctrl["sticks"][:2] = list(MOVE_DIRECTIONS[move])
            act = torch.zeros((1, 2, 8), dtype=torch.int64)
            act[..., 1:3] = 4
            act[0, 0, 0] = move
            errors = []
            hp = []
            for _ in range(120):
                cpu.step({"player_0": ctrl, "player_1": neutral()}, 1, observe=False)
                gpu.step(act)
                errors.append(
                    float(
                        np.linalg.norm(
                            cpu.players[0].position - gpu.state[0, 0, :3].numpy()
                        )
                    )
                )
                hp.append(abs(cpu.players[0].hp - gpu.state[0, 0, HP].item()) * 100)
            row = dict(
                source=source_id,
                position=source.tolist(),
                move=move,
                frames=120,
                position_rmse_u=float(np.sqrt(np.mean(np.square(errors)))),
                position_max_u=max(errors),
                hp_max_100=max(hp),
            )
            out["cases"].append(row)
            print(json.dumps(row), flush=True)
    out["position_max_u"] = max(r["position_max_u"] for r in out["cases"])
    Path(a.out).write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--calibration", required=True)
    p.add_argument("--out", required=True)
    main(p.parse_args())
