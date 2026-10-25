"""Feedback/no-feedback/chunk ablations; all outputs are ordinary held inputs."""

import torch
from torch import nn
from ..stage1.policy import Policy


class Actor(Policy):
    def __init__(self, hidden=384, horizon=1, feedback=False):
        super().__init__(hidden, action_feedback=feedback, button_semantics="level")
        self.horizon = horizon
        self.actor = nn.Linear(hidden, horizon * 8 * 17)
        nn.init.normal_(self.actor.weight, std=0.01)
        nn.init.zeros_(self.actor.bias)
        self.quality = nn.Sequential(
            nn.Linear(446, 128), nn.SiLU(), nn.Linear(128, hidden)
        )
        self.attack = nn.Linear(hidden, 4)

    def encode(self, obs):
        return super().encode(obs) + self.quality(obs["quality"].float())

    def forward(self, obs, hidden, dones=None):
        t, b = obs["hud"].shape[:2]
        flat = {k: v.reshape(t * b, *v.shape[2:]) for k, v in obs.items()}
        x = self.encode(flat).reshape(t, b, -1)
        if dones is None or not bool(dones.any()):
            memory, hidden = self.memory(x, hidden)
        else:
            rows = []
            for i in range(t):
                hidden = hidden * (~dones[i])[None, :, None]
                y, hidden = self.memory(x[i : i + 1], hidden)
                rows.append(y)
            memory = torch.cat(rows, 0)
        logits = self.actor(memory).reshape(t, b, self.horizon, 8, 17)
        logits = logits.masked_fill(~obs["action_mask"][:, :, None].bool(), -1e9)
        return logits, self.value(memory).squeeze(-1), hidden, self.attack(memory)


class Ensemble:
    """Categorical probability averaging across aligned future action predictions.

    No attack macros or feedback of held buttons. Query each2f; combine recent
    predictions for this tick with exp(-age/4), then sample/argmax physical levels.
    """

    def __init__(self, actor, batch, device, camera_decode="argmax"):
        self.actor = actor
        self.hidden = actor.initial(batch, device)
        self.predictions = []
        if camera_decode not in ("argmax", "expectation"):
            raise ValueError("unknown camera decoder")
        self.camera_decode = camera_decode

    @torch.no_grad()
    def act(self, obs, deterministic=True):
        logits, _, self.hidden, _ = self.actor(
            {k: v[None] for k, v in obs.items()}, self.hidden
        )
        self.predictions = [p[:, 1:] for p in self.predictions if p.shape[1] > 1]
        self.predictions.append(logits[0].softmax(-1))
        weight = torch.exp(
            -torch.arange(len(self.predictions) - 1, -1, -1, device=logits.device) / 4.0
        )
        mixture = (
            sum(p[:, 0] * w for p, w in zip(self.predictions, weight)) / weight.sum()
        )
        action = (
            mixture.argmax(-1)
            if deterministic
            else torch.distributions.Categorical(
                probs=mixture, validate_args=False
            ).sample()
        )
        if deterministic and self.camera_decode == "expectation":
            from ..contract import Config, camera_levels

            levels = torch.tensor(
                camera_levels(Config(camera_codebook="native_plus5")),
                device=mixture.device,
            )
            desired = (mixture[:, 1:3, :9] * levels).sum(-1)
            action[:, 1:3] = (levels[None, None] - desired[..., None]).abs().argmin(-1)
        return action


def load(path, device="cuda"):
    r = torch.load(path, map_location="cpu", weights_only=False)
    if r.get("schema") != "inklab.bc2.checkpoint.v1":
        raise ValueError("BC2 owned checkpoint required")
    p = Actor(r["hidden"], r["horizon"], r["feedback"]).to(device)
    p.load_state_dict(r["policy"])
    return p.eval(), r
