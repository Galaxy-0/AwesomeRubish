"""Sparse-parameter charge reserve/refund and explicit effective peer latency.

Latency concerns observed peer HP, not a claim about exact native hit time.
Contact uses a muzzle-anchor candidate; the native skeleton transform remains
unobserved and needs a future independent close-range calibration.
"""
import json
from pathlib import Path


class WeaponModel:
    def __init__(self, data=None):
        self.data = data or dict(schema='sim.weapon.v2', damage_delay=0, contact_muzzle_anchor=True)
        if self.data.get('schema') != 'sim.weapon.v2' or not 0 <= self.data['damage_delay'] <= 30:
            raise ValueError('invalid weapon model')

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def reserve(self, parameters, charge):
        p = parameters.charge
        # Native first-frame zero + five steps to min, then 15 to full:
        # sparse parameters are 5/20, observed control boundaries 6/21.
        elapsed = max(0, charge-1)
        minimum, maximum = p['ChargeFrameMinCharge'], p['ChargeFrameFullCharge']
        if elapsed <= minimum:
            return p['InkConsumeMinCharge']*elapsed/minimum
        ratio = min(1., (elapsed-minimum)/(maximum-minimum))
        return p['InkConsumeMinCharge'] + ratio*(p['InkConsumeFullCharge']-p['InkConsumeMinCharge'])

    def delay(self, cause):
        return int(self.data['damage_delay']) if cause in ('ink_blade', 'contact') else 0
