"""Vectorized contact tests, explicit stage0 geometric approximations.

Field collision uses the private 1u surface grid, not the native physics mesh.
Player contacts use a vertical capsule. Boxes use capsule-expanded AABBs in
local coordinates (conservative at corners); cylinders use segment distance.
"""

import torch


def segment_distance(a, b, p, q):
    u = b - a
    v = q - p
    w = a - p
    aa = (u * u).sum(-1)
    bb = (u * v).sum(-1)
    cc = (v * v).sum(-1)
    dd = (u * w).sum(-1)
    ee = (v * w).sum(-1)
    den = aa * cc - bb * bb
    s = torch.where(
        den > 1e-10, (bb * ee - cc * dd) / den.clamp_min(1e-10), torch.zeros_like(den)
    ).clamp(0, 1)
    t = (bb * s + ee) / cc.clamp_min(1e-10)
    s = torch.where(t < 0, (-dd / aa.clamp_min(1e-10)).clamp(0, 1), s)
    s = torch.where(t > 1, ((bb - dd) / aa.clamp_min(1e-10)).clamp(0, 1), s)
    t = t.clamp(0, 1)
    # Handle either zero-length segment explicitly.
    s = torch.where(cc < 1e-10, (-dd / aa.clamp_min(1e-10)).clamp(0, 1), s)
    t = torch.where(aa < 1e-10, (ee / cc.clamp_min(1e-10)).clamp(0, 1), t)
    return (w + s[..., None] * u - t[..., None] * v).norm(dim=-1)


def capsule_first(a, b, foot, radius):
    """Earliest fraction against a vertical capsule, inf when no intersection."""
    a = a - foot
    b = b - foot
    d = b - a
    near = a.clone()
    near[..., 1] -= a[..., 1].clamp(0.35, 1.3)
    inside = (near * near).sum(-1) <= radius * radius
    aa = d[..., 0].square() + d[..., 2].square()
    bb = a[..., 0] * d[..., 0] + a[..., 2] * d[..., 2]
    cc = a[..., 0].square() + a[..., 2].square() - radius * radius
    disc = bb * bb - aa * cc
    t = (-bb - disc.clamp_min(0).sqrt()) / aa.clamp_min(1e-12)
    y = a[..., 1] + t * d[..., 1]
    hit = (disc >= 0) & (aa > 1e-12) & (t >= 0) & (t <= 1) & (y >= 0.35) & (y <= 1.3)
    out = torch.where(hit, t, float("inf"))
    for height in (0.35, 1.3):
        w = a.clone()
        w[..., 1] -= height
        aa = (d * d).sum(-1)
        bb = (w * d).sum(-1)
        cc = (w * w).sum(-1) - radius * radius
        disc = bb * bb - aa * cc
        t = (-bb - disc.clamp_min(0).sqrt()) / aa.clamp_min(1e-12)
        out = torch.minimum(
            out,
            torch.where(
                (disc >= 0) & (aa > 1e-12) & (t >= 0) & (t <= 1), t, float("inf")
            ),
        )
    return torch.where(inside, 0.0, out)
