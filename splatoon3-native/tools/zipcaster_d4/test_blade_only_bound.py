import unittest
from tools.zipcaster_d4.calibration_plan_blade_only import lower_bound

class BoundTests(unittest.TestCase):
 def test_lower_bound_is_for_new_scope_and_programs(self):
  b=lower_bound();self.assertAlmostEqual(b['ground_best'],.301)
  self.assertGreater(b['one_hook_or_more'],b['ground_best'])
  for p,c in b['ground_program_bounds'].items():self.assertGreaterEqual(c,b['ground_best'])
  self.assertNotIn('full1',b['ground_program_bounds']);self.assertNotIn('light2',b['ground_program_bounds'])
 def test_grid_and_collision_clearance_need_two_travel_frames(self):
  self.assertEqual(lower_bound()['light_travel_minimum'],2)

if __name__=='__main__':unittest.main()
