"""Fallback blade kernel: credit only whole-assembly-clear first body hits.

Every parameter field ball must remain clear until a player ball's first
intersection, under both radius bounds. This intentionally excludes routes
whose success depends on unclosed per-half propagation/order. A rejected
route is not proof that native damage is zero.
"""
import numpy as np
from tools.zipcaster_d4.attack_batch_v2 import (trace_batch as original,
 capsule_axis_distance,segment_box_distances,segment_cylinder_distances)

def trace_batch(field,points,frames,enemies,rotations,collision,radius_bound='initial'):
 r=original(field,points,frames,enemies,rotations,collision,radius_bound)
 stops=np.min(r['field_times'],axis=-1,keepdims=True)
 valid=np.where(r['body_times']<stops-1e-7,r['body_times'],np.inf)
 r.update(hit=np.isfinite(valid).any(axis=-1),body_time=np.min(valid,axis=-1),damage_sphere=np.argmin(valid,axis=-1),
          assembly_uncertain=np.zeros(len(valid),bool),whole_wave_clear_required=True)
 return r
