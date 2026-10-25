"""One public-observation contract for native-sync, GPU rollout and native eval."""

import math
import numpy as np
import torch
from ..bc.model import features
from ..geometry import basis
from ..env import YAW, PITCH, CHARGE, INK


def level_mask(mask):
    result = torch.zeros_like(mask, dtype=torch.bool)
    for h, size in enumerate((17, 9, 9, 2, 2, 2, 1, 1)):
        result[..., h, :size] = True
    return result


def encode(raw, validity, age, previous):
    encoded = features(raw, previous, validity)
    encoded["quality"] = torch.cat(
        [encoded["quality"], age.reshape(-1, 1).float().clamp(0, 30) / 30], -1
    )
    encoded["action_mask"] = level_mask(encoded["action_mask"])
    return encoded


def validity(raw, camera=None):
    n = raw["hud"].shape[0]
    d = raw["hud"].device
    hv = torch.ones_like(raw["hud"], dtype=torch.bool)
    hv[..., [4, 7, 8]] = False
    return dict(
        hud_valid=hv,
        screen_channel_valid=torch.ones_like(raw["screen"], dtype=torch.bool),
        minimap_valid=torch.zeros_like(raw["minimap"], dtype=torch.bool),
        native_camera_valid=torch.ones((n, 2), device=d, dtype=torch.bool)
        if camera is None
        else camera,
        projectiles_native_valid=torch.zeros((n, 2), device=d, dtype=torch.bool),
        entity_velocity_native_valid=torch.zeros((n, 2), device=d, dtype=torch.bool),
    )


class FloorSensor:
    def __init__(self, path, device="cpu"):
        with np.load(path) as z:
            self.a = {k: torch.as_tensor(z[k].copy(), device=device) for k in z.files}
        self.shape = self.a["top"].shape
        self.height = self.a["points"][self.a["top"].clamp_min(0).long(), 1]

    def screen_cells(self, raw, state, cfg, camera_override=None):
        fwd, right, up = basis(
            state[..., YAW], state[..., PITCH] + cfg.camera_pitch_offset_radians
        )
        camera = (
            state[..., :3]
            + torch.tensor([0.0, cfg.camera_target_height, 0.0], device=state.device)
            - fwd * cfg.camera_distance
        )
        camera += (
            torch.stack(
                [
                    state[..., YAW].sin(),
                    torch.zeros_like(state[..., YAW]),
                    state[..., YAW].cos(),
                ],
                -1,
            )
            * cfg.camera_target_forward
        )
        if camera_override is not None:
            camera, fwd, right, up = camera_override
        xs = torch.linspace(-1, 1, 32, device=state.device) * math.tan(
            math.radians(cfg.camera_horizontal_fov_degrees / 2)
        )
        ys = torch.linspace(1, -1, 18, device=state.device) * math.tan(
            math.radians(cfg.camera_vertical_fov_degrees / 2)
        )
        yy, xx = torch.meshgrid(ys, xs, indexing="ij")
        direction = (
            fwd[:, :, None, None]
            + xx[None, None, :, :, None] * right[:, :, None, None]
            + yy[None, None, :, :, None] * up[:, :, None, None]
        )
        direction = direction / direction.norm(dim=-1, keepdim=True).clamp_min(1e-8)
        hit = camera[:, :, None, None] + direction * raw["screen"][..., 0, None]
        xz = torch.round(hit[..., [0, 2]] - self.a["grid_origin"]).long()
        x, z = xz.unbind(-1)
        inside = (x >= 0) & (x < self.shape[0]) & (z >= 0) & (z < self.shape[1])
        x = x.clamp(0, self.shape[0] - 1)
        z = z.clamp(0, self.shape[1] - 1)
        good = (
            inside
            & (raw["screen"][..., 1] == 1)
            & ((hit[..., 1] - self.height[x, z]).abs() <= 0.65)
        )
        return x * self.shape[1] + z, good

    def overlay(self, raw, state, cfg, color, valid_map, age, camera_override=None):
        """color/map [N,2,X,Z] is a causal *past* snapshot, not current ink."""
        v = validity(raw)
        v["minimap_valid"] = valid_map
        raw["minimap"] = torch.where(valid_map, color, 0).to(torch.uint8)
        cell, good = self.screen_cells(raw, state, cfg, camera_override)
        flat = color.flatten(-2)
        mask = valid_map.flatten(-2)
        labels = flat.gather(-1, cell.flatten(-2)).reshape_as(cell)
        good &= mask.gather(-1, cell.flatten(-2)).reshape_as(cell)
        # screen stores global team IDs; minimap stores own=1/enemy=2.
        role = torch.arange(2, device=state.device)[None, :, None, None]
        global_color = torch.where(
            labels == 1, role, torch.where(labels == 2, 1 - role, -1)
        )
        raw["screen"][..., 2] = torch.where(good, global_color, -1)
        v["screen_channel_valid"][..., 2] = good
        raw["entity_mask"] &= raw["entities"][..., 3] == 1
        return v


class GPUInk(FloorSensor):
    def __init__(self, path, env, mask_bank):
        super().__init__(path, env.device)
        self.env = env
        with np.load(mask_bank) as z:
            self.bank = torch.as_tensor(
                np.unpackbits(z["packed"], axis=1, count=int(z["cells"]))
                .reshape(-1, *self.shape)
                .astype(bool),
                device=env.device,
            )
        self.past = env.paint.clone()
        self.pending = env.paint.clone()
        self.frame = -1

    def observe(self, raw):
        e = self.env
        # Native Saber reserves visible ink while charging (A6 E0 cost curve),
        # whereas GPU physics debits it once on release. Reconstruct HUD display
        # only; do not change tank state, costs, recovery, damage or shot timing.
        native_charge = (e.state[:, 0, CHARGE] * 20 / 21).clamp(0, 20)
        reserved = torch.where(
            native_charge <= 5,
            native_charge * 0.007,
            0.035 + (native_charge - 5) * (0.082 / 15),
        )
        raw["hud"][:, 0, 0] = (e.state[:, 0, INK] - reserved).clamp_min(0)
        f = int(e.steps[0])
        # Decision=2 divides30. Capture tick30 only becomes visible at tick32.
        if self.frame >= 0 and self.frame % 30 == 0 and f > self.frame:
            self.past.copy_(self.pending)
        if f % 30 == 0:
            self.pending.copy_(e.paint)
        self.frame = f
        stamp = max(0, (f - 1) // 30)
        age = torch.full((e.n, 2), (f - 1) % 30 if f > 0 else 30, device=e.device)
        ids = (torch.arange(e.n, device=e.device) * 73 + stamp) % len(self.bank)
        valid = (
            (self.bank[ids] & self.a["map_valid"])[..., None, :, :]
            .expand(-1, 2, -1, -1)
            .clone()
        )
        if f == 0:
            valid.zero_()
        top = self.a["top"].clamp_min(0).long()
        color = self.past[:, top][:, None]
        roles = torch.arange(2, device=e.device)[None, :, None, None]
        color = torch.where(color == roles, 1, torch.where(color >= 0, 2, 0)).to(
            torch.uint8
        )
        v = self.overlay(raw, e.state, e.cfg, color, valid, age)
        return raw, v, age
