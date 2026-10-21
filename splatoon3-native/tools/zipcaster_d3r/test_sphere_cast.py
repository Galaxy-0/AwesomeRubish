import unittest,numpy as np
from tools.zipcaster_d3r.sphere_cast import first_sphere_hit
class SphereTests(unittest.TestCase):
 def test_face_and_nearest(self):
  t=np.array([[[-2,-2,5],[2,-2,5],[0,2,5]],[[-2,-2,8],[2,-2,8],[0,2,8]]]);i,p,d=first_sphere_hit(t,[0,0,0],[0,0,1],.3,10);self.assertEqual(i,0);np.testing.assert_allclose(p,[0,0,5],atol=1e-8);self.assertAlmostEqual(d,4.7)
 def test_edge_near_miss_and_zero_radius(self):
  t=np.array([[[-2,0,5],[2,0,5],[0,-2,5]]]);self.assertIsNone(first_sphere_hit(t,[0,.2,0],[0,0,1],0,10));i,p,d=first_sphere_hit(t,[0,.2,0],[0,0,1],.3,10);np.testing.assert_allclose(p,[0,0,5],atol=1e-8);self.assertAlmostEqual(d,5-np.sqrt(.3**2-.2**2))
 def test_vertex_and_direction_normalization(self):
  t=np.array([[[0,0,5],[-2,-2,5],[2,-2,5]]]);i,p,d=first_sphere_hit(t,[.1,.2,0],[0,0,20],.3,10);np.testing.assert_allclose(p,[0,0,5],atol=1e-8);self.assertAlmostEqual(d,4.8)
 def test_far_and_behind(self):
  t=np.array([[[-2,-2,-5],[2,-2,-5],[0,2,-5]]]);self.assertIsNone(first_sphere_hit(t,[0,0,0],[0,0,1],.3,10))
if __name__=='__main__':unittest.main()
