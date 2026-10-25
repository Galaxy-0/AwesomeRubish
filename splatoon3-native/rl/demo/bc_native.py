"""BC native measurement adapter, script-only capture fixture, never arena/T1.

Uses only visible GPU observations rebuilt from causal native packets. Referee
states locate the two actors for ray occlusion, never become actor xyz features.
Ink/weapon/projectile omissions keep the same explicit validity contract.
"""

from pathlib import Path
import re
import torch
from rl.gpu.bc.model import load, features
from rl.gpu.stage1.common import configuration
from rl.gpu.stage1.opponents import neutral as physical_neutral
from rl.gpu.stage1.controller import physical
from rl.gpu.contract import camera_levels, MOVE_DIRECTIONS
from rl.gpu.env import ParallelEnv
from .state_sync import NativeRebuilder, CausalIndex
from .camera_model import predict

CAMERA = re.compile(
    r"D3R_STATE frame=(\d+)[^\n]*? yaw=([^ ]+) pitch=([^ ]+) v17b8=([^ ]+) v17c4=([^ ]+)"
)


def native_action(action, cfg, camera):
    """Inverse measured steady gyro response; ordinary native input, no aim writes."""
    import numpy as np

    delta = np.asarray(camera_levels(cfg))[[action[1], action[2]]] * (
        cfg.gyro_max_radians_per_frame + cfg.stick_plus5_radians_per_frame
    )
    matrix = np.asarray(camera["gyro_matrix"])
    gyro = np.linalg.lstsq(matrix, delta, rcond=None)[0]
    if abs(gyro).max() > 8:
        raise ValueError("BC inverse camera command exceeds native fixture bounds")
    # Explicitly verify the same forward mapping used by the label quantizer.
    if not np.allclose(predict(np.r_[0.0, 0.0, gyro], camera), delta, atol=1e-6):
        raise ValueError("non-invertible calibrated gyro")
    buttons = [action[3], action[4], action[6], action[7], action[5], 0]
    return dict(
        sticks=[*MOVE_DIRECTIONS[action[0]], 0.0, 0.0],
        gyro=gyro.tolist(),
        buttons=buttons,
    )


class NativeBC:
    def __init__(
        self,
        checkpoint,
        out,
        session,
        origins,
        data,
        calibration,
        camera,
        model_loader=None,
    ):
        import json
        from dataclasses import replace

        torch.set_num_threads(1)
        self.policy, _ = (model_loader or load)(checkpoint, "cpu")
        self.camera_model = json.loads(Path(camera).read_text())
        cfg, _ = configuration(calibration)
        self.cfg = replace(cfg, camera_codebook="native_plus5")
        self.env = ParallelEnv(data, self.cfg, device="cpu")
        self.rebuilder = NativeRebuilder(self.env, out, origins)
        self.logs = [(Path(session) / f"player-{n}/host.log").open() for n in range(2)]
        self.origins = origins
        self.camera_rows = [[], []]
        self.hidden = self.policy.initial(2)
        self.previous = physical_neutral(1, "cpu")
        self.last_frame = None
        self.history = (Path(out) / "bc-decisions.jsonl").open("w")

    def read_cameras(self):
        for n, stream in enumerate(self.logs):
            for line in stream:
                m = CAMERA.search(line)
                if m:
                    self.camera_rows[n].append(
                        dict(
                            frame=int(m[1]) - self.origins[f"player_{n}"]["frame"],
                            yaw=float(m[2]),
                            pitch=float(m[3]),
                            eye=list(map(float, m[4].split(","))),
                            at=list(map(float, m[5].split(","))),
                        )
                    )
            self.camera_rows[n] = self.camera_rows[n][-16:]
            self.rebuilder.camera[n] = CausalIndex(self.camera_rows[n])

    @torch.no_grad()
    def act(self, frame, infos):
        import json

        self.read_cameras()
        raw, quality = self.rebuilder.observe(dict(frame=frame, infos=infos))
        validity = dict(
            hud_valid=torch.ones_like(raw["hud"], dtype=torch.bool),
            screen_channel_valid=torch.ones_like(raw["screen"], dtype=torch.bool),
            minimap_valid=torch.zeros_like(raw["minimap"], dtype=torch.bool),
            entity_velocity_native_valid=torch.zeros(1, 2, dtype=torch.bool),
            projectiles_native_valid=torch.zeros(1, 2, dtype=torch.bool),
            native_camera_valid=torch.tensor([quality["camera_native_valid"]]),
        )
        validity["hud_valid"][..., [4, 7, 8]] = False
        validity["screen_channel_valid"][..., 2] = False
        encoded = features(raw, self.previous, validity)
        commands, _, _, self.hidden = self.policy.act(encoded, self.hidden, True)
        self.previous = physical(commands.reshape(1, 2, 8), self.previous, "toggle")
        action = self.previous[0, 0].tolist()
        self.history.write(
            json.dumps(
                dict(
                    frame=frame,
                    actions=action,
                    quality={
                        k: quality[k]
                        for k in [
                            "state_valid",
                            "source_age_frames",
                            "camera_native_valid",
                        ]
                    },
                )
            )
            + "\n"
        )
        return native_action(action, self.cfg, self.camera_model)

    def close(self):
        for f in [*self.logs, self.history]:
            f.close()
