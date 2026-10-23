"""Torch port of S1's independently measured launch/respawn model.

ARM was reserved/unused in stage0. With native_launcher enabled only, it holds
launch age: -1 ordinary, -2 waiting for a fresh ZR after death. FX/FZ retain the
finite launch steering offset until ordinary motion takes over. No native state
is imported after initialization; all coefficients come from the existing S1
mechanism probe, not from the replay trajectory under evaluation.
"""

import torch


class LaunchModel:
    def __init__(self, model, device):
        self.model = model
        self.row = model["stages"]["1"]
        knots = torch.tensor(self.row["knots"], device=device)
        times = torch.arange(self.row["end_frame"] + 1, device=device)
        index = (
            torch.searchsorted(knots[:, 0].contiguous(), times, right=True)
            .sub(1)
            .clamp(0, len(knots) - 2)
        )
        alpha = (
            (times - knots[index, 0]) / (knots[index + 1, 0] - knots[index, 0])
        ).clamp(0, 1)
        self.path = knots[index, 1:] + alpha[:, None] * (
            knots[index + 1, 1:] - knots[index, 1:]
        )
        self.side = torch.tensor([[1.0, 1.0, 1.0], [-1.0, 1.0, -1.0]], device=device)
        self.yaw = torch.tensor([torch.pi, 0.0], device=device)
        self.ready = model["respawn"]["ready_delay"]
        self.unlock = model["respawn"]["unlock_delay"]

    def apply(self, s, t, a, died):
        from .env import (
            ARM,
            RESPAWN,
            HP,
            INK,
            YAW,
            PITCH,
            HEADING,
            GROUND,
            VX,
            VY,
            VZ,
            PROTECTED,
            PREV_ZR,
            CHARGE,
            COOL,
            RECOVER,
            EMERGE,
            HURT,
            CREDIT,
        )

        waiting = (s[..., ARM] == -2) | died
        remaining = torch.where(
            died, float(self.unlock), (s[..., RESPAWN] - 1).clamp_min(0)
        )
        t[..., RESPAWN] = torch.where(waiting, remaining, t[..., RESPAWN])
        ready = waiting & (remaining <= self.unlock - self.ready)
        launch = waiting & (remaining == 0) & (a[..., 3] > 0) & (s[..., PREV_ZR] == 0)
        age = torch.where(launch, 0.0, torch.where(waiting, -2.0, s[..., ARM]))
        t[..., HP] = torch.where(ready, 1.0, t[..., HP])
        t[..., INK] = torch.where(ready, 1.0, t[..., INK])
        t[..., :3] = torch.where(ready[..., None], self.path[0] * self.side, t[..., :3])
        for slot in (VX, VY, VZ):
            t[..., slot] = torch.where(ready, 0.0, t[..., slot])
        for slot in (PITCH, CHARGE, COOL, RECOVER, EMERGE):
            t[..., slot] = torch.where(ready, 0.0, t[..., slot])
        default_yaw = self.yaw
        t[..., YAW] = torch.where(ready, default_yaw, t[..., YAW])
        t[..., HEADING] = torch.where(ready, default_yaw, t[..., HEADING])
        t[..., GROUND] = torch.where(ready, 0.0, t[..., GROUND])
        t[..., PROTECTED] = torch.where(launch, 180.0, t[..., PROTECTED])
        t[..., CREDIT] = torch.where(launch, 0.0, t[..., CREDIT])
        t[..., HURT] = torch.where(ready, 10000.0, t[..., HURT])
        active = (age >= 0) & (age <= self.row["end_frame"])
        return age, active, launch

    def motion(self, s, t, age, active, launch, move):
        from .env import (
            ARM,
            FX,
            FZ,
            YAW,
            GROUND,
            SQUID,
            SUB,
            CHARGE,
            COOL,
            DELAY,
            CONTACT,
            VX,
            VY,
            VZ,
        )

        mag = move.norm(dim=-1).clamp_max(1)
        local = move * mag.pow(3)[..., None]
        yaw = t[..., YAW]
        steer = (
            torch.stack(
                [
                    -local[..., 0] * yaw.cos() + local[..., 1] * yaw.sin(),
                    local[..., 0] * yaw.sin() + local[..., 1] * yaw.cos(),
                ],
                -1,
            )
            * self.model["steer_speed"]
        )
        offset = torch.stack([s[..., FX], s[..., FZ]], -1)
        offset = torch.where(launch[..., None], 0.0, offset)
        offset += steer * (age > self.model["steer_start"])[..., None]
        pos = self.path[age.long().clamp(0, self.row["end_frame"])] * self.side
        pos = pos.clone()
        pos[..., 0] += offset[..., 0]
        pos[..., 2] += offset[..., 1]
        t[..., :3] = torch.where(active[..., None], pos, t[..., :3])
        velocity = pos - s[..., :3]
        for axis, slot in enumerate((VX, VY, VZ)):
            t[..., slot] = torch.where(active, velocity[..., axis], t[..., slot])
        t[..., FX] = torch.where(active, offset[..., 0], t[..., FX])
        t[..., FZ] = torch.where(active, offset[..., 1], t[..., FZ])
        t[..., GROUND] = torch.where(
            active, (age >= self.row["ground_frame"]).float(), t[..., GROUND]
        )
        t[..., SQUID] = torch.where(
            active,
            ((age >= self.row["squid_start"]) & (age < self.row["squid_end"])).float(),
            t[..., SQUID],
        )
        for slot in (SUB, CHARGE, COOL, DELAY, CONTACT):
            t[..., slot] = torch.where(active, 0.0, t[..., slot])
        next_age = torch.where(age >= self.row["end_frame"], -1.0, age + 1)
        t[..., ARM] = torch.where(active, next_age, age)
