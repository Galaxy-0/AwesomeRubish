"""Coordinator-owned referee interface and independent filtered policy accessor."""
from pathlib import Path
from .geometry import CollisionMesh,GeometricVision,VisionConfig
from .native_referee import NativeRefereeAdapter
from .visibility import PolicyProjector


class RefereeAPI:
    def __init__(self,match_id,initial_infos,weapons,teams,collision_path:Path,
                 vision_config=VisionConfig(),splash_suppressed=()):
        self._adapter=NativeRefereeAdapter(match_id,initial_infos,weapons,teams,splash_suppressed)
        self._vision=GeometricVision(CollisionMesh.load(collision_path),vision_config)
        self._projector=PolicyProjector(match_id)
        self._truth=None;self._policy_cache={}

    def update(self,infos):
        self._truth=self._adapter.snapshot(infos);self._policy_cache.clear()
        return self._truth

    def state(self):
        """Private immutable truth. Never pass it to policy code or stdout."""
        if self._truth is None:raise RuntimeError('referee has no snapshot')
        return self._truth

    def policy_observation(self,observer):
        """Only this value can be sent through PolicyProcess.act's type gate."""
        if observer not in self._policy_cache:
            truth=self.state();witnesses=self._vision.witnesses(truth,observer)
            self._policy_cache[observer]=self._projector.observe(truth,observer,witnesses)
        return self._policy_cache[observer]
