"""Stage1 GRU actor plus explicit observation-quality encoding.

Unknown channels are zeroed before encoding and accompanied by validity masks.
This is a Stamper-only actor: the .52 head/embedding is NOT trained by BC.
"""

import torch
from torch import nn
from torch.nn import functional as F
from ..stage1.policy import Policy, prepare


class BCPolicy(Policy):
    def __init__(self, hidden=384):
        super().__init__(hidden, action_feedback=True, button_semantics="toggle")
        self.quality = nn.Sequential(
            nn.Linear(445, 128), nn.SiLU(), nn.Linear(128, hidden)
        )

    def encode(self, obs):
        return super().encode(obs) + self.quality(obs["quality"].float())


def features(raw, previous, validity=None):
    """Raw [B,2,...] public obs -> prepared actor obs, including unknown masks.

    GPU deployment deliberately shares the recording's conservative contract:
    weapon-stage/turf HUD and projectile/velocity channels stay unavailable.
    No referee position is added. Map/ray ink is retained only where valid.
    """
    obs = {k: v.clone() for k, v in raw.items()}
    n = obs["hud"].shape[0]
    device = obs["hud"].device
    if validity is None:
        hv = torch.ones_like(obs["hud"], dtype=torch.bool)
        hv[..., [4, 7, 8]] = False
        sv = torch.ones_like(obs["screen"], dtype=torch.bool)
        sv[..., 2] = False
        mv = torch.zeros_like(obs["minimap"], dtype=torch.bool)
        vel = torch.zeros((n, 2), device=device, dtype=torch.bool)
        projectile = vel.clone()
        camera = ~vel
        # Native corpus lacks a qualified primary projectile active set.
        obs["entity_mask"] &= obs["entities"][..., 3] == 1
    else:
        hv = validity["hud_valid"].bool()
        sv = validity["screen_channel_valid"].bool()
        mv = validity["minimap_valid"].bool()
        vel = validity["entity_velocity_native_valid"].bool()
        projectile = validity["projectiles_native_valid"].bool()
        camera = validity["native_camera_valid"].bool()
    obs["hud"] *= hv
    obs["screen"][..., 0] *= sv[..., 0]
    obs["screen"][..., 1] *= sv[..., 1]
    obs["screen"][..., 2] = torch.where(sv[..., 2], obs["screen"][..., 2], -1)
    obs["screen"][..., 3] *= sv[..., 3]
    obs["entities"][..., 4:] *= vel[..., None, None]
    obs["minimap"] = torch.where(mv, obs["minimap"], 0)
    out = prepare(obs, previous, "toggle")
    # Reassert invalid channels after categorical/normalizing transforms.
    out["screen"][:, 1:5] *= sv[..., 1].reshape(n * 2, 1, 18, 32)
    out["quality"] = torch.cat(
        [
            hv.reshape(n * 2, 10).float(),
            F.adaptive_avg_pool2d(
                sv.reshape(n * 2, 18, 32, 4).permute(0, 3, 1, 2).float(), (3, 4)
            ).flatten(1),
            F.adaptive_avg_pool2d(
                mv.reshape(n * 2, 1, *mv.shape[-2:]).float(), (16, 24)
            ).flatten(1),
            torch.stack([vel, projectile, camera], -1).reshape(n * 2, 3).float(),
        ],
        -1,
    )
    return out


def load(path, device="cuda"):
    raw = torch.load(path, map_location="cpu", weights_only=False)
    if raw.get("schema") != "inklab.rl.bc.checkpoint.v1":
        raise ValueError("not an owned BC checkpoint")
    model = BCPolicy(raw["hidden_size"]).to(device)
    model.load_state_dict(raw["policy"])
    return model.eval(), raw
