"""Necessary geometry/time bounds; never substitutes a sphere for damage.

The envelope permits arbitrary pitch, ignores walls, enlarges the receiver,
and allows every possible channel to deal maximum damage simultaneously.
Recoil in the declared model moves radially away from the stationary source
XZ, so the original enemy has the smallest horizontal separation. A bound
may reject an impossible terminal, but cannot certify a hit.
"""
import math
import numpy as np
from tools.zipcaster_d4.model_v3 import schedule, post_path
from tools.zipcaster_d4.contact_shape import native_shape
from tools.zipcaster_d4.attack_geometry import xyz


def envelopes(parameters):
    out = {}
    for style, key in [('full', 'vertical'), ('light', 'horizontal')]:
        shape = native_shape(parameters[key+'_contact']['ShapeParam'])
        bound = np.linalg.norm(np.abs(xyz(shape['BoxCenter']))+xyz(shape['BoxHalfExtents']))
        if shape['HasCylinderShape']:
            bound = max(bound, max(np.linalg.norm(xyz(shape[k])) for k in ['CylinderCenterA', 'CylinderCenterB'])+shape['CylinderRadius'])
        col = parameters[key+'_projectile']['CollisionParam']
        projectile = max(np.linalg.norm(xyz(o))+p['InitRadiusForPlayer'] for o, p in zip(col['OffsetArray'], col['ParamArray']))
        out[style] = dict(contact=float(bound)+.6, projectile=float(projectile)+.6)
    return out


def axis_distance(source, enemy, origin_up=0., origin_forward=0.):
    horizontal = max(0., float(np.linalg.norm((enemy-source)[[0, 2]]))-origin_forward)
    low, high = enemy[1]+.35-source[1]-origin_up, enemy[1]+1.30-source[1]-origin_up
    vertical = max(low, -high, 0.)
    return math.hypot(horizontal, vertical)


def terminal_bound(world, node, enemy, speed, program, ground=False, bounds=None):
    inputs = schedule(speed, program, world.cfg)
    if not inputs:
        return None
    bounds = bounds or envelopes(world.shots.parameters)
    position = world.graph['ground'][node] if ground else world.graph['attach'][node]
    length = inputs[-1][0]+80
    body = np.repeat(position[None, :], length+1, axis=0) if ground else post_path(position, world.graph['floor'][node], length)
    events = []
    for release, style in inputs:
        full = style == 'full'
        cb, pb = release+(4 if full else 9), release+(6 if full else 11)
        # Native contact is fixed at its birth transform for all four frames.
        contact = axis_distance(body[cb], enemy, 1.2 if full else .9, .5 if full else .3)
        if contact <= bounds[style]['contact']+1e-8:
            events.append((cb+world.cfg.receive_delay, 140 if full else 20))
        # Full muzzle is yaw-only; light's rotating(0,1,1.4) is enclosed.
        if full:
            distance = axis_distance(body[pb], enemy, 2.2, .8)
            free = bounds[style]['projectile']+.03  # conservative gravity tail
            travel, velocity = 26*.8, .8
        else:
            distance = axis_distance(body[pb], enemy)
            free = bounds[style]['projectile']+math.hypot(1., 1.4)
            travel, velocity = 6*2.82, 2.82
        if distance <= travel+free+1e-8:
            age = max(0, math.ceil((distance-free-1e-8)/velocity))
            events.append((pb+age+world.cfg.receive_delay, 70 if full else 35))
    hp = 100
    for due, damage in sorted(events):
        hp -= damage
        if hp <= 0:
            extra = sum(world.cfg.full_cost if kind=='full' else world.cfg.light_cost for release, kind in inputs if release<=due)
            activation = world.cfg.activation_frames-world.cfg.activation_drain_grace if ground else 0
            return (due+activation)*world.cfg.drain+extra
    return None
