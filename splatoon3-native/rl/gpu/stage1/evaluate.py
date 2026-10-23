"""Full180s held-out evaluations; no reward shaping contributes to win counts."""

import argparse, json, time, math
from pathlib import Path
import torch
from .common import environment, load_policy, wilson
from .policy import prepare
from .opponents import D4Defender, neutral
from ..record import Recorder
from ..env import HP, SUB, YAW, HEADING, GROUND, EVENT_SIZE


def d4_positions(env):
    """Predeclared common-ground states,8 headings,12/16u approach starts.

    This is separate from normal-spawn turf games so stationary spawn campers
    cannot pass a gunfight claim simply because the learner paints elsewhere.
    """
    centers = torch.tensor(
        [[0.0, 3.0, 0.0], [-18.0, 3.0, 0.0], [0.0, 3.0, -12.0]], device=env.device
    )
    centers = env.geo.points[torch.cdist(centers, env.geo.points).argmin(-1)]
    ids = torch.arange(env.n, device=env.device)
    center = centers[ids % 3]
    heading = (ids % 4) * math.pi / 2
    approach = (ids % 8) * math.pi / 4
    radius = torch.where(ids % 2 == 0, 12.0, 16.0)
    wish = center + torch.stack(
        [approach.sin() * radius, torch.zeros_like(radius), approach.cos() * radius], -1
    )
    source = env.geo.points[torch.cdist(wish, env.geo.points).argmin(-1)]
    env.state[:, 0, :3] = source
    env.state[:, 1, :3] = center
    # Initial camera poses are fixture inputs, not enemy-position features.
    delta = center - source
    env.state[:, 0, YAW] = torch.atan2(delta[:, 0], delta[:, 2])
    env.state[:, 1, YAW] = heading
    env.state[:, :, HEADING] = env.state[:, :, YAW]
    env.state[:, :, GROUND] = 1
    return heading, dict(
        centers=centers.cpu().tolist(),
        source=source.cpu().tolist(),
        enemy=center.cpu().tolist(),
        heading=heading.cpu().tolist(),
        scope="Fixed common-state encounter cohort, not normal spawns; direct D4 reference aim, no movement or ballistic compensation",
    )


