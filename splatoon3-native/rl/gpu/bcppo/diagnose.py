"""Six-hour stop diagnostics: observed motion/visibility plus numeric controls."""

import json
import os
import subprocess
import sys
from pathlib import Path
import torch
from ..env import HP, INK, PITCH, GROUND, ARM


def run(a, match, out, status):
    e = match.env
    s = e.state
    obs = match.raw
    # Referee summaries stay outside the actor observation.
    delta = s[:, 1, :3] - s[:, 0, :3]
    length = delta.norm(dim=-1)
    start = s[:, 0, :3] + torch.tensor([0.0, 1.1, 0.0], device=e.device)
    end = s[:, 1, :3] + torch.tensor([0.0, 1.1, 0.0], device=e.device)
    d = end - start
    obstruction, _, _ = e.geo.ray(
        start, d / d.norm(dim=-1, keepdim=True).clamp_min(1e-6), 64.0, 0.5
    )
    summary = dict(
        last_train_distance_mean=float(length.mean()),
        last_train_distance_under22_fraction=float((length < 22).float().mean()),
        last_train_geometric_los_fraction=float(
            (obstruction >= length - 0.1).float().mean()
        ),
        last_train_public_enemy_fraction=float(
            obs["entity_mask"][:, 0].any(-1).float().mean()
        ),
        last_train_pitch_clamped_fraction=float(
            (s[:, 0, PITCH].abs() >= 1.099).float().mean()
        ),
        last_train_alive_fraction=float((s[:, 0, HP] > 0).float().mean()),
        last_train_ground_fraction=float(s[:, 0, GROUND].mean()),
        last_train_launcher_fraction=float((s[:, 0, ARM] >= 0).float().mean()),
        last_train_ink_mean=float(s[:, 0, INK].mean()),
    )
    # Existing synthetic parameter controls exercise actual simulator damage and
    # collision code, rather than inferring hit correctness from finite losses.
    env = os.environ.copy()
    env["RL_STAGE0_DATA"] = str(Path(a.data).resolve())
    try:
        p = subprocess.run(
            [sys.executable, "-m", "unittest", "gpu.test_env", "-q"],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        (Path(out) / "diagnosis-numeric-controls.log").write_text(p.stdout + p.stderr)
        controls = dict(returncode=p.returncode, passed=p.returncode == 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        controls = dict(passed=False, error=repr(exc))
    report = dict(
        reason="six_hour_zero_formal_damage",
        last_training=status,
        referee_summary=summary,
        numeric_controls=controls,
        limitations="single last training-state summary, not a causal proof; inspect normal-spawn eval traces and pitch/visibility curves next",
        next_checks=[
            "camera sign/gain and aim-to-projectile direction",
            "ray/entity visibility versus referee LOS and opponent submerging",
            "terrain support/route traps vs normal-spawn reachability",
            "positive flat controls vs map contact/wave clipping",
        ],
    )
    (Path(out) / "diagnosis.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
