"""Indexed static triangle queries and layered coarse Turf cells.

Ground and collision use A3 human triangles; sight uses A3 sight triangles.
Navigation nodes approximate paintable ground, not native scoring surface masks.
"""
import math
from collections import defaultdict

import numpy as np

from arena.geometry import CollisionMesh
from arena.lib.atlas import MapAtlas, STAGES
from .parameters import ROOT


class Mesh(CollisionMesh):
    def __init__(self, triangles, cell=8.):
        super().__init__(triangles)
        self.cell = cell
        self.bins = defaultdict(list)
        for i, (lo, hi) in enumerate(zip(self.low, self.high)):
            a = np.floor(lo[[0, 2]] / cell).astype(int)
            b = np.floor(hi[[0, 2]] / cell).astype(int)
            for x in range(a[0], b[0] + 1):
                for z in range(a[1], b[1] + 1):
                    self.bins[x, z].append(i)
        self.bins = {k: np.array(v, dtype=int) for k, v in self.bins.items()}

    def candidates(self, start, end):
        a = np.floor(np.minimum(start, end)[[0, 2]] / self.cell).astype(int)
        b = np.floor(np.maximum(start, end)[[0, 2]] / self.cell).astype(int)
        groups = [self.bins[x, z] for x in range(a[0], b[0] + 1)
                  for z in range(a[1], b[1] + 1) if (x, z) in self.bins]
        return np.unique(np.concatenate(groups)) if groups else np.empty(0, int)

    def hits(self, start, end, epsilon=.015):
        a, b = np.array(start, float), np.array(end, float)
        indices = self.candidates(a, b)
        if not len(indices):
            return np.empty(0)
        # Reuse the accepted double-sided segment intersection calculation.
        local = object.__new__(CollisionMesh)
        local.triangles = self.triangles[indices]
        local.low, local.high = self.low[indices], self.high[indices]
        return local.hits(a, b, epsilon)

    def floor(self, x, z, top=80., bottom=-30.):
        hits = self.hits((x, top, z), (x, bottom, z), .00001)
        return top - hits[0] if len(hits) else None

    def sweep(self, start, end, radius):
        """Conservative sampled sphere sweep (center and six axial lanes)."""
        a, b = np.asarray(start), np.asarray(end)
        # Endpoint sphere/triangle distance prevents a lane that already
        # overlaps a wall from moving deeper without crossing the plane again.
        if self.sphere_overlap(b, radius):
            return 0.
        best = math.inf
        for offset in ((0, 0, 0), (radius, 0, 0), (-radius, 0, 0),
                       (0, radius, 0), (0, -radius, 0), (0, 0, radius), (0, 0, -radius)):
            hits = self.hits(a + offset, b + offset, .00001)
            if len(hits):
                best = min(best, hits[0])
        return best

    def sphere_overlap(self, center, radius):
        center = np.asarray(center)
        ids = self.candidates(center - radius, center + radius)
        tri = self.triangles[ids]
        if not len(tri):
            return False
        keep = ((tri.min(axis=1) <= center + radius) &
                (tri.max(axis=1) >= center - radius)).all(axis=1)
        tri = tri[keep]
        if not len(tri):
            return False
        a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
        ab, ac = b - a, c - a
        n = np.cross(ab, ac)
        n2 = np.einsum('ij,ij->i', n, n)
        signed = np.einsum('ij,ij->i', center - a, n)
        projection = center - n * (signed / np.maximum(n2, 1e-20))[:, None]
        ap = projection - a
        aa = np.einsum('ij,ij->i', ab, ab)
        bb = np.einsum('ij,ij->i', ab, ac)
        cc = np.einsum('ij,ij->i', ac, ac)
        dd = np.einsum('ij,ij->i', ap, ab)
        ee = np.einsum('ij,ij->i', ap, ac)
        denom = np.maximum(aa * cc - bb * bb, 1e-20)
        u, v = (cc * dd - bb * ee) / denom, (aa * ee - bb * dd) / denom
        inside = (u >= 0) & (v >= 0) & (u + v <= 1) & (n2 > 1e-20)
        distance2 = np.where(inside, signed**2 / np.maximum(n2, 1e-20), np.inf)
        for lo, hi in ((a, b), (b, c), (c, a)):
            edge = hi - lo
            t = np.clip(np.einsum('ij,ij->i', center - lo, edge) /
                        np.maximum(np.einsum('ij,ij->i', edge, edge), 1e-20), 0, 1)
            difference = center - lo - t[:, None] * edge
            distance2 = np.minimum(distance2, np.einsum('ij,ij->i', difference, difference))
        return bool(np.any(distance2 < (radius - 1e-6)**2))


