"""Demo camera FOV before projection; shared arena body-FOV stays unchanged."""

from dataclasses import replace
from arena.geometry import GeometricVision, VisionConfig
from arena.referee_api import RefereeAPI


class CameraVision(GeometricVision):
    def witnesses(self, truth, observer):
        # Use only this observer's camera. No enemy camera/hidden heading is
        # consulted. Missing camera => unknown visibility, never a body fallback.
        players = tuple(
            replace(p, heading=p.view_yaw) if p.player_id == observer else p
            for p in truth.players
        )
        return super().witnesses(replace(truth, players=players), observer)


class DemoRefereeAPI(RefereeAPI):
    def __init__(self, *args, camera_agent=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.camera_agent = camera_agent
        self.camera_vision = CameraVision(
            self._vision.mesh,
            VisionConfig(half_fov_degrees=43, max_distance=35),
        )

    def policy_observation(self, observer):
        if observer != self.camera_agent:
            return super().policy_observation(observer)
        if observer not in self._policy_cache:
            truth = self.state()
            witnesses = self.camera_vision.witnesses(truth, observer)
            # Same LOS/submergence/freshness/public-status projector. Hidden
            # current coordinates never cross the policy wire.
            self._policy_cache[observer] = self._projector.observe(
                truth, observer, witnesses
            )
        return self._policy_cache[observer]
