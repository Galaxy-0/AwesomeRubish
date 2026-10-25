"""Full180s, normal spawns, no guidance; immutable private trace and metrics."""

import json
import time
from pathlib import Path
import torch
from ..env import EVENT_SIZE, PITCH
from ..stage1.combat_metrics import CombatMeter
from ..stage1.common import wilson
from ..record import Recorder
from .rollout import Match


@torch.no_grad()
def evaluate(a, model, out, seed, kind="script", deterministic=False, match=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    original = model.training
    model.eval()
    # Isolate evaluation RNG from on-policy training.
    saved = torch.get_rng_state()
    cuda = torch.cuda.get_rng_state_all() if a.device.startswith("cuda") else None
    torch.manual_seed(seed)
    m = match or Match(a, a.eval_envs)
    m.reset(seed, kind, near=0.0, history=a.history[0] if kind == "history" else None)
    e = m.env
    e.set_auxiliary_scale(0.0)
    hidden = model.initial(e.n, e.device)
    total = torch.zeros(e.n, 2, EVENT_SIZE, device=e.device)
    meter = CombatMeter(e.n, e.device)
    recorder = Recorder(e, stride=12)
    visible = 0.0
    clamped = 0.0
    wall = time.perf_counter()
    while True:
        obs = m.observation()
        actions, _, _, hidden = model.act(obs, hidden, deterministic)
        _, done, info, diag = m.step(actions)
        total += info["events"]
        meter.capture(e, diag["physical"], info)
        recorder.capture(diag["physical"], info)
        visible += float(diag["visible"].sum())
        clamped += float((e.state[:, 0, PITCH].abs() >= 1.099).sum())
        if bool(done.all()):
            break
        if m.tick > 5401:
            raise RuntimeError("180s did not terminate")
    counts = info["turf_counts"]
    wins = int((counts[:, 0] > counts[:, 1]).sum())
    kills = total[:, 1, 5]
    combat = meter.report()["stamper"]
    report = dict(
        schema="inklab.bcppo.eval.v1",
        seed=seed,
        opponent=kind,
        greedy=deterministic,
        games=e.n,
        frames=int(e.steps.max()),
        normal_spawns=True,
        guidance=False,
        wins=wins,
        win_rate=wins / e.n,
        win_rate_ci95=wilson(wins, e.n),
        mean_weapon_kills=float(kills.mean()),
        weapon_kills=float(kills.sum()),
        mean_deaths=float(total[:, 0, 1].mean()),
        enemy_weapon_kills=float(total[:, 0, 5].sum()),
        mean_damage=float(total[:, 1, 0].sum() * 100 / e.n),
        mean_turf_percent=float((counts[:, 0] / e.paint_count * 100).mean()),
        enemy_turf_percent=float((counts[:, 1] / e.paint_count * 100).mean()),
        visible_fraction=visible / (m.tick * e.n),
        pitch_clamped_fraction=clamped / (m.tick * e.n),
        combat=combat,
        seconds=time.perf_counter() - wall,
        passed=wins / e.n >= 0.7 and float(kills.mean()) >= 2,
        per_game=dict(
            kills=kills.cpu().tolist(),
            deaths=total[:, 0, 1].cpu().tolist(),
            turf=(counts[:, 0] / e.paint_count * 100).cpu().tolist(),
        ),
    )
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    trace = recorder.write(out / "trace.json")
    trace.update(
        label="BC warm-start PPO · GPU · " + kind,
        position_semantics="approximate GPU, normal spawn180s; not native evidence",
    )
    (out / "trace.json").write_text(json.dumps(trace, separators=(",", ":")) + "\n")
    model.train(original)
    torch.set_rng_state(saved)
    if cuda is not None:
        torch.cuda.set_rng_state_all(cuda)
    return report, m
