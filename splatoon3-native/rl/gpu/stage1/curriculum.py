"""Explicit early encounter starts; full spawn/180s held-out gates stay separate.

This changes initial poses only, never actions, physics, damage or rewards.
It fades to100% normal spawns with the auxiliary reward window(first30%).
"""

import math
import torch
from ..env import YAW, HEADING, GROUND


@torch.no_grad()
def encounter_starts(env, fraction, seed):
    if fraction <= 0:
        return 0
    # These three ordinary representative positions precede this training run.
    # Nearest1u standing cells are chosen, pairs require native-derived field LOS.
    generator = torch.Generator(device=env.device).manual_seed(seed)
    points = env.geo.points
    centers = torch.tensor(
        [[0.0, 3.0, 0.0], [-18.0, 3.0, 0.0], [0.0, 3.0, -12.0]], device=env.device
    )
    d = torch.cdist(centers, points)
    closest = d.argmin(-1)
    centers = points[closest]
    count = min(env.n, int(env.n * fraction))
    rows = torch.arange(count, device=env.device)
    center = centers[rows % 3]
    angle = torch.rand(count, device=env.device, generator=generator) * (2 * math.pi)
    radius = 6 + torch.rand(count, device=env.device, generator=generator) * 7
    wish = center + torch.stack(
        [angle.sin() * radius, torch.zeros_like(radius), angle.cos() * radius], -1
    )
    choices = torch.cdist(wish, points).argmin(-1)
    pose = points[choices]
    valid = (pose[:, 1] - center[:, 1]).abs() < 0.5
    start = center + torch.tensor([0.0, 1.0, 0.0], device=env.device)
    end = pose + torch.tensor([0.0, 1.0, 0.0], device=env.device)
    direction = end - start
    length = direction.norm(dim=-1)
    blocked, _, _ = env.geo.ray(
        start, direction / length[:, None].clamp_min(1e-6), 24.0, 0.5
    )
    valid &= (length >= 6) & (length <= 18) & (blocked >= length - 0.1)
    row = rows[valid]
    center = center[valid]
    pose = pose[valid]
    env.state[row, 0, :3] = pose
    env.state[row, 1, :3] = center
    yaw = (
        torch.rand((len(row), 2), device=env.device, generator=generator) * 2 * math.pi
        - math.pi
    )
    env.state[row, :, YAW] = yaw
    env.state[row, :, HEADING] = yaw
    env.state[row, :, GROUND] = 1
    return len(row)
