import unittest
import numpy as np
from tools.zipcaster_d4.geometry import Mesh
from tools.zipcaster_d4.attack_geometry import capsule_fraction, basis, trace_contacts
from tools.zipcaster_d4.attack_batch import (capsule_fractions, trace_batch, capsule_axis_distance,
    segment_box_distances,segment_cylinder_distances)
from tools.zipcaster_d4.attack_geometry import segment_box_distance,segment_cylinder_distance
from tools.zipcaster_d4.model_v2 import segment_distance


class BatchTests(unittest.TestCase):
    def test_box_cylinder_batches_match_exact_scalar_shapes(self):
        rng=np.random.default_rng(281006);a,b=rng.uniform(-3,3,(2,300,3));b[:10]=a[:10]
        got=segment_box_distances(a,b,[.1,.2,.3],[.5,1.4,.7])
        expected=[segment_box_distance(x,y,[.1,.2,.3],[.5,1.4,.7])for x,y in zip(a,b)]
        np.testing.assert_allclose(got,expected,atol=1e-10)
        got=segment_cylinder_distances(a,b,[-.5,0,2.1],[.5,0,2.1],1.4)
        expected=[segment_cylinder_distance(x,y,[-.5,0,2.1],[.5,0,2.1],1.4)for x,y in zip(a,b)]
        np.testing.assert_allclose(got,expected,atol=1e-9)
    def test_axis_distances_match_scalar(self):
        rng=np.random.default_rng(281005)
        a,b=rng.uniform(-3,3,(2,2000,3));b[:30]=a[:30]
        got=capsule_axis_distance(a,b)
        expected=[segment_distance(x,y,np.array([0,.35,0]),np.array([0,1.30,0]))for x,y in zip(a,b)]
        np.testing.assert_allclose(got,expected,atol=1e-10)
    def test_capsule_batch_matches_scalar_including_degenerate_motion(self):
        rng = np.random.default_rng(281004)
        a, b = rng.uniform(-3, 3, (2, 2000, 3))
        b[:30] = a[:30]
        radius = rng.uniform(.1, 1., 2000)
        batched = capsule_fractions(a, b, radius)
        expected = np.array([capsule_fraction(x, y, r) for x, y, r in zip(a, b, radius)], dtype=float)
        expected[np.isnan(expected)] = np.inf
        np.testing.assert_allclose(batched, expected, atol=1e-10)

    def test_first_body_field_and_side_policy_match_scalar(self):
        wall = Mesh([[[.7,-1,4],[1.3,-1,4],[.7,3,4]],[[1.3,-1,4],[1.3,3,4],[.7,3,4]]])
        col = dict(CoreIndex=0, OffsetArray=[dict(X=0,Y=0,Z=0),dict(X=1,Y=0,Z=0)],
                   ParamArray=[dict(InitRadiusForField=.1,InitRadiusForPlayer=.1)]*2)
        points = np.array([[[0,1,0],[0,1,10]]]*3, float)
        enemies = np.array([[[1,0,8]]*2, [[0,0,3]]*2, [[0,8,8]]*2], float)
        matrices = np.array([basis(0,0)]*3)
        out = trace_batch(wall, points, [0,6], enemies, matrices, col)
        for i in range(3):
            scalar = trace_contacts(wall, points[i], [0,6], enemies[i], 0,0,col)
            uncut = trace_contacts(wall, points[i], [0,6], enemies[i], 0,0,col,side_policy='core_lifetime')
            self.assertEqual(out['hit'][i], scalar['hit'])
            self.assertEqual(out['assembly_uncertain'][i], scalar['hit'] != uncut['hit'])
            if scalar['hit']:
                self.assertAlmostEqual(out['body_time'][i], scalar['body_time'])


if __name__ == '__main__':
    unittest.main()
