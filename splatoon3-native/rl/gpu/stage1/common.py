"""Stage1 configuration, role-balanced evaluation and private checkpoint I/O."""

import json, math, hashlib, os
from pathlib import Path
import torch
from ..contract import Config
from ..env import ParallelEnv
from ..cuda_graph import GraphEnv


def configuration(calibration):
    raw = json.loads(Path(calibration).read_text())
    cfg = dict(raw["config"])
    cfg["loadout_mode"] = "primary_only"
    # User-approved assumption, kept separate from native projection evidence.
    cfg["camera_vertical_fov_degrees"] = 55.0
    cfg["camera_horizontal_fov_degrees"] = math.degrees(
        2 * math.atan(math.tan(math.radians(55 / 2)) * 16 / 9)
    )
    return Config(**cfg), raw


def environment(data, calibration, n, device="cuda", compiled=True):
    cfg, _ = configuration(calibration)
    env = ParallelEnv(
        data,
        cfg,
        n_envs=n,
        device=device,
        compile=compiled,
        fast_rays=str(device).startswith("cuda"),
    )
    return GraphEnv(env) if str(device).startswith("cuda") else env


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checkpoint(path, policy, optimizer, *, update, frames, config, league=None):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    payload = dict(
        schema="inklab.rl.stage1.checkpoint.v1",
        policy=policy.state_dict(),
        optimizer=optimizer.state_dict() if optimizer else None,
        update=update,
        frames=frames,
        hidden_size=policy.hidden_size,
        config=config,
        torch_rng=torch.get_rng_state(),
        cuda_rng=torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
        league=None if league is None else league.snapshots,
    )
    temporary = path.with_suffix(".partial")
    torch.save(payload, temporary)
    os.replace(temporary, path)
    path.with_suffix(".json").write_text(
        json.dumps(
            dict(
                schema=payload["schema"],
                update=update,
                frames=frames,
                sha256=digest(path),
                bytes=path.stat().st_size,
                config=config,
            ),
            indent=2,
        )
        + "\n"
    )


def load_policy(path, device="cuda"):
    from .policy import Policy

    # Only owned private checkpoints produced by this project are accepted inputs.
    raw = torch.load(path, map_location="cpu", weights_only=False)
    if raw.get("schema") != "inklab.rl.stage1.checkpoint.v1":
        raise ValueError("checkpoint schema")
    p = Policy(
        raw["hidden_size"],
        action_feedback=raw.get("config", {}).get("action_feedback", False),
        control_prior=raw.get("config", {}).get("control_prior", False),
        button_semantics=raw.get("config", {}).get("button_semantics", "level"),
    ).to(device)
    p.load_state_dict(raw["policy"])
    p.eval()
    return p, raw


def wilson(wins, total, z=1.959963984540054):
    if not total:
        return [0.0, 1.0]
    p = wins / total
    den = 1 + z * z / total
    center = (p + z * z / (2 * total)) / den
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / den
    return [max(0.0, center - radius), min(1.0, center + radius)]


def elo(rating, opponent, score, k=24):
    return rating + k * (score - 1 / (1 + 10 ** ((opponent - rating) / 400)))


class CSV:
    def __init__(self, path):
        import csv

        self.path = Path(path)
        self.file = self.path.open("x", buffering=1)
        self.csv = csv
        self.writer = None

    def write(self, row):
        if self.writer is None:
            self.writer = self.csv.DictWriter(self.file, fieldnames=list(row))
            self.writer.writeheader()
        self.writer.writerow(row)
        self.file.flush()

    def close(self):
        self.file.close()
