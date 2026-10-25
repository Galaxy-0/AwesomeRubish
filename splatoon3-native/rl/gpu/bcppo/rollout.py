"""GPU-only match/sensor setup shared by training and held-out evaluation."""

from dataclasses import replace
import torch
from ..env import ParallelEnv
from ..cuda_graph import GraphEnv
from ..stage1.common import configuration
from ..stage1.curriculum import encounter_starts
from ..stage1.opponents import neutral
from ..bc2.observation import GPUInk, encode
from .model import select
from .opponents import Opponent
from .rewards import Guidance


class Match:
    def __init__(self, a, n, training=False):
        self.a, self.training = a, training
        cfg = replace(
            configuration(a.calibration)[0],
            camera_codebook="native_plus5",
            damage_shaping_scale=0.75 if training else 0.5,
        )
        e = ParallelEnv(
            a.data,
            cfg,
            n_envs=n,
            device=a.device,
            compile=a.device.startswith("cuda"),
            fast_rays=a.device.startswith("cuda"),
        )
        self.env = GraphEnv(e) if a.device.startswith("cuda") else e
        self.guide = Guidance(n, self.env.device)
        self.reset(a.seed, "easy" if training else "script")

    def reset(self, seed, kind, near=0.0, history=None):
        e = self.env
        self.raw, _ = e.reset(seed=seed)
        self.near = encounter_starts(e, near, seed)
        if self.near:
            self.raw = e._observation(e.state, e.shots, e.paint, e.steps)
        self.previous = neutral(e.n, e.device)
        self.sensor = GPUInk(self.a.contract, e, self.a.mask_bank)
        self.guide.reset()
        self.opponent = Opponent(e, kind, history)
        self.tick = 0

    def observation(self):
        raw, valid, age = self.sensor.observe(
            {k: x.clone() for k, x in self.raw.items()}
        )
        return select(encode(raw, valid, age, self.previous))

    @torch.no_grad()
    def step(self, actions, guide_scale=0.0):
        e = self.env
        physical = self.previous.clone()
        physical[:, 0] = actions
        ordinary = self.raw
        # Reward eligibility is observed BEFORE the action; no hidden lookahead.
        visible = (
            ordinary["entity_mask"][:, 0] & (ordinary["entities"][:, 0, :, 3] == 1)
        ).any(-1)
        before = e.state.clone()
        physical[:, 1] = self.opponent.actions(ordinary)[:, 1]
        self.raw, reward, term, trunc, info = e.step(physical)
        extra, components = self.guide.step(
            before, e.state, visible, info["events"], e.cfg.decision_frames
        )
        # Keep the simulator's signed zero-sum reward contract.
        reward = reward.clone()
        reward[:, 0] += extra * guide_scale
        reward[:, 1] -= extra * guide_scale
        self.previous = physical
        self.tick += 1
        return (
            reward[:, 0],
            term[:, 0] | trunc[:, 0],
            info,
            dict(visible=visible, guide=components, physical=physical),
        )
