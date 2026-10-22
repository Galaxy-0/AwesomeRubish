"""Vectorized first-body/field comparison for exhaustive finite aim scans.

Field-radius endpoint bounds are explicit. They are not a claim to have
recovered the game's per-update interpolation or multi-sphere consumption.
"""
import numpy as np


def segment_box_distances(a,b,center,half):
    a,b,center,half=map(lambda x:np.asarray(x,float),(a,b,center,half))
    a,d=a-center,b-a
    safe=np.where(np.abs(d)>1e-15,d,1.)
    cuts=np.concatenate([np.zeros(a.shape[:-1]+(1,)),np.ones(a.shape[:-1]+(1,)),
                         np.clip((-half-a)/safe,0,1),np.clip((half-a)/safe,0,1)],axis=-1)
    cuts.sort(axis=-1)
    def sq(t):return np.sum(np.maximum(np.abs(a[...,None,:]+t[...,None]*d[...,None,:])-half,0)**2,axis=-1)
    mid=(cuts[...,:-1]+cuts[...,1:])/2
    point=a[...,None,:]+mid[...,None]*d[...,None,:]
    active=np.abs(point)>half
    q=a[...,None,:]-np.sign(point)*half
    dd=np.sum(np.where(active,d[...,None,:]**2,0),axis=-1)
    opt=-np.sum(np.where(active,d[...,None,:]*q,0),axis=-1)/np.maximum(dd,1e-300)
    opt=np.clip(opt,cuts[...,:-1],cuts[...,1:])
    return np.sqrt(np.minimum(np.min(sq(cuts),axis=-1),np.min(sq(opt),axis=-1)))


def segment_cylinder_distances(a,b,ca,cb,radius):
    a,b,ca,cb=map(lambda x:np.asarray(x,float),(a,b,ca,cb))
    axis=cb-ca;length=np.linalg.norm(axis)
    if length<1e-12:raise ValueError('finite cylinder axis')
    axis/=length;center=(ca+cb)/2
    def sq(t):
        p=a+t[...,None]*(b-a)-center
        axial=p@axis
        radial=np.linalg.norm(p-axial[...,None]*axis,axis=-1)
        return np.maximum(np.abs(axial)-length/2,0)**2+np.maximum(radial-radius,0)**2
    left,right=np.zeros(a.shape[:-1]),np.ones(a.shape[:-1]);phi=(np.sqrt(5)-1)/2
    for _ in range(72):
        x,y=right-phi*(right-left),left+phi*(right-left)
        choose=sq(x)<=sq(y)
        right,left=np.where(choose,y,right),np.where(choose,left,x)
    return np.sqrt(np.minimum.reduce([sq(left),sq(right),sq(np.zeros_like(left)),sq(np.ones_like(right))]))


