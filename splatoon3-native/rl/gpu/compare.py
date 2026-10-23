"""Same-input S1 conformance report; isolates shared mechanics, not native fidelity."""

import argparse, json, tempfile
from pathlib import Path
import numpy as np
import torch
from .test_env import flat, fixture_config
from .env import HEADING, HP, HURT, INK, MOVE_DIRECTIONS, ParallelEnv, YAW


def main(args):
    from sim.test_core import fixture
    from sim.engine import Simulator, neutral
    from sim.parameters import Parameters
    from sim.motion import MotionModel

    torch.set_num_threads(1)
    references = []
    result = dict(
        schema="inklab.rl.stage0.s1-comparison.v1",
        cases=[],
        scope="Shared S1 mechanics only. S1 has no .52 or complete hooks. Synthetic calibration; not native fidelity.",
    )
    with tempfile.TemporaryDirectory() as tmp:
        flat(args.data, tmp)
        for case in [
            "walk-full",
            "walk-half",
            "diagonal",
            "jump",
            "own-swim",
            "light",
            "full",
            "recover",
        ]:
            gpu = ParallelEnv(tmp, fixture_config(decision_frames=1))
            cfg = json.loads((Path(args.data) / "parameters.json").read_text())
            cpu = Simulator(
                parameters=Parameters(cfg["saber"]),
                terrain=fixture(),
                motion_model=MotionModel(cfg["motion"]),
            )
            for p in cpu.players:
                p.yaw = 0.0
                p.heading = 0.0
            gpu.state[..., YAW] = 0.0
            gpu.state[..., HEADING] = 0.0
            if case in ["own-swim", "recover"]:
                cpu.paint.owners[:] = 0
                gpu.paint[:] = 0
            if case == "recover":
                cpu.players[0].hp = 0.2
                cpu.players[0].ink = 0
                cpu.players[0].hurt_at = 0
                gpu.state[0, 0, HP] = 0.2
                gpu.state[0, 0, INK] = 0
                gpu.state[0, 0, HURT] = 0
            reference = dict(
                case=case,
                initial_state=gpu.state.numpy().copy(),
                initial_paint=gpu.paint.numpy().copy(),
                actions=[],
                cpu=[],
            )
            errors = []
            hp = []
            ink = []
            paint = []
            damage = []
            gpu_damage = 0.0
            for frame in range(120):
                a = torch.zeros((1, 2, 8), dtype=torch.int64)
                a[..., 1:3] = 4
                control = neutral()
                if case in ["walk-full", "walk-half", "diagonal", "jump", "own-swim"]:
                    index = {
                        "walk-full": 9,
                        "walk-half": 1,
                        "diagonal": 10,
                        "jump": 9,
                        "own-swim": 9,
                    }[case]
                    a[0, 0, 0] = index
                    control["sticks"][:2] = list(MOVE_DIRECTIONS[index])
                if case == "jump" and frame == 0:
                    a[0, 0, 5] = 1
                    control["buttons"][4] = 1
                if case in ["own-swim", "recover"]:
                    a[0, 0, 4] = 1
                    control["buttons"][1] = 1
                if case in ["light", "full"] and frame < (1 if case == "light" else 21):
                    a[0, 0, 3] = 1
                    control["buttons"][0] = 1
                _, _, _, _, gi = gpu.step(a)
                gpu_damage += gi["events"][0, 1, 0].item()
                cpu.step({"player_0": control, "player_1": neutral()}, 1, observe=False)
                reference["actions"].append(a.numpy().copy())
                reference["cpu"].append(
                    [[*p.position, p.hp, p.ink] for p in cpu.players]
                    + [cpu.paint.ratios() + [0.0, 0.0, 0.0]]
                )
                errors.append(
                    float(
                        np.linalg.norm(
                            gpu.state[0, 0, :3].numpy() - cpu.players[0].position
                        )
                    )
                )
                hp.append(
                    max(
                        abs(gpu.state[0, i, HP].item() - cpu.players[i].hp)
                        for i in (0, 1)
                    )
                )
                ink.append(abs(gpu.state[0, 0, INK].item() - cpu.players[0].ink))
                ratios = [
                    float(
                        ((gpu.paint[0, :-1] == i) & gpu.geo.paintable).sum().item()
                        / gpu.paint_count
                    )
                    for i in (0, 1)
                ]
                paint.append(
                    float(np.max(np.abs(np.array(ratios) - cpu.paint.ratios())))
                )
                damage.append(
                    [
                        float(
                            sum(
                                v["amount"]
                                for v in cpu.events
                                if v["kind"] == "damage"
                                and v.get("cause") in ["ink_blade", "contact"]
                            )
                        ),
                        float(gpu_damage),
                    ]
                )
            references.append(reference)
            result["cases"].append(
                dict(
                    case=case,
                    frames=120,
                    trajectory_rmse_u=float(np.sqrt(np.mean(np.square(errors)))),
                    trajectory_max_u=max(errors),
                    hp_max_100=max(hp) * 100,
                    ink_max_100=max(ink) * 100,
                    turf_max_percentage_points=max(paint) * 100,
                    final_damage_cpu_gpu_100=np.array(damage[-1]).tolist(),
                )
            )
    if args.references:
        values = {}
        for i, r in enumerate(references):
            for key in ["initial_state", "initial_paint", "actions", "cpu"]:
                values[f"{i}_{key}"] = np.asarray(r[key])
        values["cases"] = np.array([r["case"] for r in references])
        np.savez_compressed(args.references, **values)
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--data", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--references")
    main(a.parse_args())
