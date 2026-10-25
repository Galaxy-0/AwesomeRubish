"""Coverage uses only static traversable vertices and own-action history."""

import unittest
import numpy as np
from .opponent_nav import CoverageRoute, NavigationAtlas
from arena.lib.atlas import MapAtlas


class FlatAtlas:
    points = [(x, 0, z) for x in range(-20, 21, 5) for z in range(-20, 21, 5)]
    swimmable = [True] * len(points)

    def route(self, start, end):
        return [start, end]

    def objective(self):
        return (0, 0, 0)


class CoverageTests(unittest.TestCase):
    def test_vector_nearest_preserves_weighted_height_swim_and_ties(self):
        a = MapAtlas(
            dict(
                schema="arena.map.v1",
                nodes=[[-1, 0, 0, True], [1, 0, 0, True], [0, 1, 0, False]],
                edges=[[1], [0], []],
                regions={},
                spawns={},
                resolution=1,
            )
        )
        b = NavigationAtlas(a)
        for point in ([0, 0, 0], [0, 1, 0], [1.4, 0.3, -2], [-2, 1, 0]):
            for swim in (False, True):
                self.assertEqual(a.nearest(point, swim), b.nearest(point, swim))

    def test_only_own_forward_spray_marks_estimated_coverage(self):
        c = CoverageRoute(FlatAtlas())
        c.mark(np.array([0, 0, 0]), 0, 0, True)
        forward = np.flatnonzero(np.all(c.points == [0, 0, 10], axis=1))[0]
        behind = np.flatnonzero(np.all(c.points == [0, 0, -10], axis=1))[0]
        self.assertGreater(c.visits[forward], 0)
        self.assertEqual(c.visits[behind], 0)
        self.assertTrue(np.all(c.points == np.array(FlatAtlas.points)))

    def test_failed_goal_is_temporarily_excluded(self):
        c = CoverageRoute(FlatAtlas())
        q = c.choose([0, 0, 0], 0)
        self.assertIn(tuple(q), FlatAtlas.points)
        index = c.goal_index
        c.choose([0, 0, 0], 100, failed=True)
        self.assertNotEqual(c.goal_index, index)
        self.assertGreater(c.blocked[index], 100)