class Terrain:
    def __init__(self, atlas, human, sight):
        self.atlas, self.human, self.sight = atlas, human, sight
        self.points = np.array(atlas.points, float)
        self.paintable = np.array(atlas.swimmable, bool)
        self.cell_size = atlas.resolution
        self.columns = defaultdict(list)
        for i, p in enumerate(self.points):
            self.columns[self.key(p[0], p[2])].append(i)
        self.spawn = np.array([atlas.spawns[k]['ground'] for k in ('alpha', 'bravo')], float)
        normals = np.cross(human.triangles[:, 1]-human.triangles[:, 0], human.triangles[:, 2]-human.triangles[:, 0])
        # Same .7 walkable-normal threshold as A4 atlas construction. Ground
        # support is handled separately; a ramp must not be treated as a wall
        # merely because a foot sphere touches its supporting plane.
        walls = np.abs(normals[:, 1])/np.maximum(np.linalg.norm(normals, axis=1), 1e-12) < .7
        self.obstacles = Mesh(human.triangles[walls]) if walls.any() else None

    @classmethod
    def load(cls, stage_id):
        directory = ROOT / 'work/arena/maps' / STAGES[stage_id]
        return cls(MapAtlas.load(stage_id), Mesh.load(directory / 'human.npz'),
                   Mesh.load(directory / 'sight.npz'))

    def key(self, x, z):
        return int(math.floor(x / self.cell_size + .5)), int(math.floor(z / self.cell_size + .5))

    def cell_at(self, position, tolerance=.65):
        x, y, z = position
        indices = self.columns.get(self.key(x, z), ())
        if not indices:
            return None
        i = min(indices, key=lambda i: abs(self.points[i, 1] - y))
        return i if abs(self.points[i, 1] - y) <= tolerance and self.paintable[i] else None

    def move(self, position, delta, radius=.3, grounded=True, support_aware=False):
        """Slide against static walls; supported ramps/steps up to .2 units."""
        p = np.array(position, float)
        for axis in (0, 2):
            q = p.copy()
            q[axis] += delta[axis]
            floor = self.human.floor(q[0], q[2], p[1] + .205, p[1] - .5)
            target_y = floor if grounded and floor is not None else p[1]
            clear = True
            collision = self.obstacles if support_aware else self.human
            for height in (radius + .02, .7, 1.3):
                a = p + [0, height, 0]
                b = q + [0, height + max(0., target_y - p[1]), 0]
                if collision is not None and collision.sweep(a, b, radius) < math.inf:
                    clear = False
                    break
            if clear:
                p = q
                if grounded and floor is not None:
                    p[1] = floor
        return p


class Paint:
    def __init__(self, terrain):
        self.terrain = terrain
        self.owners = np.full(len(terrain.points), -1, dtype=np.int8)

    def at(self, position):
        cell = self.terrain.cell_at(position)
        return int(self.owners[cell]) if cell is not None else -1

    def disk(self, center, radius, team):
        """Layer-aware disk; walls block spreading, same-team repaint earns zero."""
        t = self.terrain
        x, y, z = center
        indices = []
        a, b = t.key(x - radius, z - radius), t.key(x + radius, z + radius)
        for ix in range(a[0], b[0] + 1):
            for iz in range(a[1], b[1] + 1):
                indices.extend(t.columns.get((ix, iz), ()))
        if not indices:
            return 0.
        ids = np.array(indices)
        points = t.points[ids]
        keep = (t.paintable[ids] & (np.abs(points[:, 1] - y) < .6) &
                (np.sum((points[:, [0, 2]] - [x, z])**2, axis=1) <= radius**2) &
                (self.owners[ids] != team))
        ids = ids[keep]
        ids = [i for i in ids if t.sight.clear(np.array(center) + [0, .1, 0],
                                               t.points[i] + [0, .1, 0])]
        self.owners[ids] = team
        return len(ids) * t.cell_size**2

    def ratios(self):
        valid = self.terrain.paintable
        total = int(valid.sum())
        return [float(np.count_nonzero((self.owners == i) & valid) / total)
                if total else 0. for i in range(2)]
