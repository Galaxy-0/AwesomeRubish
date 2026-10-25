"""24h bounded BC->PPO; six-hour zero-formal-damage stop, hourly evaluation."""

import argparse
import copy
import json
import os
import time
from pathlib import Path
import torch
from .model import initialize, distributions
from .rollout import Match
from .ppo import update
from .rewards import schedule
from .assess import evaluate
from ..stage1.common import CSV, digest
from ..stage1.combat_metrics import CombatMeter
from ..env import EVENT_SIZE, PITCH


def atomic_json(path, row):
    path = Path(path)
    tmp = path.with_suffix(".partial")
    tmp.write_text(json.dumps(row, indent=2) + "\n")
    os.replace(tmp, path)


def export(path, model, optimizer, **meta):
    # BC2-compatible actor export for the existing one-room native fixture.
    # Separate resume checkpoint includes optimizer/RNG, not a distributed asset.
    path = Path(path)
    tmp = path.with_suffix(".partial")
    torch.save(
        dict(
            schema="inklab.bc2.checkpoint.v1",
            policy=model.state_dict(),
            hidden=model.hidden_size,
            horizon=1,
            feedback=False,
            epoch=meta.get("update", 0),
            provenance=meta,
        ),
        tmp,
    )
    os.replace(tmp, path)
    resume = path.with_name(path.stem + "-resume.pt")
    tmp = resume.with_suffix(".partial")
    torch.save(
        dict(
            schema="inklab.bcppo.resume.v1",
            model=model.state_dict(),
            optimizer=optimizer.state_dict(),
            torch_rng=torch.get_rng_state(),
            cuda_rng=torch.cuda.get_rng_state_all(),
            **meta,
        ),
        tmp,
    )
    os.replace(tmp, resume)


@torch.no_grad()
def bootstrap(model, obs, hidden):
    return model({k: x[None] for k, x in obs.items()}, hidden)[1][0]


def critic_preheat(a, model, match, out):
    """Full BC-policy episodes, Monte Carlo targets; only value.weight/bias fit."""
    previous = {
        k: x.detach().clone()
        for k, x in model.state_dict().items()
        if not k.startswith("value.")
    }
    latent = []
    rewards = []
    handle = model.value.register_forward_pre_hook(
        lambda module, args: latent.append(args[0][0].detach().half().clone())
    )
    wall = time.monotonic()
    with torch.no_grad():
        for episode in range(a.critic_episodes):
            match.reset(a.seed + episode, "easy", near=0.5)
            match.env.set_auxiliary_scale(1.0)
            hidden = model.initial(match.env.n, match.env.device)
            episode_rewards = []
            while True:
                obs = match.observation()
                actions, _, _, hidden = model.act(obs, hidden)
                reward, done, _, _ = match.step(actions, guide_scale=1.0)
                episode_rewards.append(reward.clone())
                if bool(done.all()):
                    break
            returns = torch.zeros_like(reward)
            targets = []
            for r in reversed(episode_rewards):
                returns = r + a.gamma * returns
                targets.append(returns.clone())
            rewards.extend(reversed(targets))
    handle.remove()
    x = torch.cat(latent)
    target = torch.cat(rewards)
    loss_before = float(
        ((model.value(x.float()).squeeze(-1) - target) ** 2).mean().detach()
    )
    opt = torch.optim.Adam(model.value.parameters(), lr=0.001)
    for epoch in range(6):
        for ids in torch.randperm(len(x), device=x.device).split(4096):
            loss = (
                (model.value(x[ids].float()).squeeze(-1) - target[ids]).square().mean()
            )
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
    after = float(((model.value(x.float()).squeeze(-1) - target) ** 2).mean().detach())
    unchanged = all(torch.equal(previous[k], model.state_dict()[k]) for k in previous)
    if not unchanged:
        raise RuntimeError("critic preheat modified actor")
    report = dict(
        episodes=a.critic_episodes,
        samples=len(x),
        seconds=time.monotonic() - wall,
        mse_before=loss_before,
        mse_after=after,
        actor_exactly_unchanged=unchanged,
        target_mean=float(target.mean()),
        target_std=float(target.std()),
    )
    atomic_json(out / "critic-preheat.json", report)
    return report


