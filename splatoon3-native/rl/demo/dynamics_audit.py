"""Offline sim-to-native drift ablations; none enter BC observation generation."""

import argparse, json, time
from pathlib import Path
import numpy as np
import torch
from dataclasses import replace
from rl.gpu.contract import Config
from rl.gpu.env import ParallelEnv, YAW, PITCH, HP, INK, ARM
from rl.demo.convert import anchored, quantize, stats
from rl.demo.capture import safe_out, write


def run(a):
    torch.set_num_threads(1)
    source = Path(a.recording)
    out = safe_out(a.out)
    out.mkdir(parents=True, exist_ok=False)
    rows = [json.loads(x) for x in (source / "native-barriers.jsonl").open()]
    inputs = [json.loads(x) for x in (source / "inputs-per-present.jsonl").open()]
    camera = json.load(open(a.camera))
    cfg = Config(
        **(
            json.load(open(a.calibration))["config"]
            | dict(decision_frames=1, loadout_mode="primary_only")
        )
    )
    # Only diagnostic horizon is extended to cover native Ready/Go + judging;
    # no training configuration/physics or native game time is changed.
    cfg = replace(
        cfg,
        duration_frames=len(inputs) + 1,
        camera_codebook=getattr(a, "camera_codebook", None) or cfg.camera_codebook,
        respawn_mode=getattr(a, "respawn_mode", None) or cfg.respawn_mode,
    )
    env = ParallelEnv(a.data, cfg, n_envs=3)
    env.env_ids.zero_()  # Common random numbers across the three ablations.
    env._observation = lambda *args: None
    first = next(
        f
        for f, r in enumerate(rows)
        if all(
            i.get("position_valid")
            and i.get("own_view", {}).get("valid")
            and i.get("alive")
            and i["position"][1] < 20
            and i.get("referee_motion", {}).get("ground_contact") == 0
            for i in r["infos"].values()
        )
    )
    # Initialize all variants once from the same native packet; no later pose/HP corrections.
    single = ParallelEnv(a.data, cfg)
    anchored(single, rows[first], rows[0]["infos"])
    env.state[:] = single.state
    env.steps[:] = first
    names = ["quantized_free", "native_camera_only", "native_camera_and_raw_move"]
    snap = {first: env.state.numpy().copy()}
    seen = [set(), set()]
    errors = {n: [[], []] for n in names}
    terrain = []
    wall = time.monotonic()
    f = first
    with (out / "trajectory.jsonl").open("w") as trace:
        for f in range(first, min(len(inputs), a.max_frames or len(inputs))):
            row = rows[f]
            if any(
                i["phase"] != 1
                or (i.get("time_valid") and i.get("remaining_time", 1) <= 0)
                for i in row["infos"].values()
            ):
                break
            actions = []
            for role in range(2):
                p = f"player_{role}"
                lv, _, _ = quantize(
                    inputs[f]["actions"][p], cfg, camera, [0, 4, 4, 0, 0, 0, 0, 0]
                )
                actions.append(lv)
                v = row["infos"][p].get("own_view", {})
                if v.get("valid"):
                    env.state[1:, role, YAW] = v["yaw"]
                    env.state[1:, role, PITCH] = v["pitch"]
            acts = torch.tensor([actions] * 3, dtype=torch.int64)
            acts[1:, :, 1:3] = 4
            unused = [i for i in range(17) if i not in acts[0, :, 0].tolist()]
            original = env.moves.clone()
            for role, ix in enumerate(unused[:2]):
                env.moves[ix] = torch.tensor(
                    inputs[f]["actions"][f"player_{role}"]["sticks"][:2]
                )
                acts[2, role, 0] = ix
            env.step(acts)
            env.moves[:] = original
            snap[f + 1] = env.state.numpy().copy()
            for role in range(2):
                i = rows[f + 1]["infos"][f"player_{role}"]
                sf = (
                    i.get("position_sample_frame", -1)
                    - rows[0]["infos"][f"player_{role}"]["frame"]
                )
                if sf in snap and sf not in seen[role] and i.get("position_valid"):
                    seen[role].add(sf)
                    truth = np.array(i["position"])
                    floor, cell = env.geo.support(
                        torch.tensor(truth, dtype=torch.float32)[None, None, :]
                    )
                    terrain.append(
                        dict(
                            role=role,
                            frame=sf,
                            cell_valid=bool(cell.item() >= 0),
                            native_height_over_support=float(truth[1] - floor.item()),
                        )
                    )
                    for n, name in enumerate(names):
                        st = snap[sf][n, role]
                        err = dict(
                            frame=sf,
                            position=float(np.linalg.norm(st[:3] - truth)),
                            horizontal=float(
                                np.linalg.norm(st[[0, 2]] - truth[[0, 2]])
                            ),
                            vertical=float(abs(st[1] - truth[1])),
                            hp=float(abs(st[HP] - i.get("hp", 0))),
                            ink=float(abs(st[INK] - i.get("ink", 0))),
                            native_alive=bool(i.get("alive")),
                            sim_alive=bool(st[HP] > 0 and st[ARM] != -2),
                        )
                        errors[name][role].append(err)
                    if sf % 120 < 4:
                        trace.write(
                            json.dumps(
                                dict(
                                    frame=sf,
                                    role=role,
                                    native=truth.tolist(),
                                    variants={
                                        name: snap[sf][n, role, :3].tolist()
                                        for n, name in enumerate(names)
                                    },
                                )
                            )
                            + "\n"
                        )
            snap = {k: v for k, v in snap.items() if k >= f - 120}
            if f % 1200 == 0:
                print(
                    json.dumps(dict(frame=f, seconds=time.monotonic() - wall)),
                    flush=True,
                )
    report = dict(
        schema="inklab.rl.demo.dynamics.v1",
        camera_codebook=cfg.camera_codebook,
        respawn_mode=cfg.respawn_mode,
        exact_triangle_ground="ground_triangles" in env.geo.arrays,
        source=str(source),
        first_ground_frame=first,
        last_frame=f,
        wall_seconds=time.monotonic() - wall,
        variants={},
        terrain=dict(
            valid_fraction=float(np.mean([r["cell_valid"] for r in terrain])),
            native_height_over_coarse_support=stats(
                [r["native_height_over_support"] for r in terrain if r["cell_valid"]]
            ),
        ),
        scope="Positions/HP never corrected after one grounded initialization. Variants1/2 intentionally oracle-condition camera each frame for attribution, not free-policy parity. Raw left-stick ablation uses otherwise-unused movement table slots offline only. Native RNG/paint/spawn/dynamic collision remain approximate.",
    )
    for name in names:
        report["variants"][name] = {
            str(role): {
                key: stats([r[key] for r in values])
                for key in ["position", "horizontal", "vertical", "hp", "ink"]
            }
            | dict(
                alive_mismatches=sum(
                    r["native_alive"] != r["sim_alive"] for r in values
                ),
                horizons={
                    str(h): stats(
                        [r["position"] for r in values if r["frame"] - first <= h]
                    )
                    for h in [60, 300, 1200, 3600, 10800]
                },
            )
            for role, values in enumerate(errors[name])
        }
    write(out / "report.json", report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--recording", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--data", default="work/rl-stage0/data-v5")
    p.add_argument(
        "--calibration", default="work/rl-stage0/native-camera-calibration-v1.json"
    )
    p.add_argument("--camera", required=True)
    p.add_argument(
        "--respawn-mode", choices=["ground", "native_launcher"], default=None
    )
    p.add_argument("--max-frames", type=int)
    p.add_argument(
        "--camera-codebook",
        choices=["legacy", "fine_plus5", "native_plus5"],
        default=None,
    )
    run(p.parse_args())
