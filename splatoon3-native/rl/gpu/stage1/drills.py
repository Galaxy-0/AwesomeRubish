"""Capability-gated Stamper drills. Synthetic floor is an input-isolation fixture.

Never a formal180s/normal-spawn acceptance result. Opponent weights are frozen;
no observation privileges, forced charge rewards or auto-release actions.
"""

import argparse, json, math, tempfile, time
from pathlib import Path
import torch
from ..env import HP, YAW, PITCH, HEADING
from ..test_env import flat
from .common import configuration, checkpoint, load_policy, CSV, digest
from .policy import Policy, prepare
from .controller import physical
from .opponents import neutral, D4Defender
from .ppo import update
from .combat_metrics import CombatMeter


class Drill:
    def __init__(self, env, kind, seed, fixed_distance=6.0, aim_window="full"):
        self.env, self.kind, self.seed = env, kind, seed
        self.fixed_distance = fixed_distance
        self.aim_window = aim_window
        self.gen = torch.Generator(device=env.device).manual_seed(seed)
        self.trials = torch.zeros(env.n, device=env.device)
        self.wins = self.trials.clone()
        self.defender = D4Defender(
            env, torch.full((env.n,), math.pi, device=env.device)
        )
        self.age = torch.zeros(env.n, dtype=torch.int64, device=env.device)
        self.place(torch.ones(env.n, dtype=torch.bool, device=env.device))

    def place(self, mask):
        e = self.env
        n = int(mask.sum().item())
        if not n:
            return
        # Independent per-trial positions, not hidden opponent coordinates in obs.
        angle = torch.zeros(n, device=e.device)
        distance = torch.full_like(angle, self.fixed_distance)
        if self.kind != "fixed":
            angle = torch.rand(n, generator=self.gen, device=e.device) * 2 * math.pi
            distance = 4 + torch.rand(n, generator=self.gen, device=e.device) * 8
        target = torch.stack(
            [angle.sin() * distance, torch.zeros_like(angle), angle.cos() * distance],
            -1,
        )
        e.state[mask, 0, :3] = torch.tensor([1.0, 0.0, 0.0], device=e.device)
        e.state[mask, 1, :3] = target + torch.tensor([1.0, 0.0, 0.0], device=e.device)
        yaw = angle
        if self.kind != "fixed":
            yaw = (
                angle + (torch.rand(n, generator=self.gen, device=e.device) - 0.5) * 1.2
            )
        e.state[mask, 0, YAW] = yaw
        e.state[mask, 1, YAW] = angle + math.pi
        e.state[mask, :, PITCH] = 0
        e.state[mask, :, HEADING] = e.state[mask, :, YAW]
        self.defender.heading[mask] = angle + math.pi
        self.age[mask] = 0

    def view(self, obs, previous, policy):
        v = prepare(obs, previous, policy.button_semantics)
        v["action_mask"] = v["action_mask"].clone()
        # Mask only in drills; formal evaluation uses every legal primary action.
        allowed = [3] if self.kind == "fixed" else [1, 2, 3]
        if self.kind in ("moving", "weak", "frozen"):
            allowed = [0, 1, 2, 3, 4, 5]
        for h in range(8):
            if h not in allowed:
                v["action_mask"][:, h] = False
                v["action_mask"][:, h, 4 if h in (1, 2) else 0] = True
        if self.kind != "fixed" and self.aim_window == "narrow":
            for h in (1, 2):
                v["action_mask"][:, h, :3] = False
                v["action_mask"][:, h, 6:] = False
        return v

    def opponent(self):
        e = self.env
        a = neutral(e.n, e.device)
        if self.kind == "moving":
            a[:, 1, 0] = torch.where((self.age // 60) % 2 == 0, 3, 7)
        elif self.kind == "weak":
            a = self.defender.actions()
            a[:, 1, 3] *= ((self.age >= 30) & ((self.age % 120) < 18)).long()
        return a

    def ended(self, info, terminal):
        ko = info["events"][:, 1, 5] > 0
        done = terminal[:, 0] | (self.env.state[:, :, HP] <= 0).any(-1)
        self.wins += ko
        self.trials += done
        self.age += self.env.cfg.decision_frames
        return done


def setup(a, n, seed):
    # Private synthetic floor isolates controls from known4.34u map error.
    temp = tempfile.TemporaryDirectory()
    flat(a.data, temp.name)
    # Same measured/user-approved camera as formal environment, only floor differs.
    # Duration is an explicit short skill attempt, never formal180s acceptance.
    from dataclasses import replace

    cfg = replace(configuration(a.calibration)[0], duration_frames=a.trial_frames)
    # Rebuild capture with the chosen duration rather than mutating captured config.
    from ..env import ParallelEnv
    from ..cuda_graph import GraphEnv

    base = ParallelEnv(
        temp.name,
        cfg,
        n_envs=n,
        device=a.device,
        compile=not a.no_compile,
        fast_rays=str(a.device).startswith("cuda"),
    )
    env = GraphEnv(base) if str(a.device).startswith("cuda") else base
    drill = Drill(env, a.kind, seed, a.fixed_distance, a.aim_window)
    return env, drill, temp


@torch.no_grad()
def evaluate(a, policy, seed, out=None, deterministic=False, random_semantics=None):
    # Seed categorical sampling as well as placement; training must not decide
    # the held-out action RNG stream implicitly.
    torch.manual_seed(seed)
    e, drill, temp = setup(a, a.eval_envs, seed)
    prev = neutral(e.n, e.device)
    hidden = policy.initial(e.n * 2, e.device) if policy else None
    obs = e._observation(e.state, e.shots, e.paint, e.steps)
    meter = CombatMeter(e.n, e.device)
    gen = torch.Generator(device=e.device).manual_seed(seed)
    active = torch.ones(e.n, dtype=torch.bool, device=e.device)
    success = torch.zeros_like(active)
    step = 0
    while True:
        if policy:
            v = drill.view(obs, prev, policy)
            c, _, _, hidden = policy.act(v, hidden, deterministic)
            levels = physical(c.reshape(e.n, 2, 8), prev, policy.button_semantics)
        else:
            # Step0 ablation: identical fixture, only ZR/ZL representation varies.
            c = neutral(e.n, e.device)
            c[:, :, 3:5] = torch.randint(
                0,
                3 if random_semantics == "toggle" else 2,
                (e.n, 2, 2),
                generator=gen,
                device=e.device,
            )
            levels = physical(c, prev, random_semantics)
        levels[:, 1] = drill.opponent()[:, 1]
        obs, _, term, trunc, info = e.step(levels)
        prev = levels.clone()
        if policy:
            measured = dict(info)
            measured["events"] = info["events"] * active[:, None, None]
            measured_levels = levels * active[:, None, None]
            meter.capture(e, measured_levels, measured)
            success |= (
                active & (info["events"][:, 1, 5] > 0) & (info["events"][:, 0, 1] == 0)
            )
            active &= ~(info["events"][:, :, 1] > 0).any(-1)
        else:
            meter.capture(e, levels, info)
        drill.age += e.cfg.decision_frames
        step += 1
        if bool((term | trunc).all().item()):
            break
        if step > math.ceil(e.cfg.duration_frames / e.cfg.decision_frames) + 1:
            raise RuntimeError("drill did not terminate")
    # KO may respawn during a full attempt, use events, not just final HP.
    r = dict(
        seed=seed,
        kind=a.kind,
        deterministic=deterministic,
        semantics=policy.button_semantics if policy else random_semantics,
        fixed_distance=a.fixed_distance,
        games=e.n,
        frames=int(e.steps.max().item()),
        combat=meter.report(),
        scope="synthetic-floor capability drill, not formal match; stationary/frozen opponent; no forced attack reward",
        finite=bool(torch.isfinite(e.state).all().item()),
    )
    r["ko_events"] = r["combat"]["stamper"]["weapon_kos"]
    # Ratio of at least one attributed KO per trial needs a per-environment counter.
    r["first_life_only"] = bool(policy)
    r["ko_fraction"] = float(
        (success if policy else meter.values["weapon_kos"][:, 0] > 0)
        .float()
        .mean()
        .item()
    )
    if out:
        Path(out).write_text(json.dumps(r, indent=2) + "\n")
    temp.cleanup()
    return r


def train(a):
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("high")
    torch.manual_seed(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    (out / "checkpoints").mkdir()
    start = time.perf_counter()
    e, drill, temp = setup(a, a.n_envs, a.seed)
    if a.resume:
        policy, meta = load_policy(a.resume, a.device)
        if policy.button_semantics != a.button_semantics:
            raise ValueError("cannot change semantics while resuming")
    else:
        policy = Policy(action_feedback=True, button_semantics=a.button_semantics).to(
            a.device
        )
    parent_frames = meta["frames"] if a.resume else 0
    opt = torch.optim.Adam(
        policy.parameters(), lr=a.lr, eps=1e-5, fused=str(a.device).startswith("cuda")
    )
    if a.resume:
        old = torch.load(a.resume, map_location="cpu", weights_only=False)
        if old.get("optimizer"):
            opt.load_state_dict(old["optimizer"])
            for g in opt.param_groups:
                g["lr"] = a.lr
    cfg = vars(a) | dict(
        parent_frames=parent_frames,
        parent_checkpoint_sha256=digest(a.resume) if a.resume else None,
        action_feedback=True,
        control_prior=False,
        parameters=sum(p.numel() for p in policy.parameters()),
        scope="capability-gated synthetic drill; only Stamper updates; aux constant1; not formal match",
        source_sha256={
            str(p.relative_to(Path(__file__).parents[1])): digest(p)
            for p in Path(__file__).parents[1].rglob("*.py")
        },
    )
    (out / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    # Independent held-out seeds fixed before training, both action selection modes.
    initial = evaluate(a, policy, a.seed + 50000, out / "initial.json")
    # load_policy returns eval mode; cuDNN recurrent backward needs train mode.
    policy.train()
    e.reset(seed=a.seed)
    drill.place(torch.ones(e.n, dtype=torch.bool, device=e.device))
    obs = e._observation(e.state, e.shots, e.paint, e.steps)
    prev = neutral(e.n, e.device)
    h = policy.initial(e.n * 2, a.device)
    before = torch.ones(e.n * 2, dtype=torch.bool, device=e.device)
    meter = CombatMeter(e.n, e.device)
    csv = CSV(out / "metrics.csv")
    frames = 0
    checkpoint(
        out / "checkpoints/u000000.pt",
        policy,
        opt,
        update=0,
        frames=parent_frames,
        config=cfg,
    )
    for iteration in range(1, a.updates + 1):
        store = {
            k: []
            for k in [
                "obs",
                "hidden",
                "done_before",
                "done_after",
                "actions",
                "logprob",
                "logprob_heads",
                "values",
                "rewards",
                "learn",
            ]
        }
        with torch.no_grad():
            for step in range(a.rollout):
                v = drill.view(obs, prev, policy)
                store["obs"].append({k: x.detach().clone() for k, x in v.items()})
                store["hidden"].append(h.clone())
                store["done_before"].append(before.clone())
                c, lp, value, nh, lh = policy.act(v, h, return_heads=True)
                levels = physical(c.reshape(e.n, 2, 8), prev, policy.button_semantics)
                levels[:, 1] = drill.opponent()[:, 1]
                obs, reward, term, trunc, info = e.step(levels)
                done = drill.ended(info, term | trunc)
                meter.capture(e, levels, info, done)
                prev = levels.clone()
                after = done[:, None].expand(-1, 2).reshape(-1)
                learn = torch.zeros((e.n, 2), dtype=torch.bool, device=e.device)
                learn[:, 0] = True
                for k, x in [
                    ("actions", c),
                    ("logprob", lp),
                    ("logprob_heads", lh),
                    ("values", value),
                    ("rewards", reward.reshape(-1)),
                    ("done_after", after),
                    ("learn", learn.reshape(-1)),
                ]:
                    store[k].append(x.clone())
                h = nh * (~after)[None, :, None]
                before = after
                frames += e.n * e.cfg.decision_frames
                if done.any().item():
                    e.reset(
                        seed=a.seed + iteration * a.rollout + step,
                        options={"mask": done},
                    )
                    drill.place(done)
                    prev[done] = neutral(e.n, e.device)[done]
                    obs = e._observation(e.state, e.shots, e.paint, e.steps)
        batch = {k: torch.stack(v) for k, v in store.items() if k != "obs"}
        batch["obs"] = {
            k: torch.stack([v[k] for v in store["obs"]]) for k in store["obs"][0]
        }
        with torch.no_grad():
            latest = drill.view(obs, prev, policy)
            bootstrap = policy({k: v[None] for k, v in latest.items()}, h)[1][0]
        stats = update(
            policy,
            opt,
            batch,
            bootstrap,
            sequence_length=32,
            minibatch_sequences=64,
            epochs=a.epochs,
            lam=0.99,
            entropy_coef=0.0015,
            target_kl=a.target_kl,
            advantage_floor=a.advantage_floor,
        )
        row = dict(
            update=iteration,
            environment_frames=frames,
            wall_seconds=time.perf_counter() - start,
            aux_scale=1.0,
            **stats,
            **{"stamper_" + k: v for k, v in meter.report()["stamper"].items()},
        )
        csv.write(row)
        if not stats["finite"]:
            raise FloatingPointError("nonfinite")
        if iteration % 10 == 0:
            print(json.dumps(row), flush=True)
        if (out / "STOP").exists():
            break
    path = out / f"checkpoints/u{iteration:06}.pt"
    checkpoint(
        path, policy, opt, update=iteration, frames=parent_frames + frames, config=cfg
    )
    csv.close()
    duration = time.perf_counter() - start
    sampled = evaluate(a, policy, a.seed + 50000, out / "sampled.json")
    greedy = evaluate(
        a, policy, a.seed + 50000, out / "greedy.json", deterministic=True
    )
    # Fixed threshold declared independently of score/paint; no frame-based promotion.
    gate = (
        sampled["ko_fraction"] >= 0.9
        and sampled["combat"]["stamper"]["full_releases_per_minute"] >= 1
    )
    summary = dict(
        stage1_passed=False,
        kind=a.kind,
        seed=a.seed,
        frames=frames,
        cumulative_frames=parent_frames + frames,
        updates=iteration,
        training_seconds=duration,
        peak_allocated_mib=torch.cuda.max_memory_allocated() / 2**20
        if str(a.device).startswith("cuda")
        else 0,
        initial=initial,
        sampled=sampled,
        greedy=greedy,
        capability_gate=gate,
        checkpoint=str(path),
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)
    temp.cleanup()


def main(a):
    if a.mode == "train":
        return train(a)
    torch.set_num_threads(1)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    if a.mode == "evaluate":
        policy, _ = load_policy(a.resume, a.device)
        reports = {
            name: evaluate(
                a, policy, a.seed + 50000, out / (name + ".json"), deterministic=det
            )
            for name, det in [("sampled", False), ("greedy", True)]
        }
        (out / "summary.json").write_text(json.dumps(reports, indent=2) + "\n")
        return
    for seed in a.seeds:
        for semantics in ("level", "toggle"):
            torch.manual_seed(seed)
            r = evaluate(
                a,
                None,
                seed,
                out / f"{semantics}-{seed}.json",
                random_semantics=semantics,
            )
            print(json.dumps(r), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--calibration", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--mode", choices=["ablation", "train", "evaluate"], default="train")
    p.add_argument(
        "--kind", choices=["fixed", "random_pose", "moving", "weak"], default="fixed"
    )
    p.add_argument("--button-semantics", choices=["level", "toggle"], default="toggle")
    p.add_argument("--seed", type=int, default=101)
    p.add_argument("--fixed-distance", type=float, default=6.0)
    p.add_argument("--aim-window", choices=["narrow", "full"], default="full")
    p.add_argument("--seeds", type=int, nargs="+", default=[101, 202, 303])
    p.add_argument("--trial-frames", type=int, default=360)
    p.add_argument("--eval-envs", type=int, default=64)
    p.add_argument("--n-envs", type=int, default=128)
    p.add_argument("--updates", type=int, default=128)
    p.add_argument("--rollout", type=int, default=128)
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--advantage-floor", type=float, default=0.02)
    p.add_argument("--target-kl", type=float, default=0.04)
    p.add_argument("--device", default="cuda")
    p.add_argument("--no-compile", action="store_true")
    p.add_argument("--resume")
    main(p.parse_args())
