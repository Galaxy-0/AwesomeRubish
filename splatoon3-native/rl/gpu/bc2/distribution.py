"""Descriptive train-vs-rollout feature shift, not a test of simulator fidelity."""

import numpy as np
import torch

HUD_FIELDS = [
    "ink",
    "special",
    "squid_form",
    "submerged",
    "charge",
    "hook_phase",
    "remaining_time",
    "own_turf",
    "enemy_turf",
    "own_hp_cue",
]
FIELD_NAMES = dict(
    screen=[
        "distance",
        "kind_none",
        "kind_ground",
        "kind_wall",
        "kind_person",
        "ink_own",
        "ink_enemy",
        "hookable",
    ],
    hud=HUD_FIELDS,
    minimap=["ink_own_pooled", "ink_enemy_pooled"],
    entities=[
        "screen_x",
        "screen_y",
        "distance",
        "kind",
        "velocity_x",
        "velocity_y",
        "velocity_z",
    ],
    validity=[
        "hud_ink",
        "hud_charge",
        "hud_time",
        "hud_own_turf",
        "hud_enemy_turf",
        "projectiles",
        "native_camera",
        "ink_age_over30",
    ],
    availability=["visible_enemy"]
    + ["hud_" + k for k in HUD_FIELDS]
    + [
        "screen_distance",
        "screen_kind",
        "screen_ink",
        "screen_hookable",
        "minimap",
        "entity_velocity",
        "projectiles",
        "native_camera",
        "ink_age_over30",
    ],
)


def groups(obs):
    """Already normalized policy inputs; callers pass only the Stamper rows."""
    # Fixed lattice subsampling keeps long-rollout reports small and reproducible.
    screen = obs["screen"].permute(0, 2, 3, 1).reshape(-1, 8)[::17]
    mini = obs["minimap"].permute(0, 2, 3, 1).reshape(-1, 2)[::13]
    ent = obs["entities"][obs["entity_mask"].bool()]
    quality = obs["quality"]
    availability_tensor = torch.cat(
        [
            obs["entity_mask"].any(-1, keepdim=True).float(),
            quality[:, :10],
            quality[:, 10:58].reshape(-1, 4, 12).mean(-1),
            quality[:, 58:442].mean(-1, keepdim=True),
            quality[:, 442:446],
        ],
        -1,
    )
    return dict(
        screen=screen,
        hud=obs["hud"],
        minimap=mini,
        entities=ent,
        validity=obs["quality"][:, [0, 4, 6, 7, 8, -3, -2, -1]],
        availability=availability_tensor,
    )


class Collector:
    def __init__(self, limit=100000):
        self.limit = limit
        self.rows = {}

    def capture(self, obs):
        for k, v in groups(obs).items():
            # Every evenly spaced snapshot contributes; final thinning is uniform.
            self.rows.setdefault(k, []).append(
                v.detach().cpu().numpy().astype(np.float32)
            )

    def arrays(self):
        result = {}
        for k, rows in self.rows.items():
            a = np.concatenate(rows) if rows else np.empty((0, 0))
            if len(a) > self.limit:
                a = a[np.linspace(0, len(a) - 1, self.limit, dtype=int)]
            result[k] = a
        return result


def compare(train, test):
    result = {}
    for k, a in train.items():
        b = test[k]
        fields = []
        for h in range(a.shape[-1]):
            x = np.sort(a[:, h])
            y = np.sort(b[:, h])
            metadata = dict(
                name=FIELD_NAMES.get(k, [str(i) for i in range(a.shape[-1])])[h],
                train_n=len(x),
                gpu_n=len(y),
                train_mean=float(x.mean()) if len(x) else None,
                train_variance=float(x.var()) if len(x) else None,
                gpu_mean=float(y.mean()) if len(y) else None,
                gpu_variance=float(y.var()) if len(y) else None,
            )
            if not len(x) or not len(y):
                fields.append(dict(**metadata, ks=None))
                continue
            points = np.unique(np.r_[x, y])
            ks = np.max(
                np.abs(
                    np.searchsorted(x, points, side="right") / len(x)
                    - np.searchsorted(y, points, side="right") / len(y)
                )
            )
            fields.append(
                dict(
                    **metadata,
                    ks=float(ks),
                )
            )
        result[k] = fields
    return result
