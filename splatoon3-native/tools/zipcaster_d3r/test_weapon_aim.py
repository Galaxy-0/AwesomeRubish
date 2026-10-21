import unittest,math
from tools.zipcaster_d3r.weapon_aim import blade_angles
class AimTests(unittest.TestCase):
 def setUp(self):self.p=dict(full_origin_height=2.2,light_origin_height=1.,blade_target_height=1.1,blade_elevation_bias=0,blade_elevation_scale=1.)
 def test_full_emission_wait_keeps_full_muzzle(self):
  full=blade_angles([0,3,0],[0,3,10],self.p,style='full');light=blade_angles([0,3,0],[0,3,10],self.p,style='light');self.assertAlmostEqual(full[1],math.atan2(-1.1,10));self.assertAlmostEqual(light[1],math.atan2(.1,10));self.assertLess(full[1],light[1])
 def test_stage_string_cannot_be_a_style(self):
  for stage in['full-flight','light-flight','flight','']:
   with self.assertRaises(ValueError):blade_angles([0,0,0],[0,0,1],self.p,style=stage)
 def test_elevation_and_bounds(self):
  self.assertGreater(blade_angles([0,0,0],[0,5,10],self.p,style='full')[1],0);self.assertEqual(blade_angles([0,0,0],[0,100,0],self.p,style='light')[1],.85)
if __name__=='__main__':unittest.main()
