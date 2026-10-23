"""Stage-0 public contract, independent of game data and native host imports."""

from dataclasses import dataclass
import math

MOVE_DIRECTIONS = ((0.0, 0.0),) + tuple(
    (math.sin(i * math.pi / 4) * strength, math.cos(i * math.pi / 4) * strength)
    for strength in (0.5, 1.0)
    for i in range(8)
)
# Separate nine-way categories for yaw and pitch. Input remains held for a step.
CAMERA_LEVELS = (-1.0, -0.35, -0.12, -0.03, 0.0, 0.03, 0.12, 0.35, 1.0)
ACTION_FIELDS = ("move", "yaw", "pitch", "ZR", "ZL", "B", "R", "RS")
ACTION_SIZES = (17, 9, 9, 2, 2, 2, 2, 2)
AGENTS = ("stamper", "52")


@dataclass(frozen=True)
class Config:
    decision_frames: int = 2
    duration_frames: int = 10800
    screen_width: int = 32
    screen_height: int = 18
    max_entities: int = 16
    # Human upper-bound assumption: 90deg / 0.1s, not a measured gyro setting.
    gyro_max_radians_per_frame: float = math.pi / 12
    # Native +5 stick, FOV, camera offset stay unset until measured.
    stick_plus5_radians_per_frame: float | None = None
    camera_horizontal_fov_degrees: float | None = None
    camera_vertical_fov_degrees: float | None = None
    camera_target_forward: float = 0.0
    camera_distance: float | None = None
    camera_target_height: float | None = None
    camera_pitch_offset_radians: float | None = None
    gun_spread_degrees: float = 6.0
    contact_occlusion: str = "whole_shape_clear"  # conservative, unconfirmed
    wave_clipping: str = "whole_wave"  # alternative: independent_halves, unconfirmed
    damage_shaping_scale: float = 0.5
    paint_shaping_per_percent: float = 0.02

    def validate(self):
        if self.decision_frames < 1 or self.duration_frames < 1:
            raise ValueError("positive fixed60 durations required")
        if self.max_entities != 16 or (self.screen_width, self.screen_height) != (
            32,
            18,
        ):
            raise ValueError(
                "stage0 observation contract is 32x18 rays and 16 entities"
            )
        if self.contact_occlusion not in ("whole_shape_clear", "ignore"):
            raise ValueError("unknown contact occlusion approximation")
        if self.wave_clipping not in ("whole_wave", "independent_halves"):
            raise ValueError("unknown wave-clipping approximation")
        if self.camera_pitch_offset_radians is None or not math.isfinite(
            self.camera_pitch_offset_radians
        ):
            raise ValueError("native camera pitch-offset calibration missing")
        for name in (
            "stick_plus5_radians_per_frame",
            "camera_horizontal_fov_degrees",
            "camera_vertical_fov_degrees",
            "camera_distance",
            "camera_target_height",
        ):
            value = getattr(self, name)
            if value is None or not math.isfinite(value) or value <= 0:
                raise ValueError("native calibration missing: " + name)
