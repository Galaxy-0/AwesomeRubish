"""11.3.0 native contact-shape construction, separate from world transform.

Shape registration identifies center+30, half extents+3c, A+48, B+54.
SaberSlash initializer adds half-extents.z to all three centers before setting
the box/cylinder. This local translation does not validate the world rotation.
"""
import copy


def native_shape(shape):
    out = copy.deepcopy(shape)
    shift = shape['BoxHalfExtents']['Z']
    for key in ['BoxCenter', 'CylinderCenterA', 'CylinderCenterB']:
        out[key]['Z'] += shift
    return out
