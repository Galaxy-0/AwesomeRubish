"""Shared visible-observation actor/critic with weapon embedding and GRU memory."""

import torch
from torch import nn
from torch.nn import functional as F


def prepare(obs):
    """GPU-only visible feature encoding. No referee position/HP of opponents."""
    n = obs["hud"].shape[0]
    role = torch.arange(2, device=obs["hud"].device)[None, :, None, None]
    screen = obs["screen"]
    color = screen[..., 2]
    kind = screen[..., 1].long().clamp(0, 3)
    features = (
        torch.cat(
            [
                screen[..., :1].clamp(0, 64) / 64,
                F.one_hot(kind, 4).float(),
                (color == role).float()[..., None],
                ((color >= 0) & (color != role)).float()[..., None],
                screen[..., 3:4],
            ],
            -1,
        )
        .reshape(n * 2, 18, 32, 8)
        .permute(0, 3, 1, 2)
    )
    ent = obs["entities"].reshape(n * 2, 16, 7).clone()
    ent[..., :2] = ent[..., :2].clamp(-1, 1)
    ent[..., 2] = ent[..., 2].clamp(0, 64) / 64
    ent[..., 3] /= 5
    ent[..., 4:] = (ent[..., 4:] / 3.06).clamp(-2, 2)
    hud = obs["hud"].reshape(n * 2, -1).clone()
    hud[:, 5] /= 5
    hud[:, 6] /= 180
    # Global turf ratio order is converted to own/opponent order, never position.
    ratios = hud[:, 7:9].reshape(n, 2, 2)
    hud[:, 7:9] = torch.stack([ratios[:, 0], ratios[:, 1].flip(-1)], 1).reshape(
        n * 2, 2
    )
    ink = obs["minimap"].reshape(n * 2, 1, *obs["minimap"].shape[-2:])
    mini = F.adaptive_avg_pool2d(
        torch.cat([(ink == 1).float(), (ink == 2).float()], 1), (16, 24)
    )
    return dict(
        screen=features,
        entities=ent,
        entity_mask=obs["entity_mask"].reshape(n * 2, 16),
        hud=hud,
        minimap=mini,
        weapon=torch.arange(2, device=hud.device).repeat(n),
        action_mask=obs["action_mask"].reshape(n * 2, 8, 17),
    )


class Policy(nn.Module):
    def __init__(self, hidden=384, hud_size=10):
        super().__init__()
        self.hidden_size = hidden
        self.screen = nn.Sequential(
            nn.Conv2d(8, 32, 3, 2, 1),
            nn.SiLU(),
            nn.Conv2d(32, 64, 3, 2, 1),
            nn.SiLU(),
            nn.Conv2d(64, 64, 3, 2, 1),
            nn.SiLU(),
            nn.Flatten(),
            nn.Linear(64 * 3 * 4, 128),
            nn.SiLU(),
        )
        self.entity = nn.Sequential(
            nn.Linear(7, 128), nn.SiLU(), nn.Linear(128, 128), nn.SiLU()
        )
        self.entity_pool = nn.Sequential(nn.Linear(256, 128), nn.SiLU())
        self.hud = nn.Sequential(nn.Linear(hud_size, 128), nn.SiLU())
        self.minimap = nn.Sequential(
            nn.Flatten(),
            nn.Linear(2 * 16 * 24, 256),
            nn.SiLU(),
            nn.Linear(256, 128),
            nn.SiLU(),
        )
        self.weapon = nn.Embedding(2, 16)
        self.fuse = nn.Sequential(
            nn.Linear(128 * 4 + 16, hidden), nn.LayerNorm(hidden), nn.SiLU()
        )
        self.memory = nn.GRU(hidden, hidden)
        self.actor = nn.Linear(hidden, 8 * 17)
        self.value = nn.Linear(hidden, 1)
        nn.init.normal_(self.actor.weight, std=0.01)
        nn.init.zeros_(self.actor.bias)
        nn.init.zeros_(self.value.bias)

    def initial(self, batch, device=None):
        return torch.zeros(
            (1, batch, self.hidden_size),
            device=device or next(self.parameters()).device,
        )

    def encode(self, obs):
        ent = self.entity(obs["entities"].float())
        mask = obs["entity_mask"].bool()[..., None]
        mean = (ent * mask).sum(-2) / mask.sum(-2).clamp_min(1)
        maximum = ent.masked_fill(~mask, -1e4).max(-2).values
        maximum = torch.where(mask.any(-2), maximum, 0.0)
        return self.fuse(
            torch.cat(
                [
                    self.screen(obs["screen"].float()),
                    self.entity_pool(torch.cat([mean, maximum], -1)),
                    self.hud(obs["hud"].float()),
                    self.minimap(obs["minimap"].float()),
                    self.weapon(obs["weapon"].long()),
                ],
                -1,
            )
        )

    def forward(self, obs, hidden, dones=None):
        """obs [T,B,...], dones[t] resets memory BEFORE observation t."""
        t, b = obs["hud"].shape[:2]
        flat = {k: v.reshape(t * b, *v.shape[2:]) for k, v in obs.items()}
        encoded = self.encode(flat).reshape(t, b, -1)
        if dones is None or not bool(dones.any().item()):
            states, hidden = self.memory(encoded, hidden)
        else:
            rows = []
            for i in range(t):
                hidden = hidden * (~dones[i])[None, :, None]
                x, hidden = self.memory(encoded[i : i + 1], hidden)
                rows.append(x)
            states = torch.cat(rows, 0)
        logits = self.actor(states).reshape(t, b, 8, 17)
        logits = logits.masked_fill(~obs["action_mask"].bool(), -1e9)
        return logits, self.value(states).squeeze(-1), hidden

    def act(self, obs, hidden, deterministic=False):
        seq = {k: v.unsqueeze(0) for k, v in obs.items()}
        logits, value, hidden = self(seq, hidden)
        dist = torch.distributions.Categorical(logits=logits[0], validate_args=False)
        action = logits[0].argmax(-1) if deterministic else dist.sample()
        return action, dist.log_prob(action).sum(-1), value[0], hidden

    def sequence(self, obs, hidden, dones, actions):
        logits, value, _ = self(obs, hidden, dones)
        dist = torch.distributions.Categorical(logits=logits, validate_args=False)
        return dist.log_prob(actions).sum(-1), dist.entropy().sum(-1), value
