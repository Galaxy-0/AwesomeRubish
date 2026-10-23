"""Exact barycentric floor support: ramps, true edges, stacked floors, ceilings."""

import unittest
import torch
from .geometry import Geometry


class GroundTests(unittest.TestCase):
    def geometry(self):
        g = Geometry.__new__(Geometry)
        # Two overlapping sloped/floating triangular floors. No navigation cells
        # are needed for testing support triangles themselves.
        g.arrays = dict(
            ground_origin=torch.tensor([0.0, 0.0]),
            ground_resolution=torch.tensor(1.0),
            ground_bins=torch.tensor([0, 1]).expand(3, 3, 2),
            ground_triangles=torch.tensor(
                [
                    [[0.0, 0.0, 0.0], [2.0, 1.0, 0.0], [0.0, 0.0, 2.0]],
                    [[0.0, 3.0, 0.0], [2.0, 3.0, 0.0], [0.0, 3.0, 2.0]],
                ]
            ),
        )
        return g

    def test_slope_uses_query_position_not_nearest_nav_height(self):
        g = self.geometry()
        p = torch.tensor([[0.2, 0.1, 0.2], [0.8, 0.4, 0.2], [1.2, 0.6, 0.2]])
        y, good = g.ground_candidates(p)
        self.assertTrue(good.all())
        torch.testing.assert_close(y[:, 0], p[:, 1])

    def test_triangle_edge_is_not_its_rectangular_bin(self):
        g = self.geometry()
        _, good = g.ground_candidates(
            torch.tensor([[1.9, 0.0, 0.8], [1.0, 0.0, 1.0], [3.0, 0.0, 0.0]])
        )
        self.assertEqual(good[:, 0].tolist(), [False, True, False])

    def test_stacked_surfaces_retained_for_below_ceiling_query(self):
        g = self.geometry()
        y, good = g.ground_candidates(torch.tensor([[0.2, 0.2, 0.2], [0.2, 3.0, 0.2]]))
        self.assertTrue(good.all())
        under = good & (y <= torch.tensor([0.405, 3.205])[:, None])
        torch.testing.assert_close(
            torch.where(under, y, -100.0).max(-1).values, torch.tensor([0.1, 3.0])
        )


class CudaGroundTests(unittest.TestCase):
    @unittest.skipUnless(torch.cuda.is_available(), "CUDA graph device required")
    def test_triangle_query_has_no_implicit_cpu_index_transfer(self):
        g = GroundTests().geometry()
        g.arrays = {k: v.cuda() for k, v in g.arrays.items()}
        p = torch.tensor([[0.2, 0.1, 0.2], [1.9, 0.0, 0.8]], device="cuda")
        stream = torch.cuda.Stream()
        stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            for _ in range(3):
                expected = g.ground_candidates(p)
        torch.cuda.current_stream().wait_stream(stream)
        graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):
            actual = g.ground_candidates(p)
        graph.replay()
        for a, b in zip(actual, expected):
            torch.testing.assert_close(a, b)


if __name__ == "__main__":
    unittest.main()
