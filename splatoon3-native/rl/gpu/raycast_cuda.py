"""Optional fused voxel rays, numerically checked against Torch before use.

This is an inference environment kernel, not a training kernel. Registered as
an opaque PyTorch op so Inductor does not unroll64 voxel-gather subgraphs.
"""

import math
import torch
import triton
import triton.language as tl
from triton.language.extra import libdevice


@triton.jit
def _rays(
    V,
    N,
    O,
    D,
    G,
    Lengths,
    Kinds,
    Normals,
    COUNT: tl.constexpr,
    DX: tl.constexpr,
    DY: tl.constexpr,
    DZ: tl.constexpr,
    RES: tl.constexpr,
    DIST: tl.constexpr,
    STRIDE: tl.constexpr,
    STEPS: tl.constexpr,
    BLOCK: tl.constexpr,
):
    i = tl.program_id(0) * BLOCK + tl.arange(0, BLOCK)
    valid = i < COUNT
    ox = tl.load(O + i * 3, valid, 0)
    oy = tl.load(O + i * 3 + 1, valid, 0)
    oz = tl.load(O + i * 3 + 2, valid, 0)
    dx = tl.load(D + i * 3, valid, 0)
    dy = tl.load(D + i * 3 + 1, valid, 0)
    dz = tl.load(D + i * 3 + 2, valid, 0)
    gx = tl.load(G)
    gy = tl.load(G + 1)
    gz = tl.load(G + 2)
    found = ~valid
    kind = tl.full((BLOCK,), 0, tl.int64)
    distance = tl.full((BLOCK,), DIST, tl.float32)
    first = tl.full((BLOCK,), 0, tl.int32)
    step = 1
    while (step <= STEPS) & (tl.sum((~found).to(tl.int32), 0) > 0):
        t = tl.minimum(DIST, step * STRIDE)
        x = libdevice.nearbyint((ox + dx * t - gx) / RES).to(tl.int32)
        y = libdevice.nearbyint((oy + dy * t - gy) / RES).to(tl.int32)
        z = libdevice.nearbyint((oz + dz * t - gz) / RES).to(tl.int32)
        inside = (
            (x >= 0) & (x < DX) & (y >= 0) & (y < DY) & (z >= 0) & (z < DZ) & ~found
        )
        index = (x * DY + y) * DZ + z
        code = tl.load(V + index, inside, 0).to(tl.int64)
        hit = inside & (code > 0)
        kind = tl.where(hit, code, kind)
        distance = tl.where(hit, t, distance)
        first = tl.where(hit, index, first)
        found |= hit
        step += 1
    tl.store(Lengths + i, distance, valid)
    tl.store(Kinds + i, kind, valid)
    for axis in tl.static_range(3):
        n = tl.load(N + first * 3 + axis, valid & (kind > 0), 0)
        tl.store(Normals + i * 3 + axis, n, valid)


@torch.library.custom_op("inklab::voxel_ray", mutates_args=())
def voxel_ray(
    vox: torch.Tensor,
    normal: torch.Tensor,
    origin: torch.Tensor,
    direction: torch.Tensor,
    grid_origin: torch.Tensor,
    dims: list[int],
    resolution: float,
    distance: float,
    stride: float,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    o = origin.expand_as(direction).contiguous()
    d = direction.contiguous()
    length = torch.empty_like(direction[..., 0])
    kind = torch.empty_like(length, dtype=torch.int64)
    n = torch.empty_like(direction)
    count = length.numel()
    _rays[(triton.cdiv(count, 128),)](
        vox,
        normal,
        o,
        d,
        grid_origin,
        length,
        kind,
        n,
        count,
        *dims,
        resolution,
        distance,
        stride,
        math.ceil(distance / stride),
        128,
    )
    return length, kind, n


@voxel_ray.register_fake
def _(vox, normal, origin, direction, grid_origin, dims, resolution, distance, stride):
    return (
        torch.empty_like(direction[..., 0]),
        torch.empty_like(direction[..., 0], dtype=torch.int64),
        torch.empty_like(direction),
    )
