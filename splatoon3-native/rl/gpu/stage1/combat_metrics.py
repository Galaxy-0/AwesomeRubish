"""Referee-side diagnostics only; none of these fields enter actor observations."""

import torch
from ..env import FULL, SUB


class CombatMeter:
    def __init__(self, n, device):
        self.seconds = 0.0
        self.values = {
            k: torch.zeros((n, 2), device=device)
            for k in (
                "attacks",
                "full_releases",
                "hit_decisions",
                "weapon_kos",
                "zl_frames",
                "submerged_frames",
            )
        }
        self.streak = torch.zeros((n, 2), device=device)
        self.longest = self.streak.clone()

    def capture(self, env, physical, info, done=None):
        df = env.cfg.decision_frames
        self.seconds += df / 60
        ev = info["events"]
        self.values["attacks"] += ev[..., 2]
        self.values["full_releases"][:, 0] += ev[:, 0, 2] * (env.state[:, 0, FULL] > 0)
        self.values["hit_decisions"] += (ev[..., 0] > 0).flip(1)
        self.values["weapon_kos"] += ev[..., 5].flip(1)
        self.values["zl_frames"] += physical[..., 4] * df
        self.values["submerged_frames"] += env.state[..., SUB] * df
        self.streak = torch.where(physical[..., 4] > 0, self.streak + df, 0.0)
        self.longest = torch.maximum(self.longest, self.streak)
        if done is not None:
            self.streak[done] = 0

    def report(self, mask=None):
        result = {}
        for i, role in enumerate(("stamper", "52")):
            rows = (
                torch.ones(
                    self.streak.shape[0], dtype=torch.bool, device=self.streak.device
                )
                if mask is None
                else mask[:, i]
            )
            n = int(rows.sum().item())
            if not n:
                continue
            row = {k: float(v[rows, i].sum().item()) for k, v in self.values.items()}
            row.update(
                {
                    k + "_per_minute": row[k] / max(1e-6, n * self.seconds / 60)
                    for k in ("attacks", "full_releases", "hit_decisions", "weapon_kos")
                }
            )
            row["zl_fraction"] = row["zl_frames"] / max(1, n * self.seconds * 60)
            row["longest_zl_frames"] = float(self.longest[rows, i].max().item())
            row["environments"] = n
            result[role] = row
        return result
