"""BC2-exact actor adapter; critic preheat cannot change actor features."""

import torch
from ..bc2.model import Actor


class WarmActor(Actor):
    def __init__(self, hidden=384):
        super().__init__(hidden, horizon=1, feedback=False)

    def forward(self, obs, hidden, dones=None):
        logits, value, hidden, _ = super().forward(obs, hidden, dones)
        return logits[:, :, 0], value, hidden


def initialize(path, device):
    raw = torch.load(path, map_location="cpu", weights_only=False)
    if raw.get("schema") != "inklab.bc2.checkpoint.v1":
        raise ValueError("owned BC2 checkpoint required")
    if raw["horizon"] != 1 or raw["feedback"]:
        raise ValueError("only accepted no-feedback single-step BC2 may warm start")
    model = WarmActor(raw["hidden"]).to(device)
    model.load_state_dict(raw["policy"], strict=True)
    return model, raw


def select(raw):
    """BC encoder interleaves roles. Only Stamper rows enter learning."""
    return {k: x[::2] for k, x in raw.items()}


def distributions(logits):
    return torch.distributions.Categorical(logits=logits, validate_args=False)


def bc_kl(logits, teacher_prob):
    # Six legal heads; frozen R/RS contribute neither reward nor dilution.
    teacher_prob = teacher_prob.float()
    teacher_prob = teacher_prob / teacher_prob.sum(-1, keepdim=True).clamp_min(1e-20)
    return (
        (teacher_prob * (teacher_prob.clamp_min(1e-20).log() - logits.log_softmax(-1)))
        .sum(-1)[..., :6]
        .mean(-1)
    )
