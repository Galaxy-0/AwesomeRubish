"""Privileged reward bookkeeping, never actor inputs. All guidance is bounded."""

import torch
from ..env import HP, YAW, PITCH


def schedule(elapsed, budget=86400):
    fraction = min(1.0, max(0.0, elapsed / budget))
    fade = max(0.0, 1 - fraction / 0.25)
    return dict(
        auxiliary=fade,
        bc_kl=fade,
        entropy=0.01 - 0.005 * fraction,
        extra_zr_entropy=0.005,
        near_fraction=0.5 * fade,
    )


class Guidance:
    """Signed zero-sum addition; positive budgets persist across reacquisition.

    Last-seen position is updated ONLY when public enemy_mask is true. Reward
    uses privileged pose to evaluate improvement toward that last observed point.
    Death resets life budgets but not match budgets, preventing respawn farming.
    """

    def __init__(self, n, device, memory_frames=90):
        self.n, self.device, self.memory_frames = n, device, memory_frames
        self.reset()

    def reset(self):
        self.last = torch.zeros(self.n, 3, device=self.device)
        self.age = torch.full((self.n,), self.memory_frames + 1, device=self.device)
        self.life = torch.zeros(self.n, 3, device=self.device)
        self.match = torch.zeros_like(self.life)
        self.life_cap = torch.tensor([0.30, 0.10, 0.10], device=self.device)
        self.match_cap = torch.tensor([0.80, 0.30, 0.30], device=self.device)

    @staticmethod
    def error(state, target):
        origin = state[:, :3] + torch.tensor([0.0, 2.2, 0.0], device=state.device)
        d = target - origin
        yaw = torch.atan2(d[:, 0], d[:, 2])
        pitch = torch.atan2(d[:, 1], d[:, [0, 2]].norm(dim=-1))
        dy = torch.atan2((yaw - state[:, YAW]).sin(), (yaw - state[:, YAW]).cos())
        return (dy.square() + (pitch - state[:, PITCH]).square()).sqrt(), d.norm(dim=-1)

    @torch.no_grad()
    def step(self, before, after, visible, events, df=2):
        self.age += df
        self.last = torch.where(
            visible[:, None],
            before[:, 1, :3] + torch.tensor([0.0, 1.1, 0.0], device=self.device),
            self.last,
        )
        self.age = torch.where(visible, 0.0, self.age)
        live = (before[:, 0, HP] > 0) & (after[:, 0, HP] > 0)
        eligible = (self.age <= self.memory_frames) & live
        old_angle, old_dist = self.error(before[:, 0], self.last)
        angle, dist = self.error(after[:, 0], self.last)
        amounts = (
            torch.stack(
                [
                    0.003 * (old_dist - dist).clamp(0, 0.5),
                    0.03 * (old_angle - angle).clamp(0, 0.2),
                    0.01 * events[:, 0, 2] * visible * (angle < 0.12) * (dist <= 22),
                ],
                -1,
            )
            * eligible[:, None]
        )
        amounts = torch.minimum(amounts, (self.life_cap - self.life).clamp_min(0))
        amounts = torch.minimum(amounts, (self.match_cap - self.match).clamp_min(0))
        self.life += amounts
        self.match += amounts
        self.life = torch.where((after[:, 0, HP] <= 0)[:, None], 0.0, self.life)
        return amounts.sum(-1), amounts
