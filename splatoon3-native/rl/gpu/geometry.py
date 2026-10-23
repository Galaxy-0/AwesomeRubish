"""Torch-only private voxel queries; no native host dependency."""

from pathlib import Path
import math
import numpy as np
import torch


class Geometry:
    def __init__(self, path, device, fast_rays=False):
        with np.load(Path(path) / "map.npz", allow_pickle=False) as a:
            self.arrays = {
                k: torch.as_tensor(a[k].copy(), device=device) for k in a.files
            }
        a = self.arrays
        self.dims = tuple(a["voxels"].shape)
        self.vox = a["voxels"].flatten()
        self.normal = a["normals"].reshape(-1, 3).float()
        self.planes = a["planes"].flatten()
        self.fast_rays = fast_rays
        if fast_rays:
            from .raycast_cuda import voxel_ray

            self.cuda_ray = voxel_ray
        self.floor = a["floors"]
        self.ids = a["cell_ids"]
        self.shape = self.floor.shape[:2]
        self.origin = a["voxel_origin"]
        self.res = float(a["voxel_resolution"].item())
        self.grid_origin = a["grid_origin"]
        self.points = a["points"]
        self.spawn = a["spawn"]
        self.paintable = a["paintable"]
        self.map_top = self.ids.gather(
            -1, (self.ids >= 0).sum(-1).sub(1).clamp_min(0).unsqueeze(-1)
        ).squeeze(-1)

    def column(self, p):
        x = torch.round(p[..., 0] - self.grid_origin[0]).long()
        z = torch.round(p[..., 2] - self.grid_origin[1]).long()
        valid = (x >= 0) & (x < self.shape[0]) & (z >= 0) & (z < self.shape[1])
        x = x.clamp(0, self.shape[0] - 1)
        z = z.clamp(0, self.shape[1] - 1)
        return self.floor[x, z], self.ids[x, z], valid

    def support(self, p, top_offset=0.205):
        y, ids, valid = self.column(p)
        good = (ids >= 0) & (y <= p[..., 1, None] + top_offset) & valid[..., None]
        yy = torch.where(good, y, -100.0)
        floor, layer = yy.max(-1)
        cell = ids.gather(-1, layer[..., None]).squeeze(-1)
        return floor, torch.where(good.any(-1), cell, -1)

    def cell(self, p):
        y, ids, valid = self.column(p)
        delta = (y - p[..., 1, None]).abs()
        layer = delta.argmin(-1)
        cell = ids.gather(-1, layer[..., None]).squeeze(-1)
        return torch.where(
            valid & (delta.min(-1).values <= 0.65) & (cell >= 0), cell, -1
        )

    def _index(self, p):
        grid = torch.round((p - self.origin) / self.res).long()
        x, y, z = grid.unbind(-1)
        valid = (
            (x >= 0)
            & (x < self.dims[0])
            & (y >= 0)
            & (y < self.dims[1])
            & (z >= 0)
            & (z < self.dims[2])
        )
        index = (
            x.clamp(0, self.dims[0] - 1) * self.dims[1] + y.clamp(0, self.dims[1] - 1)
        ) * self.dims[2] + z.clamp(0, self.dims[2] - 1)
        return index, valid

    def lookup(self, p):
        index, valid = self._index(p)
        return torch.where(valid, self.vox[index], 0), self.normal[index]

    def sweep(self, a, b, samples=4, radius=0.0):
        # Intersect the surface plane represented by each visited voxel; a
        # voxel's thickness is not a solid wall/ground collision volume.
        out = torch.full_like((b - a)[..., 0], float("inf"))
        d = b - a
        for step in range(samples + 1):
            p = a + d * (step / samples)
            g = torch.round((p - self.origin) / self.res).long()
            x, y, z = g.unbind(-1)
            valid = (
                (x >= 0)
                & (x < self.dims[0])
                & (y >= 0)
                & (y < self.dims[1])
                & (z >= 0)
                & (z < self.dims[2])
            )
            idx = (
                x.clamp(0, self.dims[0] - 1) * self.dims[1]
                + y.clamp(0, self.dims[1] - 1)
            ) * self.dims[2] + z.clamp(0, self.dims[2] - 1)
            normal = self.normal[idx]
            den = (d * normal).sum(-1)
            signed = (a * normal).sum(-1) - self.planes[idx]
            num = self.planes[idx] + signed.sign() * radius - (a * normal).sum(-1)
            t = num / torch.where(den.abs() > 1e-8, den, torch.ones_like(den))
            at = a + d * t[..., None]
            center = self.origin + g * self.res
            hit = (
                valid
                & (self.vox[idx] > 0)
                & (den.abs() > 1e-8)
                & (t >= 0)
                & (t <= 1)
                & (
                    (at - center).abs()
                    <= self.res * 0.55
                    + (
                        radius[..., None]
                        if isinstance(radius, torch.Tensor)
                        else radius
                    )
                ).all(-1)
            )
            out = torch.minimum(out, torch.where(hit, t, float("inf")))
        return out

    def ray(self, origin, direction, distance=64.0, stride=0.75):
        if self.fast_rays:
            return self.cuda_ray(
                self.vox,
                self.normal,
                origin,
                direction,
                self.origin,
                list(self.dims),
                self.res,
                float(distance),
                float(stride),
            )
        # Fixed work count supports GPU graph capture, including empty scenes.
        length = torch.full_like(direction[..., 0], distance)
        kind = torch.zeros_like(length, dtype=torch.int64)
        normal = torch.zeros_like(direction)
        for step in range(1, math.ceil(distance / stride) + 1):
            t = min(distance, step * stride)
            code, n = self.lookup(origin + direction * t)
            hit = (kind == 0) & (code > 0)
            length = torch.where(hit, t, length)
            kind = torch.where(hit, code.long(), kind)
            normal = torch.where(hit[..., None], n, normal)
        return length, kind, normal

    def clear(self, a, b, samples=12, wall_only=False):
        blocked = torch.zeros_like((b - a)[..., 0], dtype=torch.bool)
        for i in range(1, samples):
            code, _ = self.lookup(a + (b - a) * (i / samples))
            blocked |= ((code & 3) == 2) if wall_only else (code > 0)
        return ~blocked

    def color(self, paint, p):
        cell = self.cell(p)
        flat = cell.reshape(paint.shape[0], -1)
        value = paint.gather(1, flat.clamp_min(0)).reshape(cell.shape)
        return torch.where(cell >= 0, value, -1)


def basis(yaw, pitch):
    cy, sy = torch.cos(yaw), torch.sin(yaw)
    cp, sp = torch.cos(pitch), torch.sin(pitch)
    zero = torch.zeros_like(yaw)
    forward = torch.stack([sy * cp, sp, cy * cp], -1)
    right = torch.stack([cy, zero, -sy], -1)
    up = torch.cross(forward, right, dim=-1)
    return forward, right, up
