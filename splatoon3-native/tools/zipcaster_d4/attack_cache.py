"""Bounded exact-input caches; no pose rounding or changed collision predicate."""
from functools import lru_cache
import numpy as np
from tools.zipcaster_d4.attack_model_v5 import Shots as Uncached


class Shots(Uncached):
    def best(self,source,target,style,step=.01):
        return self._best(tuple(source),tuple(target),style,step)
    @lru_cache(maxsize=8192)
    def _best(self,source,target,style,step):
        return super().best(source,target,style,step)
    def best_contact(self,source,target,style,step=.01):
        return self._best_contact(tuple(source),tuple(target),style,step)
    @lru_cache(maxsize=8192)
    def _best_contact(self,source,target,style,step):
        return super().best_contact(source,target,style,step)
    def evaluate(self,source,target,style,yaw,pitch,target_positions=None):
        packed=None if target_positions is None else np.asarray(target_positions,dtype=np.float64).tobytes()
        return self._evaluate(tuple(source),tuple(target),style,yaw,pitch,packed)
    @lru_cache(maxsize=8192)
    def _evaluate(self,source,target,style,yaw,pitch,packed):
        poses=None if packed is None else np.frombuffer(packed,dtype=np.float64).reshape(-1,3)
        return super().evaluate(source,target,style,yaw,pitch,poses)
    def contact(self,source_path,target_path,style,yaw,pitch,receiver='ColBullet'):
        return self._contact(np.asarray(source_path,dtype=np.float64).tobytes(),
                             np.asarray(target_path,dtype=np.float64).tobytes(),style,yaw,pitch,receiver)
    @lru_cache(maxsize=8192)
    def _contact(self,source,target,style,yaw,pitch,receiver):
        return super().contact(np.frombuffer(source,dtype=np.float64).reshape(-1,3),
                               np.frombuffer(target,dtype=np.float64).reshape(-1,3),style,yaw,pitch,receiver)
