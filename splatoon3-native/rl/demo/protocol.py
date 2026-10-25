"""Demo-only extension: real physical gyro rates are turns/s, not normalized sticks."""

from functools import lru_cache
import numpy as np
from gymnasium import spaces
from rl.protocol import Client
from rl.env import NativeParallelEnv


class DemoClient(Client):
    def send_step(self, action, frames):
        axes = np.asarray(action["sticks"], float)
        gyro = np.asarray(action["gyro"], float)
        buttons = np.asarray(action["buttons"])
        observer = np.asarray(action.get("observer_buttons", [0]))
        if (
            axes.shape != (4,)
            or gyro.shape != (3,)
            or buttons.shape != (6,)
            or observer.shape != (1,)
        ):
            raise ValueError("demo input shapes")
        if (
            not np.isfinite(axes).all()
            or not np.isfinite(gyro).all()
            or (abs(axes) > 1).any()
            or (abs(gyro) > 8).any()
        ):
            raise ValueError("sticks ±1; physical gyro ±8 turns/s")
        if (
            not np.isin(buttons, (0, 1)).all()
            or not np.isin(observer, (0, 1)).all()
            or type(frames) is not int
            or not 1 <= frames <= 3600
        ):
            raise ValueError("invalid demo input")
        mask = sum(int(v) << bit for v, bit in zip(buttons, (9, 8, 7, 5, 1, 3)))
        mask |= int(observer[0]) << 2  # nn::hid X, printed Nintendo X.
        sticks = np.rint(axes * 32767).astype(np.int32)
        self.sequence += 1
        self.expected = frames
        self.pending.append((self.sequence, frames))
        line = (
            f"STEP {self.sequence} {frames} {mask:x} "
            + " ".join(map(str, sticks))
            + " "
            + " ".join(map(str, gyro))
            + "\n"
        )
        self.socket.sendall(line.encode("ascii"))


class DemoEnv(NativeParallelEnv):
    @lru_cache(None)
    def action_space(self, agent):
        old = super().action_space(agent)
        return spaces.Dict(
            dict(old.spaces)
            | dict(
                gyro=spaces.Box(-8, 8, (3,), np.float32),
                observer_buttons=spaces.MultiBinary(1),
            )
        )

    def reset(self, *args, **kwargs):
        value = super().reset(*args, **kwargs)
        for c in self.clients.values():
            c.__class__ = DemoClient
        return value
