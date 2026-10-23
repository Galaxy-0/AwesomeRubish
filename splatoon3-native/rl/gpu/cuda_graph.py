"""Whole-step CUDA graph replay, preserving state and full observation semantics.

The persistent input buffers receive the just-computed referee state inside the
captured graph, so every replay advances the previous result rather than replaying
one frozen frame. reset updates those same buffers. No CPU reads on step.
"""

import torch


class GraphEnv:
    def __init__(self, env):
        if env.device.type != "cuda":
            raise ValueError("CUDA graph requires CUDA")
        self.env = env
        self.buffers = {
            k: getattr(env, k)
            for k in ["state", "shots", "paint", "steps", "dead", "seed_tensor"]
        }
        self.actions = env.random_actions()
        stream = torch.cuda.Stream()
        stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            for _ in range(3):
                self._iteration()
        torch.cuda.current_stream().wait_stream(stream)
        torch.cuda.synchronize()
        self.graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(self.graph):
            self.result = self._iteration()
        self.reset()

    def __getattr__(self, key):
        return getattr(self.env, key)

    def _restore(self):
        for k, original in self.buffers.items():
            value = getattr(self.env, k)
            if value is not original:
                original.copy_(value)
                setattr(self.env, k, original)

    def _iteration(self):
        result = self.env.step(self.actions)
        self._restore()
        return result

    def step(self, actions):
        if (
            actions.shape != self.actions.shape
            or actions.device != self.actions.device
            or actions.dtype != torch.int64
        ):
            raise ValueError("graph action shape/device/dtype")
        self.actions.copy_(actions)
        self.graph.replay()
        return self.result

    def reset(self, seed=None, options=None):
        _, info = self.env.reset(seed=seed, options=options)
        self._restore()
        return self.env._observation(
            self.env.state, self.env.shots, self.env.paint, self.env.steps
        ), info
