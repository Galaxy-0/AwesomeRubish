"""Freeze .52 for stable attribution; easy -> D4 -> mixed frozen history."""

import math
import torch
from ..stage1.opponents import neutral, D4Defender
from ..stage1.common import load_policy
from ..stage1.policy import prepare
from ..stage1.controller import physical
from ..contract import Config, camera_levels
from ..env import HP, INK


class Opponent:
    def __init__(self, env, kind="easy", history=None):
        self.env, self.kind = env, kind
        self.reference = D4Defender(env)
        self.reaction = torch.zeros(env.n, device=env.device)
        self.history = load_policy(history, env.device)[0] if history else None
        self.hidden = (
            self.history.initial(env.n * 2, env.device) if self.history else None
        )
        self.previous = neutral(env.n, env.device)

    @torch.no_grad()
    def actions(self, ordinary):
        e = self.env
        if self.kind == "script":
            return self.reference.actions()
        if self.kind == "history":
            if self.history is None:
                raise ValueError("frozen history required")
            action, _, _, self.hidden = self.history.act(
                prepare(ordinary, self.previous, self.history.button_semantics),
                self.hidden,
            )
            old = physical(
                action.reshape(e.n, 2, 8), self.previous, self.history.button_semantics
            )
            # Preserve the old policy's angular rates rather than silently using
            # its legacy bins under the new native_plus5 physics codebook.
            legacy = torch.tensor(
                camera_levels(Config(camera_codebook="legacy")),
                device=e.device,
            )
            current = torch.tensor(camera_levels(e.cfg), device=e.device)
            for h in (1, 2):
                desired = legacy[old[..., h]]
                old[..., h] = (desired[..., None] - current).abs().argmin(-1)
            reference = self.reference.actions()
            # Stage3: 75% strong fixed script,25% historical (not symmetric SP).
            rows = torch.arange(e.n, device=e.device) % 4 == 0
            reference[rows, 1] = old[rows, 1]
            self.previous = old
            return reference
        if self.kind != "easy":
            raise ValueError("unknown opponent")
        # Easy is delayed, limited-rate and only uses public visibility. It has
        # no pose writes, in contrast to the unchanged D4 acceptance reference.
        mask = ordinary["entity_mask"][:, 1]
        ents = ordinary["entities"][:, 1]
        visible = (mask & (ents[..., 3] == 1)).any(-1)
        self.reaction = torch.where(visible, self.reaction + e.cfg.decision_frames, 0.0)
        chosen = (mask & (ents[..., 3] == 1)).long().argmax(-1)
        target = ents.gather(1, chosen[:, None, None].expand(-1, 1, 7)).squeeze(1)
        yaw_error = torch.atan(
            target[:, 0]
            * math.tan(math.radians(e.cfg.camera_horizontal_fov_degrees / 2))
        )
        pitch_error = torch.atan(
            target[:, 1] * math.tan(math.radians(e.cfg.camera_vertical_fov_degrees / 2))
        )
        # Convert desired rate into ordinary camera levels with bounded speed.
        maximum = e.cfg.stick_plus5_radians_per_frame + e.cfg.gyro_max_radians_per_frame
        levels = torch.tensor(camera_levels(e.cfg), device=e.device)
        a = neutral(e.n, e.device)
        for h, error in [(1, yaw_error), (2, pitch_error)]:
            desired = error.clamp(-0.06, 0.06) / (maximum * e.cfg.decision_frames)
            a[:, 1, h] = (desired[:, None] - levels).abs().argmin(-1)
        a[:, 1, 3] = (
            visible
            & (self.reaction >= 24)
            & (target[:, 2] <= 13.4)
            & (e.state[:, 1, INK] > 0.04)
            & (e.state[:, 1, HP] > 0)
        ).long()
        a[:, 1, 4] = ((e.state[:, 1, INK] < 0.15) & ~visible).long()
        return a
