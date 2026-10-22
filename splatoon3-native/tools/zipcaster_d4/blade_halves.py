"""Ordered blade clipping, kept separate from unproved contact filtering.

The 11.3.0 shared projectile routine truncates from a consumed ball toward
that edge. This is stricter than independent balls; it preserves the opposite
side. Centre handling remains explicit because two native query arrays have
asymmetric centre branches. No contact-140 rule is inferred from this module.
"""
import numpy as np


def outward_stops(field_times, core, centre='both'):
    """First field event able to remove each ball, arbitrary batch prefixes.

    A left/upper ball j<core removes [0,j]. A right/lower ball j>core removes
    [j,n). 'both' conservatively stops both on core; 'positive' mirrors the
    first query-array branch (core removes [core,n)), for diagnostics only.
    Time ties fail closed in first_hit. Inputs include infinity for no event.
    """
    a=np.asarray(field_times,float)
    if a.ndim<1 or not 0<=core<a.shape[-1]:raise ValueError('core index')
    if centre not in ('both','positive'):raise ValueError('explicit centre policy')
    out=np.full_like(a,np.inf)
    for j in range(a.shape[-1]):
        if j<core:out[...,j]=np.min(a[...,j:core+(centre=='both')],axis=-1)
        else:out[...,j]=np.min(a[...,core:j+1],axis=-1)
    return out


def first_hit(body_times,field_times,core,centre='both'):
    body=np.asarray(body_times,float);stops=outward_stops(field_times,core,centre)
    valid=np.where(body<stops-1e-7,body,np.inf)
    return dict(hit=np.isfinite(valid).any(axis=-1),body_time=np.min(valid,axis=-1),
                damage_sphere=np.argmin(valid,axis=-1),stops=stops)