def main(a):
    torch.set_num_threads(2)
    torch.set_float32_matmul_precision("high")
    torch.manual_seed(a.seed)
    if a.hours > 48 or a.hours <= 0:
        raise ValueError("wall budget must be in(0,48]h")
    if a.eval_envs < 32:
        raise ValueError("formal script eval requires>=32 full matches")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    (out / "checkpoints").mkdir()
    wall = time.monotonic()
    start_utc = time.time()
    budget = a.hours * 3600
    model, meta = initialize(a.bc, a.device)
    resumed = None
    if a.resume:
        resumed = torch.load(a.resume, map_location="cpu", weights_only=False)
        if resumed.get("schema") != "inklab.bcppo.resume.v1":
            raise ValueError("owned PPO resume schema required")
        if resumed.get("bc_sha256") != digest(a.bc):
            raise ValueError("BC identity differs at resume")
        wall -= resumed["elapsed"]
    model.train()
    teacher = copy.deepcopy(model).eval()
    for p in teacher.parameters():
        p.requires_grad_(False)
    with torch.no_grad():
        model.value.weight.zero_()
        model.value.bias.zero_()
    config = vars(a) | dict(
        bc_sha256=digest(a.bc),
        model_parameters=sum(p.numel() for p in model.parameters()),
        scope="Stage1 Stamper only; .52 frozen. No native host or VPT access.",
        curriculum="50% near starts fade first25%wall; easy -> D4 ->75%D4/25%frozen history by capability; acceptance always normal spawn180s",
        reward="kill1,terminal.5 unchanged; life-capped damage.75,total includes extra.25; paint.02/percent; guidance separately capped. All auxiliaries fade first25%wall",
        actor_semantics="BC2 exact nofeedback physical levels, ZR/ZL2 classes; primary R/RS unavailable; no forced release",
        source_sha256={
            str(p.relative_to(Path(__file__).parents[1])): digest(p)
            for p in Path(__file__).parents[1].rglob("*.py")
        },
        started_unix=start_utc,
    )
    atomic_json(out / "config.json", config)
    train = Match(a, a.n_envs, True)
    preheat = (
        critic_preheat(a, model, train, out)
        if resumed is None
        else dict(
            resumed_from=a.resume, skip_preheat=True, environment_reset_at_resume=True
        )
    )
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=a.lr, eps=1e-5, weight_decay=1e-4
    )
    if resumed:
        model.load_state_dict(resumed["model"])
        optimizer.load_state_dict(resumed["optimizer"])
        torch.set_rng_state(resumed["torch_rng"])
        torch.cuda.set_rng_state_all(resumed["cuda_rng"])
    export(
        out / "checkpoints/preheated.pt",
        model,
        optimizer,
        update=resumed["update"] if resumed else 0,
        frames=resumed["frames"] if resumed else 0,
        elapsed=time.monotonic() - wall,
        phase=resumed.get("phase", "easy") if resumed else "easy",
        bc_sha256=config["bc_sha256"],
        best_formal_damage=resumed.get("best_formal_damage", 0.0) if resumed else 0.0,
    )
    writer = None
    try:
        from torch.utils.tensorboard import SummaryWriter

        writer = SummaryWriter(str(out / "tensorboard"))
    except ImportError:
        pass
    metrics = CSV(out / "metrics.csv")
    episode = 0
    frames = resumed["frames"] if resumed else 0
    iteration = resumed["update"] if resumed else 0
    phase = resumed.get("phase", "easy") if resumed else "easy"
    best = (-1.0, -1.0, -1.0)
    last_eval = -1e20
    last_save = time.monotonic()
    best_formal_damage = resumed.get("best_formal_damage", 0.0) if resumed else 0.0
    eval_match = None
    eval_index = 0
    health_evaluated = False
    reason = "wall_budget"
    meter = CombatMeter(a.n_envs, train.env.device)
    zr_streak = torch.zeros(a.n_envs, device=a.device)
    longest_zr = 0.0
    collapse_streak = 0

    def reset():
        nonlocal episode, meter
        history = a.history[episode % len(a.history)] if phase == "history" else None
        train.reset(
            a.seed + 1000 + episode,
            phase,
            near=schedule(time.monotonic() - wall, budget)["near_fraction"],
            history=history,
        )
        meter = CombatMeter(a.n_envs, train.env.device)
        episode += 1
        return model.initial(a.n_envs, a.device), teacher.initial(a.n_envs, a.device)

    hidden, teacher_hidden = reset()
    before = torch.ones(a.n_envs, dtype=torch.bool, device=a.device)
    cumulative = torch.zeros(a.n_envs, 2, EVENT_SIZE, device=a.device)
    status = dict(
        state="running", pid=os.getpid(), started_unix=start_utc, preheat=preheat
    )
    print(json.dumps(dict(event="training-ready", preheat=preheat)), flush=True)
    try:
        while time.monotonic() - wall < budget:
            elapsed = time.monotonic() - wall
            due = (
                last_eval < 0
                or (not health_evaluated and elapsed >= a.health_eval_minutes * 60)
                or elapsed - last_eval >= a.eval_hours * 3600
                or (
                    elapsed >= a.zero_damage_hours * 3600
                    and best_formal_damage == 0
                    and last_eval < a.zero_damage_hours * 3600
                )
            )
            if due:
                eval_rows = []
                for kind in ["easy", "script"]:
                    for greedy in [False, True]:
                        row, eval_match = evaluate(
                            a,
                            model,
                            out
                            / f"eval-{eval_index:03}-{kind}-{'greedy' if greedy else 'sampled'}",
                            a.seed + 900000 + int(greedy),
                            kind,
                            greedy,
                            eval_match,
                        )
                        eval_rows.append(row)
                        with (out / "evaluations.jsonl").open("a") as f:
                            f.write(json.dumps(row) + "\n")
                formal = [r for r in eval_rows if r["opponent"] == "script"]
                score = max(
                    (r["mean_weapon_kills"], r["mean_damage"], r["win_rate"])
                    for r in formal
                )
                if score > best:
                    best = score
                    export(
                        out / "best.pt",
                        model,
                        optimizer,
                        update=iteration,
                        frames=frames,
                        elapsed=elapsed,
                        evaluation=eval_rows,
                        phase=phase,
                        bc_sha256=config["bc_sha256"],
                        best_formal_damage=max(
                            best_formal_damage, max(r["mean_damage"] for r in formal)
                        ),
                    )
                best_formal_damage = max(
                    best_formal_damage, max(r["mean_damage"] for r in formal)
                )
                easy = max(
                    (r for r in eval_rows if r["opponent"] == "easy"),
                    key=lambda r: r["mean_weapon_kills"],
                )
                if (
                    phase == "easy"
                    and easy["mean_weapon_kills"] >= 0.5
                    and easy["mean_damage"] >= 50
                ):
                    phase = "script"
                if (
                    phase == "script"
                    and max(r["mean_weapon_kills"] for r in formal) >= 1
                    and a.history
                ):
                    phase = "history"
                atomic_json(
                    out / "latest-evaluation.json",
                    dict(
                        index=eval_index, elapsed=elapsed, phase=phase, rows=eval_rows
                    ),
                )
                print(
                    json.dumps(
                        dict(
                            event="evaluation",
                            index=eval_index,
                            elapsed=elapsed,
                            phase=phase,
                            rows=eval_rows,
                        )
                    ),
                    flush=True,
                )
                eval_index += 1
                last_eval = time.monotonic() - wall
                if elapsed >= a.health_eval_minutes * 60:
                    health_evaluated = True
                # Both decisions and the attack metric remain explicit; turf-only
                # wins cannot pass the conjunctive weapon-KO gate.
                passed = [r for r in formal if r["passed"]]
                if passed:
                    export(
                        out / "passed.pt",
                        model,
                        optimizer,
                        update=iteration,
                        frames=frames,
                        evaluation=passed,
                        elapsed=elapsed,
                        phase=phase,
                        bc_sha256=config["bc_sha256"],
                        best_formal_damage=best_formal_damage,
                    )
                    reason = "gpu_gate_passed_native_precheck_pending"
                    break
                # Held-out rollout reset does not touch train env/hidden/RNG.
                model.train()
            if (
                time.monotonic() - wall >= a.zero_damage_hours * 3600
                and best_formal_damage == 0
            ):
                reason = "six_hour_zero_formal_damage"
                break
            if (out / "STOP").exists():
                reason = "STOP_file"
                break
            coef = schedule(time.monotonic() - wall, budget)
            train.env.set_auxiliary_scale(coef["auxiliary"])
            batch = {
                k: []
                for k in [
                    "obs",
                    "hidden",
                    "before",
                    "actions",
                    "logprob",
                    "heads",
                    "values",
                    "teacher",
                    "rewards",
                    "after",
                ]
            }
            visible = 0.0
            pitch_clamped = 0.0
            zr = 0.0
            zero = 0.0
            guide = torch.zeros(3, device=a.device)
            with torch.no_grad():
                for step in range(a.rollout):
                    obs = train.observation()
                    logits, value, next_hidden = model(
                        {k: x[None] for k, x in obs.items()}, hidden
                    )
                    ref, _, teacher_hidden = teacher(
                        {k: x[None] for k, x in obs.items()}, teacher_hidden
                    )
                    dist = distributions(logits[0])
                    action = dist.sample()
                    logs = dist.log_prob(action)
                    batch["obs"].append(
                        {
                            k: x.half().clone() if x.is_floating_point() else x.clone()
                            for k, x in obs.items()
                        }
                    )
                    for k, x in dict(
                        hidden=hidden,
                        before=before,
                        actions=action,
                        logprob=logs.sum(-1),
                        heads=logs,
                        values=value[0],
                        teacher=ref[0].softmax(-1).half(),
                    ).items():
                        batch[k].append(x.clone())
                    reward, done, info, diag = train.step(action, coef["auxiliary"])
                    batch["rewards"].append(reward.clone())
                    batch["after"].append(done.clone())
                    cumulative += info["events"]
                    meter.capture(train.env, diag["physical"], info)
                    visible += float(diag["visible"].sum())
                    zr += float(action[:, 3].sum())
                    zr_streak = torch.where(
                        action[:, 3] > 0, zr_streak + train.env.cfg.decision_frames, 0.0
                    )
                    longest_zr = max(longest_zr, float(zr_streak.max()))
                    pitch_clamped += float(
                        (train.env.state[:, 0, PITCH].abs() >= 1.099).sum()
                    )
                    zero += float((reward.abs() > 1e-9).sum())
                    guide += diag["guide"].sum(0)
                    frames += a.n_envs * train.env.cfg.decision_frames
                    hidden = next_hidden * (~done)[None, :, None]
                    teacher_hidden *= (~done)[None, :, None]
                    before = done
                    if bool(done.all()):
                        counts = info["turf_counts"]
                        record = dict(
                            episode=episode,
                            frames=frames,
                            elapsed=time.monotonic() - wall,
                            phase=phase,
                            near_starts=train.near,
                            weapon_kills=float(cumulative[:, 1, 5].sum()),
                            damage=float(cumulative[:, 1, 0].sum() * 100),
                            mean_turf_percent=float(
                                (counts[:, 0] / train.env.paint_count * 100).mean()
                            ),
                            combat=meter.report(),
                        )
                        with (out / "matches.jsonl").open("a") as f:
                            f.write(json.dumps(record) + "\n")
                        cumulative.zero_()
                        zr_streak.zero_()
                        hidden, teacher_hidden = reset()
            tensors = {k: torch.stack(x) for k, x in batch.items() if k != "obs"}
            tensors["obs"] = {
                k: torch.stack([x[k] for x in batch["obs"]]) for k in batch["obs"][0]
            }
            with torch.no_grad():
                value = bootstrap(model, train.observation(), hidden)
            stats = update(
                model,
                optimizer,
                tensors,
                value,
                bc_coef=coef["bc_kl"],
                entropy_coef=coef["entropy"],
                zr_entropy=coef["extra_zr_entropy"],
                sequence=a.sequence,
                minibatch=a.minibatch,
                epochs=a.epochs,
                gamma=a.gamma,
            )
            iteration += 1
            elapsed = time.monotonic() - wall
            row = dict(
                update=iteration,
                environment_frames=frames,
                wall_seconds=elapsed,
                phase=phase,
                auxiliary_scale=coef["auxiliary"],
                bc_kl_coef=coef["bc_kl"],
                entropy_coef=coef["entropy"],
                zr_entropy_coef=coef["extra_zr_entropy"],
                near_fraction=coef["near_fraction"],
                **stats,
                visible_fraction=visible / (a.rollout * a.n_envs),
                zr_fraction=zr / (a.rollout * a.n_envs),
                nonzero_reward_rate=zero / (a.rollout * a.n_envs),
                approach_reward_raw=float(guide[0]),
                aim_reward_raw=float(guide[1]),
                attack_reward_raw=float(guide[2]),
                attacks_per_minute=meter.report()["stamper"]["attacks_per_minute"],
                full_per_minute=meter.report()["stamper"]["full_releases_per_minute"],
                longest_zr_frames=longest_zr,
                pitch_clamped_fraction=pitch_clamped / (a.rollout * a.n_envs),
                peak_cuda_mib=torch.cuda.max_memory_allocated() / 2**20,
            )
            metrics.write(row)
            collapse_streak = (
                collapse_streak + 1
                if row["zr_fraction"] > 0.98 and row["entropy_ZR"] < 0.05
                else 0
            )
            if collapse_streak >= 10:
                atomic_json(
                    out / "collapse-warning.json",
                    dict(
                        update=iteration,
                        elapsed=elapsed,
                        zr_fraction=row["zr_fraction"],
                        entropy_ZR=row["entropy_ZR"],
                        note="10 near-deterministic held-ZR rollouts; diagnostics only, no forced-release macro",
                    ),
                )
            status.update(
                row,
                last_evaluation=eval_index - 1,
                best_formal_damage=best_formal_damage,
                healthy=all(
                    torch.isfinite(torch.tensor(v))
                    for v in stats.values()
                    if isinstance(v, (float, int))
                ),
            )
            atomic_json(out / "status.json", status)
            if iteration % 10 == 0:
                print(json.dumps(row), flush=True)
            if writer:
                for k, v in row.items():
                    if isinstance(v, (float, int)):
                        writer.add_scalar(k, v, frames)
            if time.monotonic() - last_save >= a.save_minutes * 60:
                export(
                    out / f"checkpoints/u{iteration:07}.pt",
                    model,
                    optimizer,
                    update=iteration,
                    frames=frames,
                    elapsed=elapsed,
                    phase=phase,
                    bc_sha256=config["bc_sha256"],
                    best_formal_damage=best_formal_damage,
                )
                last_save = time.monotonic()
    except Exception as exc:
        reason = "exception:" + repr(exc)
        raise
    finally:
        elapsed = time.monotonic() - wall
        export(
            out / "last.pt",
            model,
            optimizer,
            update=iteration,
            frames=frames,
            elapsed=elapsed,
            reason=reason,
            phase=phase,
            bc_sha256=config["bc_sha256"],
            best_formal_damage=best_formal_damage,
        )
        status.update(
            state="stopped",
            reason=reason,
            elapsed=elapsed,
            frames=frames,
            best_formal_damage=best_formal_damage,
        )
        atomic_json(out / "status.json", status)
        if reason == "six_hour_zero_formal_damage":
            from .diagnose import run

            run(a, train, out, status)
        metrics.close()
        if writer:
            writer.close()
        print(
            json.dumps(dict(event="stopped", reason=reason, elapsed=elapsed)),
            flush=True,
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ["data", "calibration", "contract", "mask-bank", "bc", "out"]:
        p.add_argument("--" + k, required=True)
    p.add_argument("--history", action="append", default=[])
    p.add_argument(
        "--resume",
        help="private owned PPO resume checkpoint; starts a fresh match, cumulative wall budget",
    )
    p.add_argument("--n-envs", type=int, default=128)
    p.add_argument("--eval-envs", type=int, default=32)
    p.add_argument("--seed", type=int, default=81)
    p.add_argument("--device", default="cuda")
    p.add_argument("--hours", type=float, default=24)
    p.add_argument("--eval-hours", type=float, default=1)
    p.add_argument("--health-eval-minutes", type=float, default=30)
    p.add_argument("--zero-damage-hours", type=float, default=6)
    p.add_argument("--save-minutes", type=float, default=15)
    p.add_argument("--critic-episodes", type=int, default=2)
    p.add_argument("--lr", type=float, default=0.0001)
    p.add_argument("--gamma", type=float, default=0.9995)
    p.add_argument("--rollout", type=int, default=128)
    p.add_argument("--sequence", type=int, default=32)
    p.add_argument("--minibatch", type=int, default=16)
    p.add_argument("--epochs", type=int, default=3)
    main(p.parse_args())
