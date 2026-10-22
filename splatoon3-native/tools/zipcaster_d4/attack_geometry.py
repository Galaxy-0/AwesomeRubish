"""Explicit projectile/body and native box/cylinder geometry for D4.

No game code or assets. Cylinder means a finite flat-ended cylinder, not a
capsule. Player capsules and assembly policies are declared separately.
"""
import math
import numpy as np

def basis(yaw, elevation):
    right = np.array([math.cos(yaw), 0., -math.sin(yaw)])
    forward = np.array([math.sin(yaw)*math.cos(elevation), math.sin(elevation),
                        math.cos(yaw)*math.cos(elevation)])
    up = np.cross(forward, right)
    return np.stack([right, up, forward], axis=1)

def muzzle(source, yaw, elevation, style):
    """Hypothesis from native pose/p110 only, never fitted to damage labels."""
    source = np.asarray(source, float)
    if style == 'full':
        b = basis(yaw, 0.)
        start = source + [0., 2.2, 0.]
        return start + b[:, 2]*.8, start
    if style != 'light':
        raise ValueError('explicit style required')
    b = basis(yaw, elevation)
    start = source + b[:, 1]
    return start + b[:, 2]*1.4, start

def capsule_fraction(a, b, radius, low=.35, high=1.30):
    """First intersection of a segment with a vertical capsule at the origin.

    radius includes the moving sphere's radius (exact Minkowski sum).
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b-a
    near = a - [0., np.clip(a[1], low, high), 0.]
    if near@near <= radius*radius:
        return 0.
    roots = []
    aa = float(d[[0,2]]@d[[0,2]])
    bb = float(a[[0,2]]@d[[0,2]])
    cc = float(a[[0,2]]@a[[0,2]] - radius*radius)
    disc = bb*bb-aa*cc
    if aa > 1e-15 and disc >= 0:
        t = (-bb-math.sqrt(disc))/aa
        if 0 <= t <= 1 and low <= a[1]+t*d[1] <= high:
            roots.append(t)
    for y in (low, high):
        q = a-[0., y, 0.]
        aa, bb, cc = float(d@d), float(q@d), float(q@q-radius*radius)
        disc = bb*bb-aa*cc
        if aa > 1e-15 and disc >= 0:
            t = (-bb-math.sqrt(disc))/aa
            if 0 <= t <= 1:
                roots.append(t)
    return min(roots) if roots else None

def segment_box_distance(a, b, center, half):
    """Exact piecewise quadratic distance from segment to solid AABB."""
    a, b, center, half = map(lambda x: np.asarray(x, float), (a,b,center,half))
    a, d = a-center, b-a
    breaks = [0., 1.]
    for i in range(3):
        if abs(d[i]) > 1e-15:
            breaks.extend(float(t) for t in ((-half[i]-a[i])/d[i],
                                            (half[i]-a[i])/d[i]) if 0 < t < 1)
    breaks = sorted(set(breaks))
    def sq(t):
        v = np.maximum(np.abs(a+t*d)-half, 0.)
        return float(v@v)
    best = min(map(sq, breaks))
    for left, right in zip(breaks, breaks[1:]):
        p = a+(left+right)/2*d
        active = np.abs(p)>half
        dd = d[active]
        offset = a[active]-np.sign(p[active])*half[active]
        if dd@dd > 1e-15:
            t = float(np.clip(-(dd@offset)/(dd@dd), left, right))
            best = min(best, sq(t))
    return math.sqrt(best)

def segment_cylinder_distance(a, b, ca, cb, radius):
    """Distance to a solid flat-ended cylinder, 1D convex minimization.

    Numerical minimization error is bounded by segment_length*interval_width;
    this never replaces the cylinder with rounded end caps.
    """
    a,b,ca,cb = map(lambda x: np.asarray(x,float), (a,b,ca,cb))
    axis = cb-ca
    length = float(np.linalg.norm(axis))
    if length < 1e-12:
        raise ValueError('degenerate cylinder needs explicit disk semantics')
    axis /= length
    center = (ca+cb)/2
    def sq(t):
        p = a+t*(b-a)-center
        axial = float(p@axis)
        radial = np.linalg.norm(p-axial*axis)
        return max(abs(axial)-length/2,0.)**2 + max(radial-radius,0.)**2
    left,right = 0.,1.
    phi = (math.sqrt(5)-1)/2
    x,y = right-phi*(right-left), left+phi*(right-left)
    fx,fy = sq(x),sq(y)
    for _ in range(72):
        if fx <= fy:
            right,y,fy = y,x,fx
            x = right-phi*(right-left); fx = sq(x)
        else:
            left,x,fx = x,y,fy
            y = left+phi*(right-left); fy = sq(y)
    return math.sqrt(min(sq(0.),sq(1.),fx,fy))

def xyz(row):
    return np.array([row[k] for k in ('X','Y','Z')],float)

def contact_overlap(origin, rotation, shape, target, body_radius=.35,
                    body_low=.35, body_high=1.30):
    """Union of native box and optional cylinder against target capsule."""
    target, origin = np.asarray(target,float), np.asarray(origin,float)
    a = rotation.T@(target+[0,body_low,0]-origin)
    b = rotation.T@(target+[0,body_high,0]-origin)
    box = segment_box_distance(a,b,xyz(shape['BoxCenter']),xyz(shape['BoxHalfExtents']))
    cylinder = None
    if shape['HasCylinderShape']:
        cylinder = segment_cylinder_distance(a,b,xyz(shape['CylinderCenterA']),
                                             xyz(shape['CylinderCenterB']),shape['CylinderRadius'])
    distance = min(box, cylinder if cylinder is not None else math.inf)
    return dict(hit=distance<=body_radius+1e-9,box_distance=box,
                cylinder_distance=cylinder,clearance=body_radius-distance)

def trace_contacts(field, points, frames, enemies, yaw, elevation, collision,
                   core_only=False, side_policy='independent'):
    """Compare first player, field and lifetime events on a finite root trace.

    'independent': side sphere stops contributing after its own wall hit;
    'core_lifetime': sides continue until core stops. Neither is silently
    equated with whole-projectile death on the first side collision.
    """
    if side_policy not in ('independent','core_lifetime'):
        raise ValueError('assembly policy')
    points,enemies = np.asarray(points,float),np.asarray(enemies,float)
    rotation = basis(yaw,elevation)
    offsets = np.array([rotation@xyz(o) for o in collision['OffsetArray']])
    core = collision['CoreIndex']
    n = len(points)-1
    if n < 1:
        return dict(hit=False,body_time=None,core_field_time=None,side_events=[],lifetime_end=float(frames[-1]))
    starts = (points[:-1,None,:]+offsets).reshape(-1,3)
    ends = (points[1:,None,:]+offsets).reshape(-1,3)
    movement = ends-starts
    lengths = np.linalg.norm(movement,axis=1)
    directions = movement/np.maximum(lengths[:,None],1e-15)
    k = len(offsets)
    radii = np.array([r['InitRadiusForField'] for r in collision['ParamArray']])
    indices,_,dist = field.sphere(starts,directions,np.tile(radii,n),np.maximum(lengths,1e-12))
    field_times = [None]*k
    bodies = [None]*k
    for step in range(n):
        dt = frames[step+1]-frames[step]
        for j in range(k):
            flat = step*k+j
            if indices[flat]>=0 and field_times[j] is None:
                field_times[j] = float(frames[step]+dt*dist[flat]/max(lengths[flat],1e-15))
            if bodies[j] is None:
                player_radius = collision['ParamArray'][j]['InitRadiusForPlayer']
                fraction = capsule_fraction(starts[flat]-enemies[step],ends[flat]-enemies[step+1],.35+player_radius)
                if fraction is not None:
                    bodies[j] = float(frames[step]+dt*fraction)
    valid=[]
    for j,t in enumerate(bodies):
        if core_only and j!=core or t is None:
            continue
        stop = field_times[core]
        if side_policy=='independent' and field_times[j] is not None:
            stop = min(stop if stop is not None else math.inf,field_times[j])
        if stop is None or t<stop-1e-7:
            valid.append((t,j))
    first = min(valid) if valid else None
    return dict(hit=first is not None,body_time=first[0]if first else None,
                damage_sphere=first[1]if first else None,
                core_field_time=field_times[core],lifetime_end=float(frames[-1]),
                side_events=[dict(index=j,core=j==core,body_time=bodies[j],field_time=field_times[j])for j in range(k)])
