"""Full180s BC2 closed-loop ablations; no privileged observations for the actor."""

import argparse
import json
import time
from pathlib import Path
from dataclasses import replace
import torch
import numpy as np
from .model import load, Ensemble
from .observation import GPUInk, encode
from .distribution import Collector
from ..stage1.common import configuration, load_policy
from ..stage1.opponents import neutral, D4Defender
from ..stage1.policy import prepare
from ..stage1.controller import physical
from ..stage1.combat_metrics import CombatMeter
from ..env import ParallelEnv, EVENT_SIZE
from ..cuda_graph import GraphEnv
from ..record import Recorder


@torch.no_grad()
def play(a):
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("high")
    torch.manual_seed(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    model, meta = load(a.checkpoint, a.device)
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
    raw, _ = env.reset(seed=a.seed)
    sensor = GPUInk(a.contract, env, a.mask_bank)
    actor = Ensemble(model, a.games * 2, a.device, a.camera_decode)
    opponent = load_policy(a.opponent, a.device)[0] if a.kind == "history" else None
    other_hidden = opponent.initial(a.games * 2, a.device) if opponent else None
    script = D4Defender(env) if a.kind == "script" else None
    previous = neutral(a.games, a.device)
    random = env.random_actions()
    totals = torch.zeros(a.games, 2, EVENT_SIZE, device=a.device)
    meter = CombatMeter(a.games, a.device)
    recorder = Recorder(env, stride=12)
    collector = Collector()
    wall = time.perf_counter()
    step = 0
    while True:
        ordinary = raw
        raw, v, age = sensor.observe({k: x.clone() for k, x in raw.items()})
        observation = encode(raw, v, age, previous)
        # 31 decisions = 62f is coprime to the 15 decision ink-snapshot cycle.
        # A 60f probe would always observe age29 and misreport an age shift.
        if step % 31 == 0:
            collector.capture({k: x[::2] for k, x in observation.items()})
        actions = actor.act(observation, not a.stochastic).reshape(a.games, 2, 8)
        if opponent:
            # Historical controller sees its ordinary public obs, not BC2 masks.
            other, _, _, other_hidden = opponent.act(
                prepare(ordinary, previous, opponent.button_semantics),
                other_hidden,
                not a.stochastic,
            )
            other = physical(
                other.reshape(a.games, 2, 8), previous, opponent.button_semantics
            )
        elif script:
            other = script.actions()
        else:
            if step % 16 == 0:
                random = env.random_actions()
            other = random
        actions[:, 1] = other[:, 1]
        raw, _, term, trunc, info = env.step(actions)
        previous = actions.clone()
        totals += info["events"]
        meter.capture(env, actions, info)
        recorder.capture(actions, info)
        step += 1
        if step % 1800 == 0:
            print(json.dumps(dict(frame=int(env.steps.max()), kind=a.kind)), flush=True)
        if bool((term | trunc).all()):
            break
        if step > 5402:
            raise RuntimeError("full180s did not terminate")
    counts = info["turf_counts"]
    attacks = float(totals[:, 0, 2].sum())
    hits = float(meter.values["hit_decisions"][:, 0].sum())
    report = dict(
        schema="inklab.bc2.evaluate.v1",
        games=a.games,
        kind=a.kind,
        deterministic=not a.stochastic,
        camera_decode=a.camera_decode,
        seed=a.seed,
        frames=int(env.steps.max()),
        all_terminated=bool(term.all()),
        kills=float(totals[:, 1, 5].sum()),
        deaths=float(totals[:, 0, 1].sum()),
        enemy_weapon_kills=float(totals[:, 0, 5].sum()),
        damage=float(totals[:, 1, 0].sum()) * 100,
        attacks=attacks,
        attacks_per_minute=attacks / (a.games * 3),
        hit_decisions=hits,
        hit_decisions_per_attack=hits / max(1, attacks),
        turf_percent=float((counts[:, 0] / env.paint_count * 100).mean()),
        enemy_turf_percent=float((counts[:, 1] / env.paint_count * 100).mean()),
        wins=int((counts[:, 0] > counts[:, 1]).sum()),
        combat=meter.report(),
        seconds=time.perf_counter() - wall,
        peak_cuda_mib=torch.cuda.max_memory_allocated() / 2**20,
        checkpoint_epoch=meta["epoch"],
        horizon=model.horizon,
        feedback=model.action_feedback,
        contract="GPU approximate normal-spawn180s, causal30f ink sampling; native-trained missingness bank, same floor eligibility. No enemy xyz enters actor. Script is existing privileged fixed D4 reference, not native medium.",
        per_game=dict(
            kills=totals[:, 1, 5].cpu().tolist(),
            deaths=totals[:, 0, 1].cpu().tolist(),
            turf=(counts[:, 0] / env.paint_count * 100).cpu().tolist(),
        ),
    )
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    np.savez_compressed(out / "distributions.npz", **collector.arrays())
    clip = recorder.write(out / "trace.json")
    clip.update(
        label="BC第二轮 · GPU · " + a.kind,
        position_semantics="BC2 in approximate GPU simulation; not native evidence",
    )
    (out / "trace.json").write_text(json.dumps(clip, separators=(",", ":")) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("checkpoint", "data", "calibration", "contract", "mask-bank", "out"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--kind", choices=["random", "script", "history"], default="random")
    p.add_argument("--opponent")
    p.add_argument("--games", type=int, default=16)
    p.add_argument("--seed", type=int, default=80001)
    p.add_argument("--stochastic", action="store_true")
    p.add_argument(
        "--camera-decode", choices=["argmax", "expectation"], default="argmax"
    )
    p.add_argument("--device", default="cuda")
    play(p.parse_args())
