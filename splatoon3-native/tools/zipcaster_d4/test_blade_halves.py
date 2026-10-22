import unittest
import numpy as np
from tools.zipcaster_d4.blade_halves import outward_stops,first_hit

class OrderedClipping(unittest.TestCase):
 def test_inner_upper_removes_outer_upper_only(self):
  a=[np.inf]*7;a[1]=2
  np.testing.assert_array_equal(outward_stops(a,3),[2,2,np.inf,np.inf,np.inf,np.inf,np.inf])
 def test_lower_block_leaves_upper_damage(self):
  a=[np.inf]*7;a[4]=1
  r=first_hit([3]+[np.inf]*6,a,3)
  self.assertTrue(r['hit']);self.assertEqual(r['damage_sphere'],0)
 def test_blocked_inner_removes_outer_target_ball(self):
  a=[np.inf]*5;a[1]=1
  self.assertFalse(first_hit([3]+[np.inf]*4,a,2)['hit'])
 def test_centre_branch_is_explicit(self):
  a=[np.inf]*7;a[3]=1
  np.testing.assert_array_equal(outward_stops(a,3,'positive'),[np.inf]*3+[1]*4)
  self.assertFalse(first_hit([3]+[np.inf]*6,a,3)['hit'])
 def test_batched_ties_and_symmetry(self):
  a=np.array([[np.inf,2,np.inf,np.inf,np.inf],[np.inf,np.inf,np.inf,2,np.inf]])
  stops=outward_stops(a,2)
  np.testing.assert_array_equal(stops[0],stops[1][::-1])
  self.assertFalse(first_hit([2,np.inf,np.inf,np.inf,np.inf],a[0],2)['hit'])

if __name__=='__main__':unittest.main()
