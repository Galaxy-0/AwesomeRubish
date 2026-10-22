import unittest,numpy as np
from tools.zipcaster_d4.model_v2 import World,Config
from tools.zipcaster_d4.geometry import Mesh
class LaunchSweepTests(unittest.TestCase):
 def test_birth_offset_must_not_skip_wall_corner(self):
  w=object.__new__(World);w.cfg=Config();w.attack_parameters=dict(blade_elevation_bias=0.,blade_elevation_scale=1.);w.graph={'ground':np.array([[.6,0.,0.]])};enemy=np.array([-6.,0.,4.]);w.field=Mesh(np.empty((0,3,3)));self.assertIsNotNone(w.terminal(0,enemy,40,'full-light',ground=True))
  # Full muzzle is above the wall, but light launch crosses its near edge
  # before the nominal1.4u birth offset. A post-birth-only ray invents aKO.
  w.field=Mesh([[[0,0,-2],[0,1.5,-2],[0,0,1]],[[0,1.5,-2],[0,1.5,1],[0,0,1]]]);self.assertIsNone(w.terminal(0,enemy,40,'full-light',ground=True))
 def test_activation_budget_includes_one_plus_thirty_native_frames(self):
  self.assertEqual(Config().activation_frames,31)
if __name__=='__main__':unittest.main()
