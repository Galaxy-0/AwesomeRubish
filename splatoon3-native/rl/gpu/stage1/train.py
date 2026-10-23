"""Bounded stage1 recurrent PPO run. Private checkpoints; no native host imports."""

import argparse, json, time, math
from pathlib import Path
import torch
from ..env import EVENT_SIZE
from .common import environment, checkpoint, CSV, digest
from .policy import Policy, prepare
from .opponents import League
from .ppo import update
from .curriculum import encounter_starts


def main(a):
    torch.set_num_threads(a.cpu_threads)
    torch.set_float32_matmul_precision("high")
    torch.manual_seed(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    (out / "checkpoints").mkdir()
    start = time.perf_counter()
    env = environment(
        a.data, a.calibration, a.n_envs, a.device, compiled=not a.no_compile
    )
    policy = Policy(a.hidden).to(a.device)
    optimizer = torch.optim.Adam(
        policy.parameters(), lr=a.lr, eps=1e-5, fused=str(a.device).startswith("cuda")
    )
    begin_update = 0
    frames = 0
    resume_data = None
    if a.resume:
        resume_data = torch.load(a.resume, map_location="cpu", weights_only=False)
        assert resume_data["schema"] == "inklab.rl.stage1.checkpoint.v1"
        policy.load_state_dict(resume_data["policy"])
        optimizer.load_state_dict(resume_data["optimizer"])
        for group in optimizer.param_groups:
            group["lr"] = a.lr
        torch.set_rng_state(resume_data["torch_rng"])
        if str(a.device).startswith("cuda") and resume_data.get("cuda_rng"):
            torch.cuda.set_rng_state_all(resume_data["cuda_rng"])
        begin_update = resume_data["update"]
        frames = resume_data["frames"]
    if a.frames <= frames:
        raise ValueError("target frames must exceed resumed checkpoint")
    league = League(policy, a.n_envs, a.device, a.seed)
    if resume_data and resume_data.get("league"):
        league.snapshots = resume_data["league"]
        league.new_match()
    config = vars(a) | dict(
        parameters=sum(p.numel() for p in policy.parameters()),
        fov="55deg vertical ASSUMPTION; exact16:9 horizontal85.56559; pending native projection",
        known_map_error_u=4.338097024348868,
        reward="zero-sum kill1,turf-terminal.5,life-capped damage.5,turf.02/percent; auxiliaries linear first30%",
        league="50% latest/40% historical(two20% cohorts)/10% held16-decision random",
        curriculum="first30% only: up to70% near-ground starts6..18u, fades to normal spawns; all games180s; held-out normal-spawn evaluation separate",
        data_sha256=digest(Path(a.data) / "parameters.json"),
        map_sha256=digest(Path(a.data) / "map.npz"),
        source_sha256={
            str(p.relative_to(Path(__file__).resolve().parents[1])): digest(p)
            for p in Path(__file__).resolve().parents[1].rglob("*.py")
        },
    )
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    csv = CSV(out / "metrics.csv")
    writer = None
    try:
        from torch.utils.tensorboard import SummaryWriter

        writer = SummaryWriter(str(out / "tensorboard"))
    except ImportError:
        print("TensorBoard unavailable; complete metrics retained in CSV", flush=True)
    obs, _ = env.reset(seed=a.seed)
    episode = 0
    ncurr = encounter_starts(
        env, 0.7 * max(0, 1 - frames / (a.schedule_frames * 0.3)), a.seed
    )
    obs = env._observation(env.state, env.shots, env.paint, env.steps)
    hidden = policy.initial(a.n_envs * 2, a.device)
    before = torch.ones(a.n_envs * 2, dtype=torch.bool, device=a.device)
    random_actions = env.random_actions()
    match_reward = torch.zeros((a.n_envs, 2), device=a.device)
    match_events = torch.zeros((a.n_envs, 2, EVENT_SIZE), device=a.device)
    match_records = []
    frame_unit = a.n_envs * env.cfg.decision_frames
    max_updates = (
        math.ceil((a.frames - frames) / (frame_unit * a.rollout)) + begin_update
    )
    last_path = None
    if not a.resume:
        checkpoint(
            out / "checkpoints/u000000.pt",
            policy,
            optimizer,
            update=0,
            frames=0,
            config=config,
            league=league,
        )
    print(
        json.dumps(
            dict(
                event="training-ready",
                parameters=config["parameters"],
                target_frames=a.frames,
                n_envs=a.n_envs,
                construction_seconds=time.perf_counter() - start,
            )
        ),
        flush=True,
    )
    try:
        for iteration in range(begin_update + 1, max_updates + 1):
            rollout_start = time.perf_counter()
            progress = frames / a.schedule_frames
            scale = max(0.0, 1 - progress / 0.3)
            env.set_auxiliary_scale(scale)
            stored = {
                k: []
                for k in [
                    "obs",
                    "actions",
                    "logprob",
                    "values",
                    "rewards",
                    "done_after",
                    "done_before",
                    "hidden",
                    "learn",
                ]
            }
            policy.train()
            with torch.no_grad():
                for step in range(a.rollout):
                    visible = prepare(obs)
                    stored["obs"].append(
                        {
                            k: v.detach().to(torch.float16).clone()
                            if v.dtype.is_floating_point
                            else v.detach().clone()
                            for k, v in visible.items()
                        }
                    )
                    stored["hidden"].append(hidden.detach().clone())
                    stored["done_before"].append(before.clone())
                    action, logprob, value, next_hidden = policy.act(visible, hidden)
                    if ((iteration - 1) * a.rollout + step) % 16 == 0:
                        random_actions = env.random_actions()
                    action = league.override(
                        visible, action.reshape(a.n_envs, 2, 8), random_actions
                    )
                    obs, reward, term, trunc, info = env.step(action)
                    after = term.reshape(-1).clone()
                    stored["actions"].append(action.reshape(a.n_envs * 2, 8).clone())
                    stored["logprob"].append(logprob.clone())
                    stored["values"].append(value.clone())
                    stored["rewards"].append(reward.reshape(-1).clone())
                    stored["done_after"].append(after)
                    stored["learn"].append(league.learner.reshape(-1).clone())
                    hidden = next_hidden * (~after)[None, :, None]
                    before = after
                    frames += frame_unit
                    match_reward += reward
                    match_events += info["events"]
                    if bool(term[:, 0].all().item()):
                        counts = info["turf_counts"]
                        winner = torch.sign(counts[:, 0] - counts[:, 1])
                        record = dict(
                            episode=episode,
                            frames=frames,
                            aux_scale=scale,
                            curriculum_starts=ncurr,
                            alpha_win=float((winner > 0).float().mean().item()),
                            bravo_win=float((winner < 0).float().mean().item()),
                            draw=float((winner == 0).float().mean().item()),
                            damage_received=match_events[:, :, 0].sum(0).cpu().tolist(),
                            deaths=match_events[:, :, 1].sum(0).cpu().tolist(),
                            weapon_kills=match_events[:, :, 5]
                            .flip(1)
                            .sum(0)
                            .cpu()
                            .tolist(),
                            self_splats=(match_events[:, :, 1] - match_events[:, :, 5])
                            .sum(0)
                            .cpu()
                            .tolist(),
                            turf_percent=(counts / env.paint_count * 100)
                            .mean(0)
                            .cpu()
                            .tolist(),
                            history_versions=league.assignments,
                            reward=match_reward.mean(0).cpu().tolist(),
                        )
                        match_records.append(record)
                        with (out / "matches.jsonl").open("a") as f:
                            f.write(json.dumps(record) + "\n")
                        episode += 1
                        obs, _ = env.reset(seed=a.seed + episode)
                        ncurr = encounter_starts(
                            env,
                            0.7 * max(0, 1 - frames / (a.schedule_frames * 0.3)),
                            a.seed + episode,
                        )
                        obs = env._observation(
                            env.state, env.shots, env.paint, env.steps
                        )
                        league.new_match()
                        random_actions = env.random_actions()
                        match_reward.zero_()
                        match_events.zero_()
            batch = {k: torch.stack(v) for k, v in stored.items() if k != "obs"}
            batch["obs"] = {
                k: torch.stack([v[k] for v in stored["obs"]]) for k in stored["obs"][0]
            }
            with torch.no_grad():
                latest = prepare(obs)
                bootstrap = policy({k: v[None] for k, v in latest.items()}, hidden)[1][
                    0
                ]
            stats = update(
                policy,
                optimizer,
                batch,
                bootstrap,
                sequence_length=a.sequence,
                minibatch_sequences=a.minibatch_sequences,
                epochs=a.epochs,
                gamma=a.gamma,
                lam=a.gae_lambda,
                entropy_coef=a.entropy * (1 - 0.8 * min(1, progress)),
                target_kl=a.target_kl,
            )
            if not stats["finite"]:
                raise FloatingPointError(
                    "Nonfinite network; stop and preserve checkpoint/logs"
                )
            wall = time.perf_counter() - start
            recent = match_records[-1] if match_records else None
            row = dict(
                update=iteration,
                environment_frames=frames,
                wall_seconds=wall,
                environment_frames_per_second=(
                    frames - (resume_data["frames"] if resume_data else 0)
                )
                / wall,
                update_seconds=time.perf_counter() - rollout_start,
                aux_scale=scale,
                **stats,
                alpha_win=recent["alpha_win"] if recent else "",
                bravo_win=recent["bravo_win"] if recent else "",
                alpha_kd=(recent["weapon_kills"][0] / max(1, recent["deaths"][0]))
                if recent
                else "",
                bravo_kd=(recent["weapon_kills"][1] / max(1, recent["deaths"][1]))
                if recent
                else "",
                alpha_damage=recent["damage_received"][1] * 100 if recent else "",
                bravo_damage=recent["damage_received"][0] * 100 if recent else "",
                alpha_turf=recent["turf_percent"][0] if recent else "",
                bravo_turf=recent["turf_percent"][1] if recent else "",
                peak_allocated_mib=torch.cuda.max_memory_allocated() / 2**20
                if str(a.device).startswith("cuda")
                else 0,
            )
            csv.write(row)
            if writer:
                for key, value in row.items():
                    if isinstance(value, (float, int)) and not isinstance(value, bool):
                        writer.add_scalar(key, value, frames)
            if iteration % a.log_every == 0:
                print(json.dumps(dict(event="update", **row)), flush=True)
            if iteration % a.snapshot_every == 0:
                league.snapshot(iteration)
            if iteration % a.checkpoint_every == 0 or iteration == max_updates:
                last_path = out / "checkpoints" / f"u{iteration:06}.pt"
                checkpoint(
                    last_path,
                    policy,
                    optimizer,
                    update=iteration,
                    frames=frames,
                    config=config,
                    league=league,
                )
                print(
                    json.dumps(
                        dict(event="checkpoint", path=str(last_path), frames=frames)
                    ),
                    flush=True,
                )
            # Optional operator stop is read at safe update boundaries; no kill needed.
            if (out / "STOP").exists():
                if iteration % a.checkpoint_every:
                    last_path = out / "checkpoints" / f"u{iteration:06}.pt"
                    checkpoint(
                        last_path,
                        policy,
                        optimizer,
                        update=iteration,
                        frames=frames,
                        config=config,
                        league=league,
                    )
                break
    finally:
        csv.close()
        if writer:
            writer.close()
    summary = dict(
        frames=frames,
        updates=iteration,
        wall_seconds=time.perf_counter() - start,
        checkpoint=str(last_path),
        parameters=config["parameters"],
        peak_allocated_mib=torch.cuda.max_memory_allocated() / 2**20
        if str(a.device).startswith("cuda")
        else 0,
        stage=1,
        stage1_passed=False,
        reason="Training completed; held-out gates and replay behavior evaluated separately",
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--calibration", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=123)
    p.add_argument("--n-envs", type=int, default=256)
    p.add_argument("--schedule-frames", type=int, default=64_000_000)
    p.add_argument("--frames", type=int, default=64_000_000)
    p.add_argument("--hidden", type=int, default=384)
    p.add_argument("--rollout", type=int, default=128)
    p.add_argument("--sequence", type=int, default=32)
    p.add_argument("--minibatch-sequences", type=int, default=64)
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--gamma", type=float, default=0.9995)
    p.add_argument("--gae-lambda", type=float, default=0.95)
    p.add_argument("--entropy", type=float, default=0.0015)
    p.add_argument("--target-kl", type=float, default=0.04)
    p.add_argument("--snapshot-every", type=int, default=40)
    p.add_argument("--checkpoint-every", type=int, default=100)
    p.add_argument("--log-every", type=int, default=5)
    p.add_argument("--cpu-threads", type=int, default=1)
    p.add_argument("--no-compile", action="store_true")
    p.add_argument("--resume")
    a = p.parse_args()
    if a.n_envs < 10 or a.rollout % a.sequence:
        raise ValueError("at least10 environments and complete sequences")
    main(a)
