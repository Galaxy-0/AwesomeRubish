"""Dependency-free parallel-env contract, plus batched environments.

Dictionary observations match arena.policy.v1. This is a PettingZoo-style
adapter, not registered Gym/PettingZoo conformance (spaces need a later wrapper).
"""
from .engine import Simulator, BatchSimulator
from .batch import VectorBatchSimulator


class ParallelEnv:
    possible_agents = ['player_0', 'player_1']
    metadata = Simulator.metadata

    def __init__(self, **kwargs):
        self.sim = Simulator(**kwargs)
        self.agents = self.possible_agents.copy()

    def reset(self, seed=None, options=None):
        obs, info = self.sim.reset(seed=seed, options=options)
        self.agents = self.possible_agents.copy()
        return obs, {agent: dict(info) for agent in self.agents}

    def step(self, actions):
        if not self.agents:
            raise RuntimeError('reset before stepping a completed environment')
        before = self.sim.paint.ratios()
        obs, info = self.sim.step(actions)
        after = info['turf_ratio_by_role']
        reward = {agent: (after[i] - before[i]) - (after[1-i] - before[1-i])
                  for i, agent in enumerate(self.agents)}
        terminated = {agent: self.sim.done for agent in self.agents}
        truncated = {agent: False for agent in self.agents}
        infos = {agent: dict(info) for agent in self.agents}
        if self.sim.done:
            self.agents = []
        return obs, reward, terminated, truncated, infos

    def close(self):
        pass


__all__ = ['ParallelEnv', 'BatchSimulator', 'VectorBatchSimulator']
