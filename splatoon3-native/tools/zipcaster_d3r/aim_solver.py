"""Invert frozen hook-ray surrogate for a requested world anchor.

Translation correction is a fitted effective ray origin, not a body/anchor write.
"""
import math
import numpy as np
from tools.zipcaster_d3r.fit_mapping import bases
from tools.zipcaster_d3r.ray_model import inverse_pitch

def hook_angles(position,body_heading,anchor,parameters):
 p=np.asarray(position);q=np.asarray(anchor);yaw=math.atan2(q[0]-p[0],q[2]-p[2])-parameters['yaw_bias']
 for _ in range(8):
  origin=p+bases(dict(command=dict(yaw=yaw),body_heading=body_heading))@parameters['origin_coefficients'];delta=q-origin;yaw=math.atan2(delta[0],delta[2])-parameters['yaw_bias']
 elevation=math.atan2(delta[1],math.hypot(delta[0],delta[2]));pitch=inverse_pitch(elevation,parameters)
 if abs(pitch)>.9:raise ValueError('anchor requires native pitch outside fixture domain')
 return math.atan2(math.sin(yaw),math.cos(yaw)),pitch
