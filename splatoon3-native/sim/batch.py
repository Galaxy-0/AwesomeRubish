"""Vectorized multi-game motion/ground queries with scalar combat resolution."""
import numpy as np

from .engine import BatchSimulator, gear_factor
from .identify import MODES


class VectorBatchSimulator(BatchSimulator):
    """Same per-env Simulator state/API; batch movement across all live players.

    Weapons, paint and observations retain the scalar implementation. This
    avoids replacing the full judgment model with a faster movement-only toy.
    """
    def __init__(self, count, stage_id=1, **kwargs):
        if kwargs.get('motion_model') is None:
            raise ValueError('vector batch requires explicit fitted MotionModel')
        super().__init__(count, stage_id, **kwargs)
        self.model = self.envs[0].motion_model

    def step(self, actions, frames=1, *, observe=True):
        from arena.process import validate_action
        if len(actions) != len(self.envs) or type(frames) is not int or frames < 1:
            raise ValueError('batch shape/frame budget')
        for env, pair in zip(self.envs, actions):
            if env.frame+frames > env.duration or set(pair) != {'player_0', 'player_1'}:
                raise ValueError('batch match/action budget')
            for action in pair.values(): validate_action(action)
        terrain = self.envs[0].terrain
        for _ in range(frames):
            active = []
            for env, pair in zip(self.envs, actions):
                env.frame += 1
                for role in range(2):
                    action = pair[f'player_{role}']
                    if env._prepare_player(role, action):
                        active.append((env, role, action, env.players[role]))
            if active:
                velocity = np.array([p.velocity[[0, 2]] for _, _, _, p in active])
                sticks = np.array([a['sticks'][:2] for _, _, a, _ in active])
                yaws = np.array([p.yaw for _, _, _, p in active])
                modes = np.array([MODES.index(self.model.mode(p.squid, p.submerged, p.grounded, p.charge, p.cooldown))
                                  for _, _, _, p in active])
                multipliers = np.array([gear_factor('swim_speed_up', p.ap.get('swim_speed_up', 0)) if MODES[m] == 'squid_own' else 1.
                                        for m, (_, _, _, p) in zip(modes, active)])
                multipliers *= np.array([self.model.gear_multiplier(MODES[m],p.ap) for m,(_,_,_,p) in zip(modes,active)])
                horizontal, targets = self.model.batch_advance(velocity, sticks, yaws, modes, multipliers)
                positions = np.array([p.position for _, _, _, p in active])
                deltas = np.array([p.velocity for _, _, _, p in active])
                deltas[:, [0, 2]] = horizontal
                grounded = np.array([p.grounded and not (a['buttons'][4] and not p.previous[4])
                                     for _, _, a, p in active])
                for i, (env, role, _, p) in enumerate(active):
                    if terrain and env.paint.at(p.position) not in (-1, role) and p.grounded:
                        horizontal[i] = np.clip(horizontal[i], -env.rules.enemy_ink_speed, env.rules.enemy_ink_speed)
                        deltas[i, [0, 2]] = horizontal[i]
                moved = terrain.move_batch(positions, deltas, grounded, self.envs[0].rules.terrain_radius)
                floors = terrain.human.floor_batch(moved, moved[:, 1]+.205, -30.)
                for i, (env, role, action, _) in enumerate(active):
                    env._finish_player(role, action, (horizontal[i], targets[i]), moved[i], floors[i])
            for env in self.envs:
                env._weapons()
                env._observations = None
        return [(env.observations() if observe else None, env.info()) for env in self.envs]
