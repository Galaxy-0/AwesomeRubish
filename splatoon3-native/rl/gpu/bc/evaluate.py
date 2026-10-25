"""Stamper-only BC/majority evaluations, normal-spawn 180s GPU approximation."""

import argparse
import json
import time
from pathlib import Path
import torch
from .model import load, features
from ..stage1.common import configuration, load_policy, wilson
from ..env import ParallelEnv
from ..cuda_graph import GraphEnv
from ..stage1.opponents import D4Defender, neutral
from ..stage1.controller import physical
from ..stage1.policy import prepare
from ..stage1.combat_metrics import CombatMeter
from ..stage1.evaluate import d4_positions
from ..record import Recorder
from ..env import EVENT_SIZE


@torch.no_grad()
def play(a):
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("high")
    torch.manual_seed(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    policy, meta = load(a.checkpoint, a.device)
    from dataclasses import replace

    cfg, _ = configuration(a.calibration)
    cfg = replace(cfg, camera_codebook="native_plus5")
    env = ParallelEnv(
        a.data,
        cfg,
        n_envs=a.games,
        device=a.device,
        compile=a.device.startswith("cuda"),
        fast_rays=a.device.startswith("cuda"),
    )
    if a.device.startswith("cuda"):
        env = GraphEnv(env)
    obs, _ = env.reset(seed=a.seed)
    script = None
    if a.kind == "d4-encounter":
        heading, _ = d4_positions(env)
        script = D4Defender(env, heading)
        obs = env._observation(env.state, env.shots, env.paint, env.steps)
    elif a.kind == "d4-spawn":
        script = D4Defender(env)
    other = load_policy(a.opponent, a.device)[0] if a.kind == "history" else None
    hidden = policy.initial(a.games * 2, a.device)
    ohidden = other.initial(a.games * 2, a.device) if other else None
    previous = neutral(a.games, a.device)
    totals = torch.zeros((a.games, 2, EVENT_SIZE), device=a.device)
    meter = CombatMeter(a.games, a.device)
    record = Recorder(env, stride=12)
    random = env.random_actions()
    prior = None
    if a.majority:
        ds = json.loads(Path(a.majority).read_text())
        from .data import HEADS

        prior = torch.tensor(
            [ds["baseline"][k]["majority_class"] for k in HEADS], device=a.device
        )
    start = time.perf_counter()
    step = 0
    while True:
        encoded = features(obs, previous)
        cmd, _, _, hidden = policy.act(encoded, hidden, deterministic=not a.stochastic)
        cmd = cmd.reshape(a.games, 2, 8)
        if prior is not None:
            cmd[:, 0] = prior
        actions = physical(cmd, previous, "toggle")
        if other:
            op = prepare(obs, previous, other.button_semantics)
            oa, _, _, ohidden = other.act(op, ohidden, deterministic=not a.stochastic)
            opponent = physical(
                oa.reshape(a.games, 2, 8), previous, other.button_semantics
            )
        elif script:
            opponent = script.actions()
        else:
            if step % 16 == 0:
                random = env.random_actions()
            opponent = random
        actions[:, 1] = opponent[:, 1]
        obs, _, term, trunc, info = env.step(actions)
        previous = actions.clone()
        totals += info["events"]
        meter.capture(env, actions, info)
        record.capture(actions, info)
        step += 1
        if step % 1800 == 0:
            print(
                json.dumps(
                    dict(
                        event="evaluation-progress",
                        kind=a.kind,
                        frame=int(env.steps.max()),
                    )
                ),
                flush=True,
            )
        if bool((term | trunc).all()):
            break
        if step > env.cfg.duration_frames // env.cfg.decision_frames + 2:
            raise RuntimeError("did not terminate")
    counts = info["turf_counts"]
    wins = int((counts[:, 0] > counts[:, 1]).sum())
    attacks = totals[:, 0, 2].sum().item()
    hit_decisions = (meter.values["hit_decisions"][:, 0]).sum().item()
    result = dict(
        schema="inklab.rl.bc.evaluate.v1",
        kind=a.kind,
        games=a.games,
        seed=a.seed,
        deterministic=not a.stochastic,
        majority=bool(a.majority),
        frames=int(env.steps.max()),
        all_terminated=bool(term.all()),
        wins=wins,
        win_rate=wins / a.games,
        wilson95=wilson(wins, a.games),
        kills=float(totals[:, 1, 5].sum()),
        deaths=float(totals[:, 0, 1].sum()),
        enemy_kills=float(totals[:, 0, 5].sum()),
        damage_dealt=float(totals[:, 1, 0].sum()) * 100,
        own_turf_percent=float((counts[:, 0] / env.paint_count * 100).mean()),
        enemy_turf_percent=float((counts[:, 1] / env.paint_count * 100).mean()),
        attacks=attacks,
        hit_decisions=hit_decisions,
        hit_decisions_per_attack=hit_decisions / max(1, attacks),
        combat=meter.report(),
        seconds=time.perf_counter() - start,
        peak_cuda_mib=torch.cuda.max_memory_allocated() / 2**20,
        checkpoint_epoch=meta["epoch"],
        contract="GPU approximate full180s, Stamper-only; native missing weapon/projectile velocity and ink masked conservatively. D4 is privileged direct-aim fixed script, not human medium .52.",
        per_game=dict(
            turf=counts.cpu().tolist(),
            kills=totals[:, :, 5].flip(1).cpu().tolist(),
            deaths=totals[:, :, 1].cpu().tolist(),
        ),
    )
    clip = record.write(out / "trace.json")
    clip.update(
        label="人类示范 BC · GPU近似 · " + a.kind,
        position_semantics="BC policy in approximate GPU environment; not native evidence",
    )
    (out / "trace.json").write_text(json.dumps(clip, separators=(",", ":")) + "\n")
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--calibration", required=True)
    p.add_argument("--out", required=True)
    p.add_argument(
        "--kind",
        choices=["random", "d4-spawn", "d4-encounter", "history"],
        default="random",
    )
    p.add_argument("--opponent")
    p.add_argument(
        "--majority",
        help="training dataset.json; constant training-majority policy baseline",
    )
    p.add_argument("--games", type=int, default=16)
    p.add_argument("--seed", type=int, default=79001)
    p.add_argument("--device", default="cuda")
    p.add_argument("--stochastic", action="store_true")
    play(p.parse_args())
