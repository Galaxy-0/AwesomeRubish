"""Historical match cohorts and an explicitly privileged D4 reference fixture.

Only the fixed-script evaluator reads referee positions. Learned actors receive
prepare(public_obs) only. The D4 cone stays fixed even while ideal gun aim moves.
"""

import copy
import torch
from ..env import HP, SUB, YAW, PITCH, INK


def neutral(n, device):
    a = torch.zeros((n, 2, 8), device=device, dtype=torch.int64)
    a[..., 1:3] = 4
    return a


class D4Defender:
    def __init__(self, env, heading=None):
        self.env = env
        self.heading = (
            env.state[:, 1, YAW].clone() if heading is None else heading.clone()
        )
        self.fired = torch.zeros(env.n, device=env.device)
        self.seen = torch.zeros_like(self.fired)

    def actions(self):
        e = self.env
        s = e.state
        delta = s[:, 0, :3] - s[:, 1, :3]
        distance = delta.norm(dim=-1)
        facing = (
            delta[:, 0] * self.heading.sin() + delta[:, 2] * self.heading.cos() >= -1e-8
        )
        start = s[:, 1, :3] + torch.tensor([0.0, 1.1, 0.0], device=e.device)
        visible = torch.zeros(e.n, dtype=torch.bool, device=e.device)
        for h in [0.12, 0.7, 1.3]:
            end = s[:, 0, :3] + torch.tensor([0.0, h, 0.0], device=e.device)
            d = end - start
            length = d.norm(dim=-1)
            blocked, _, _ = e.geo.ray(
                start, d / length[:, None].clamp_min(1e-6), 30.0, 0.5
            )
            visible |= blocked >= length - 0.1
        visible &= facing & (distance <= 30) & (s[:, 0, HP] > 0) & (s[:, 0, SUB] == 0)
        fire = visible & (distance <= 13.4) & (s[:, 1, HP] > 0) & (s[:, 1, INK] > 0.015)
        # Native D4 uses direct aim and no ballistic compensation; preserve this
        # reference strength/limitation. Camera value is a fixture, not policy obs.
        yaw = torch.atan2(delta[:, 0], delta[:, 2])
        pitch = torch.atan2(
            delta[:, 1], torch.linalg.vector_norm(delta[:, [0, 2]], dim=-1)
        )
        s[:, 1, YAW] = torch.where(fire, yaw, self.heading)
        s[:, 1, PITCH] = torch.where(fire, pitch.clamp(-0.85, 0.85), 0.0)
        a = neutral(e.n, e.device)
        a[:, 1, 3] = fire.long()
        self.fired += fire
        self.seen += visible
        return a


class League:
    """50% latest,40% historical(two20% cohorts),10% held-random.

    Models are chosen at full-match reset, never replaced mid-match. Both roles
    alternate as learner by env parity. Historical actions do not enter PPO loss.
    """

    def __init__(self, policy, n, device, seed=0):
        self.n = n
        self.device = device
        self.policy = policy
        self.generator = torch.Generator().manual_seed(seed)
        self.snapshots = []
        self.models = []
        self.hidden = []
        self.assignments = []
        self.bounds = [(n // 2, 7 * n // 10), (7 * n // 10, 9 * n // 10)]
        self.role = torch.arange(n, device=device) % 2
        self.learner = torch.ones((n, 2), dtype=torch.bool, device=device)
        rows = torch.arange(n // 2, n, device=device)
        self.learner[rows, 1 - self.role[rows]] = False
        self.snapshot(0)
        self.new_match()

    def snapshot(self, version):
        state = {
            k: v.detach().cpu().clone() for k, v in self.policy.state_dict().items()
        }
        self.snapshots.append((version, state))

    def new_match(self):
        self.models = []
        self.hidden = []
        self.assignments = []
        for start, end in self.bounds:
            i = int(
                torch.randint(
                    len(self.snapshots), (1,), generator=self.generator
                ).item()
            )
            version, state = self.snapshots[i]
            model = copy.deepcopy(self.policy).eval()
            model.load_state_dict(state)
            model.memory.flatten_parameters()
            for p in model.parameters():
                p.requires_grad_(False)
            self.models.append(model)
            self.hidden.append(model.initial((end - start) * 2, self.device))
            self.assignments.append(version)

    @torch.no_grad()
    def override(self, obs, actions, random_actions):
        for i, (start, end) in enumerate(self.bounds):
            if end <= start:
                continue
            view = {k: v[start * 2 : end * 2] for k, v in obs.items()}
            old, _, _, self.hidden[i] = self.models[i].act(view, self.hidden[i])
            old = old.reshape(end - start, 2, 8)
            rows = torch.arange(start, end, device=self.device)
            opponent = 1 - self.role[rows]
            actions[rows, opponent] = old[rows - start, opponent]
        start = 9 * self.n // 10
        rows = torch.arange(start, self.n, device=self.device)
        opponent = 1 - self.role[rows]
        actions[rows, opponent] = random_actions[rows, opponent]
        return actions
