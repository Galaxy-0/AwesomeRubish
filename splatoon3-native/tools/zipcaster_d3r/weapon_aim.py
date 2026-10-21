"""Explicit weapon style. Stage names must never select muzzle geometry."""
import math

def blade_angles(source,target,parameters,*,style):
 if style not in('full','light'):raise ValueError('explicit full/light style required')
 dx,dz=target[0]-source[0],target[2]-source[2];height=parameters[style+'_origin_height'];elevation=math.atan2(target[1]+parameters['blade_target_height']-source[1]-height,max(.01,math.hypot(dx,dz)));pitch=(elevation-parameters['blade_elevation_bias'])/parameters['blade_elevation_scale']
 return math.atan2(dx,dz),max(-.85,min(.85,pitch))