@torch.no_grad()
def play(
    policy,
    data,
    calibration,
    *,
    games=128,
    kind="random",
    seed=10001,
    device="cuda",
    deterministic=True,
    trace=None,
    opponent=None,
    trace_env=0,
):
    torch.manual_seed(seed)
    env = environment(data, calibration, games, device)
    obs, _ = env.reset(seed=seed)
    setup = None
    script = None
    if kind == "d4-encounter":
        heading, setup = d4_positions(env)
        script = D4Defender(env, heading)
    elif kind == "d4-spawn":
        script = D4Defender(env)
    hidden = policy.initial(games * 2, device)
    other_hidden = opponent.initial(games * 2, device) if opponent else None
    roles = (
        torch.arange(games, device=device) % 2
        if kind in ("random", "history")
        else torch.zeros(games, dtype=torch.long, device=device)
    )
    rows = torch.arange(games, device=device)
    if not 0 <= trace_env < games:
        raise ValueError("trace environment index outside batch")
    record = Recorder(env, environment=trace_env, stride=6) if trace else None
    totals = torch.zeros((games, 2, EVENT_SIZE), device=device)
    healing = torch.zeros((games, 2), device=device)
    cover = torch.zeros_like(healing)
    damaging_heal = torch.zeros_like(healing)
    first_kill = torch.full((games, 2), -1, dtype=torch.long, device=device)
    previous_actions = neutral(games, device)
    invalid_special = torch.zeros((), dtype=torch.int64, device=device)
    next_random = env.random_actions()
    start = time.perf_counter()
    for step in range(5400):
        # Observation after explicit initial placement, and on every subsequent step.
        if step == 0:
            obs = env._observation(env.state, env.shots, env.paint, env.steps)
        prepared = prepare(obs, previous_actions)
        action, _, _, hidden = policy.act(prepared, hidden, deterministic)
        action = action.reshape(games, 2, 8)
        if kind == "history":
            oa, _, _, other_hidden = opponent.act(prepared, other_hidden, deterministic)
            other = oa.reshape(games, 2, 8)
        elif script:
            other = script.actions()
        else:
            if step % 16 == 0:
                next_random = env.random_actions()
            other = next_random
        action[rows, 1 - roles] = other[rows, 1 - roles]
        invalid_special += (action[:, :, 6:] != 0).sum()
        oldhp = env.state[:, :, HP].clone()
        oldpos = env.state[:, :, :3].clone()
        obs, reward, term, trunc, info = env.step(action)
        previous_actions = action.detach().clone()
        totals += info["events"]
        recovering = (
            (oldhp > 0)
            & (oldhp < 0.5)
            & (env.state[:, :, HP] > oldhp + 1e-5)
            & (env.state[:, :, SUB] > 0)
            & (env.state[:, :, HP] > 0)
        )
        healing += recovering
        damaging_heal += recovering & (totals[:, :, 0] > 0)
        # Descriptive use of cover only: wounded, moves, and field blocks enemy.
        if step % 6 == 0:
            p = env.state[:, :, :3] + torch.tensor([0.0, 1.0, 0.0], device=device)
            d = p.flip(1) - p
            length = d.norm(dim=-1)
            blocked, _, _ = env.geo.ray(
                p, d / length[..., None].clamp_min(1e-6), 64.0, 0.75
            )
            covered = (blocked < length - 0.35) & (length < 30)
            cover += (
                covered
                & (oldhp > 0)
                & (env.state[:, :, HP] > 0)
                & (oldhp < 0.5)
                & ((env.state[:, :, :3] - oldpos).norm(dim=-1) > 0.005)
            )
        kills = info["events"][:, :, 5].flip(1) > 0
        first_kill = torch.where(
            (first_kill < 0) & kills, env.steps[:, None], first_kill
        )
        if record:
            record.capture(action, info)
        if step % 900 == 0:
            print(
                json.dumps(
                    dict(
                        event="evaluation-progress",
                        kind=kind,
                        step=step,
                        frame=int(env.steps[0].item()),
                    )
                ),
                flush=True,
            )
    if str(device).startswith("cuda"):
        torch.cuda.synchronize()
    count = info["turf_counts"]
    winner = torch.sign(count[:, 0] - count[:, 1]).long()
    desired = torch.where(roles == 0, 1, -1)
    win = winner == desired
    draw = winner == 0
    report = dict(
        kind=kind,
        games=games,
        seed=seed,
        frames=10800,
        wall_seconds=time.perf_counter() - start,
        deterministic=deterministic,
        all_terminated=bool(term.all().item()),
        finite=bool(torch.isfinite(env.state).all().item()),
        invalid_special_inputs=bool(invalid_special.item()),
        invalid_special_input_count=int(invalid_special.item()),
        roles={},
        fixture=setup,
        script_privileged_referee_reads=bool(script),
        model_scope="GPU approximation, stage1 primary only; no native/player win-rate claim",
    )
    for role, name in [(0, "stamper"), (1, "52")]:
        mask = roles == role
        number = int(mask.sum().item())
        if not number:
            continue
        wins = int((win & mask).sum().item())
        draws = int((draw & mask).sum().item())
        damage = totals[mask, 1 - role, 0].sum().item() * 100
        deaths = totals[mask, role, 1].sum().item()
        kills = totals[mask, 1 - role, 5].sum().item()
        report["roles"][name] = dict(
            games=number,
            wins=wins,
            losses=number - wins - draws,
            draws=draws,
            win_rate=wins / number,
            wilson95=wilson(wins, number),
            kills=kills,
            deaths=deaths,
            self_splats=float(
                (totals[mask, role, 1] - totals[mask, role, 5]).sum().item()
            ),
            kd=kills / max(1, deaths),
            damage_dealt=damage,
            own_turf_percent=float(
                (count[mask, role] / env.paint_count * 100).mean().item()
            ),
            enemy_turf_percent=float(
                (count[mask, 1 - role] / env.paint_count * 100).mean().item()
            ),
            submerged_recovery_agent_frames=float(
                damaging_heal[mask, role].sum().item()
            ),
            wounded_covered_movement_samples=float(cover[mask, role].sum().item()),
        )
    if script:
        report["defender"] = dict(
            firing_agent_decisions=float(script.fired.sum().item()),
            visible_agent_decisions=float(script.seen.sum().item()),
            damage_dealt=float(totals[:, 0, 0].sum().item() * 100),
            stamper_deaths=float(totals[:, 0, 1].sum().item()),
        )
    if record:
        clip = record.write(trace)
        clip.update(
            id="rl-stage1-" + kind + "-env" + str(trace_env),
            label="RL 阶段1 · " + kind,
            position_semantics="Trained recurrent PPO in GPU approximation; primary weapons only, not native evidence",
        )
        Path(trace).write_text(
            json.dumps(clip, separators=(",", ":"), ensure_ascii=False) + "\n"
        )
        report["trace"] = str(trace)
        report["trace_environment"] = trace_env
    report["per_game"] = dict(
        role=roles.cpu().tolist(),
        winner=winner.cpu().tolist(),
        turf=count.cpu().tolist(),
        kills=totals[:, :, 5].flip(1).cpu().tolist(),
        deaths=totals[:, :, 1].cpu().tolist(),
        first_kill_frame=first_kill.cpu().tolist(),
        submerged_recovery_agent_frames=damaging_heal.cpu().tolist(),
        wounded_covered_movement_samples=cover.cpu().tolist(),
    )
    return report


def main(a):
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("high")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    p, meta = load_policy(a.checkpoint, a.device)
    other = load_policy(a.opponent, a.device)[0] if a.opponent else None
    report = play(
        p,
        a.data,
        a.calibration,
        games=a.games,
        kind=a.kind,
        seed=a.seed,
        device=a.device,
        deterministic=not a.stochastic,
        trace=out / "trace.json" if a.trace else None,
        opponent=other,
        trace_env=a.trace_env,
    )
    report.update(
        checkpoint=str(a.checkpoint),
        training_frames=meta["frames"],
        training_update=meta["update"],
    )
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--calibration", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--opponent")
    p.add_argument("--out", required=True)
    p.add_argument("--games", type=int, default=128)
    p.add_argument("--seed", type=int, default=10001)
    p.add_argument(
        "--kind",
        choices=["random", "d4-spawn", "d4-encounter", "history"],
        default="random",
    )
    p.add_argument("--device", default="cuda")
    p.add_argument("--trace", action="store_true")
    p.add_argument("--trace-env", type=int, default=0)
    p.add_argument("--stochastic", action="store_true")
    main(p.parse_args())