def capsule_axis_distance(a, b, low=.35, high=1.30):
    """Exact finite segment-to-vertical-axis distance, batched."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    u = b-a
    w = a.copy()
    w[..., 1] -= low
    height = high-low
    aa, bb = np.sum(u*u, axis=-1), u[..., 1]*height
    cc = height*height
    dd, ee = np.sum(u*w, axis=-1), w[..., 1]*height
    den = aa*cc-bb*bb
    s = np.where(den > 1e-15, np.clip((bb*ee-cc*dd)/np.maximum(den, 1e-300),0,1), 0.)
    t = (bb*s+ee)/cc
    s = np.where(t < 0, np.clip(-dd/np.maximum(aa, 1e-300),0,1), s)
    s = np.where(t > 1, np.clip((bb-dd)/np.maximum(aa, 1e-300),0,1), s)
    t = np.clip(t,0,1)
    q = w+s[...,None]*u
    q[...,1] -= t*height
    return np.linalg.norm(q, axis=-1)


def capsule_fractions(a, b, radius, low=.35, high=1.30):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b-a
    near = a.copy()
    near[..., 1] -= np.clip(a[..., 1], low, high)
    out = np.where(np.sum(near*near, axis=-1) <= radius*radius, 0., np.inf)
    aa = d[..., 0]**2+d[..., 2]**2
    bb = a[..., 0]*d[..., 0]+a[..., 2]*d[..., 2]
    cc = a[..., 0]**2+a[..., 2]**2-radius*radius
    disc = bb*bb-aa*cc
    root = (-bb-np.sqrt(np.maximum(disc, 0)))/np.maximum(aa, 1e-300)
    height = a[..., 1]+root*d[..., 1]
    valid = (aa > 1e-15)&(disc >= 0)&(root >= 0)&(root <= 1)&(height >= low)&(height <= high)
    out = np.minimum(out, np.where(valid, root, np.inf))
    aa = np.sum(d*d, axis=-1)
    for y in (low, high):
        q = a.copy()
        q[..., 1] -= y
        bb = np.sum(q*d, axis=-1)
        cc = np.sum(q*q, axis=-1)-radius*radius
        disc = bb*bb-aa*cc
        root = (-bb-np.sqrt(np.maximum(disc, 0)))/np.maximum(aa, 1e-300)
        valid = (aa > 1e-15)&(disc >= 0)&(root >= 0)&(root <= 1)
        out = np.minimum(out, np.where(valid, root, np.inf))
    return out


def trace_batch(field, points, frames, enemies, rotations, collision, radius_bound='initial'):
    """P traces, T recorded poses and K parameter balls; no wall-clear credit."""
    if radius_bound not in ('initial', 'end'):
        raise ValueError('explicit field-radius bound')
    points, enemies, rotations = map(lambda x: np.asarray(x, float), (points, enemies, rotations))
    frames = np.asarray(frames, float)
    offsets = np.array([[o[k] for k in ('X', 'Y', 'Z')] for o in collision['OffsetArray']])
    offsets = np.einsum('pij,kj->pki', rotations, offsets)
    starts = points[:, :-1, None, :]+offsets[:, None, :, :]
    ends = points[:, 1:, None, :]+offsets[:, None, :, :]
    lengths = np.linalg.norm(ends-starts, axis=-1)
    directions = (ends-starts)/np.maximum(lengths[..., None], 1e-15)
    field_key = 'InitRadiusForField' if radius_bound == 'initial' else 'EndRadiusForField'
    radii = np.array([r.get(field_key, r['InitRadiusForField']) for r in collision['ParamArray']])
    rs = np.broadcast_to(radii, lengths.shape)
    ids, _, dist = field.sphere(starts.reshape(-1, 3), directions.reshape(-1, 3), rs.reshape(-1), np.maximum(lengths.reshape(-1), 1e-12))
    dist, ids = dist.reshape(lengths.shape), ids.reshape(lengths.shape)
    delta_t = np.diff(frames)[None, :, None]
    field_times = frames[None, :-1, None]+delta_t*dist/np.maximum(lengths, 1e-15)
    field_times = np.min(np.where(ids >= 0, field_times, np.inf), axis=1)
    player_r = .35+np.array([r['InitRadiusForPlayer'] for r in collision['ParamArray']])
    fraction = capsule_fractions(starts-enemies[:, :-1, None, :], ends-enemies[:, 1:, None, :], player_r)
    body_times = np.min(frames[None, :-1, None]+delta_t*fraction, axis=1)
    core = collision['CoreIndex']
    clipped = np.where(body_times < np.minimum(field_times, field_times[:, core, None])-1e-7, body_times, np.inf)
    uncut = np.where(body_times < field_times[:, core, None]-1e-7, body_times, np.inf)
    first = np.min(clipped, axis=1)
    return dict(hit=np.isfinite(first), body_time=first, damage_sphere=np.argmin(clipped, axis=1),
                core_hit=body_times[:, core] < field_times[:, core]-1e-7,
                assembly_uncertain=np.isfinite(first) != np.isfinite(np.min(uncut, axis=1)),
                field_times=field_times, body_times=body_times, radius_bound=radius_bound)
