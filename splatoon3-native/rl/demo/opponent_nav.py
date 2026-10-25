"""Terrain-only coverage memory for the demo bot; no live enemy/ink oracle."""

import math
import numpy as np
from arena.lib.atlas import MapAtlas


class NavigationAtlas(MapAtlas):
    """Identical weighted nearest vertex, vectorized on the demo side only."""

    def __init__(self, atlas):
        super().__init__(atlas.data)
        self._points = np.asarray(self.points, dtype=float)
        self._swimmable = np.asarray(self.swimmable, dtype=bool)

    def nearest(self, position, swim=False):
        delta = self._points - position
        distance = np.sum(delta * delta * [1, 4, 1], axis=1)
        if swim:
            distance = np.where(self._swimmable, distance, np.inf)
        return int(np.argmin(distance))


class CoverageRoute:
    def __init__(self, atlas):
        self.atlas = atlas
        points = np.asarray(atlas.points, float)
        # One actual traversable vertex per coarse cell, not a fabricated floor.
        cells = {}
        swimmable = getattr(atlas, "swimmable", [True] * len(points))
        for i, p in enumerate(points):
            if swimmable[i] and abs(p[0]) < 50 and abs(p[2]) < 96 and p[1] < 18:
                cells.setdefault(tuple(np.floor(p / [5, 3, 5]).astype(int)), p)
        self.points = np.asarray(list(cells.values()) or list(points), float)
        self.visits = np.zeros(len(self.points))
        self.blocked = {}
        self.goal = None
        self.goal_index = None
        self.last_mark = -10000

    def mark(self, pos, yaw, frame, firing, walking=True):
        if frame - self.last_mark < 12:
            return
        self.last_mark = frame
        delta = self.points - pos
        distance = np.linalg.norm(delta[:, [0, 2]], axis=1)
        if walking:
            self.visits[(distance < 3) & (abs(delta[:, 1]) < 2)] += 0.2
        if firing:
            angle = np.arctan2(delta[:, 0], delta[:, 2]) - yaw
            angle = np.arctan2(np.sin(angle), np.cos(angle))
            # This is an own-shot coverage estimate, never labelled native ink.
            self.visits[
                (distance < 13) & (abs(angle) < 0.25) & (abs(delta[:, 1]) < 3)
            ] += 0.5

    def choose(self, pos, frame, failed=False):
        if failed and self.goal_index is not None:
            self.blocked[self.goal_index] = frame + 1800
        delta = self.points - pos
        ds = np.linalg.norm(delta[:, [0, 2]], axis=1)
        # Prefer fresh nearby territory, rather than resetting a route to mid
        # after every spawn, or cycling four tiny centre points forever.
        candidates = np.flatnonzero((ds > 8) & (ds < 28) & (abs(delta[:, 1]) < 7))
        if not len(candidates):
            candidates = np.flatnonzero(ds > 4)
        scores = (
            (1 / (1 + self.visits)) * 12 - abs(ds - 15) * 0.15 - abs(delta[:, 1]) * 0.15
        )
        ranked = [
            i
            for i in sorted(candidates, key=lambda i: -scores[i])
            if self.blocked.get(int(i), 0) <= frame
        ]
        for i in ranked[:8]:
            if self.blocked.get(int(i), 0) > frame:
                continue
            q = self.points[i].tolist()
            try:
                path = self.atlas.route(pos, q)
            except ValueError:
                self.blocked[int(i)] = frame + 1800
                continue
            length = sum(math.dist(a, b) for a, b in zip(path, path[1:]))
            if length > max(15, ds[i] * 1.8):
                continue
            self.goal_index, self.goal = int(i), q
            # Reserve the destination so failed/short moves do not choose it
            # again immediately. Actual shot/visit updates do the rest.
            self.visits[i] += 1
            return q
        self.goal = list(self.atlas.objective())
        return self.goal
