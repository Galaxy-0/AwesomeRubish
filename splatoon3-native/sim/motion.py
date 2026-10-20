"""Fitted scalar/NumPy motion equations shared by single and batch simulators."""
import json
import math
from pathlib import Path

import numpy as np

from .identify import MODES, response


class MotionModel:
    def __init__(self, data):
        if data.get('schema') != 'sim.motion.v2' or set(data['modes']) != set(MODES):
            raise ValueError('unsupported motion model')
        self.data = data
        for params in data['modes'].values():
            if not (0 < params['speed'] <= .5 and 0 <= params['deadzone'] < 1 and
                    params['exponent'] > 0 and params['acceleration'] > 0 and params['braking'] > 0):
                raise ValueError('invalid motion coefficients')
            if params.get('response_space','axis') not in ('axis','radial'):raise ValueError('invalid response space')
        curve=data.get('run_speed_up_curve')
        if curve is not None:
            points=np.asarray(curve,float)
            if (points.ndim!=2 or points.shape[1]!=2 or len(points)<2 or not np.isfinite(points).all()
                or points[0,0]!=0 or np.any(np.diff(points[:,0])<=0) or np.any(points[:,1]<=0)):
                raise ValueError('invalid gear curve')

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def to_dict(self):
        return self.data

    def gear_multiplier(self, mode, ap):
        curve=self.data.get('run_speed_up_curve') if mode=='human' else None
        if curve is None:return 1.
        points=np.asarray(curve,float)
        return float(np.interp(ap.get('run_speed_up',0),points[:,0],points[:,1]))

    @staticmethod
    def mode(squid, submerged, grounded, charge, cooldown):
        return 'air' if not grounded else ('squid_own' if submerged else 'squid_dry') if squid else (
            'charge' if charge >= 5 else 'recovery' if cooldown else 'human')

    def camera(self, yaw, pitch, sticks, gyro):
        c = self.data['camera']
        x = math.copysign(max(0., abs(sticks[2])-c['stick_deadzone'])/(1-c['stick_deadzone']), sticks[2])
        yaw += -x*c['stick_gain'] + gyro[2]*c['gyro_gain']
        pitch += -gyro[0]*c['pitch_gain'] + sticks[3]*.012
        return math.atan2(math.sin(yaw), math.cos(yaw)), max(-.9, min(.9, pitch))

    def advance(self, velocity, sticks, yaw, mode, multiplier=1.):
        params = self.data['modes'][mode]
        x = response(np.asarray(sticks[:2]),params['deadzone'],params['exponent'],params.get('response_space','axis'))
        norm = max(1., math.hypot(*x))
        speed = params['speed']*multiplier/norm
        target = np.array([-x[0]*math.cos(yaw)+x[1]*math.sin(yaw),
                           x[0]*math.sin(yaw)+x[1]*math.cos(yaw)])*speed
        current = velocity[[0, 2]]
        rate = params['braking'] if np.linalg.norm(target) < np.linalg.norm(current) else params['acceleration']
        return current+np.clip(target-current, -rate, rate), target

    def batch_advance(self, velocity, sticks, yaw, mode_indices, multipliers=None):
        """Vectorize across arbitrary leading environment/player dimensions."""
        mode_indices = np.asarray(mode_indices)
        result, targets = np.empty_like(velocity), np.empty_like(velocity)
        for index, name in enumerate(MODES):
            mask = mode_indices == index
            if not mask.any():
                continue
            p = self.data['modes'][name]
            local = response(sticks[mask], p['deadzone'], p['exponent'],p.get('response_space','axis'))
            angle = yaw[mask]
            target = np.stack([-local[:, 0]*np.cos(angle)+local[:, 1]*np.sin(angle),
                               local[:, 0]*np.sin(angle)+local[:, 1]*np.cos(angle)], axis=-1)*p['speed']
            if multipliers is not None:
                target *= multipliers[mask, None]
            current = velocity[mask]
            rate = np.where(np.linalg.norm(target, axis=-1) < np.linalg.norm(current, axis=-1), p['braking'], p['acceleration'])
            result[mask] = current+np.clip(target-current, -rate[:, None], rate[:, None])
            targets[mask] = target
        return result, targets
