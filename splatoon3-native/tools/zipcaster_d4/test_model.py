import math,unittest,numpy as np
from tools.zipcaster_d4.model import World,Config,schedule,capsule_hit_fraction,damage_at_distance
from tools.zipcaster_d4.geometry import Mesh
class ModelTests(unittest.TestCase):
 def test_moving_capsule_contact_precedes_wall_behind_body(self):
  f=capsule_hit_fraction([-2,1,0],[2,1,0]);self.assertAlmostEqual(f,(2-.635)/4);self.assertLess(f,.9)
 def test_capsule_caps_grazing_and_degenerate(self):
  self.assertIsNone(capsule_hit_fraction([-2,2,0],[2,2,0]));self.assertIsNotNone(capsule_hit_fraction([-2,1.9,0],[2,1.9,0]));self.assertEqual(capsule_hit_fraction([0,1,0],[0,1,0]),0.)
 def test_fixed_half_plane_and_view_distance(self):
  w=object.__new__(World);w.cfg=Config();w.vision=Mesh(np.empty((0,3,3)));path=np.array([[0,0,5],[0,0,-5],[5,0,0],[0,0,31]],float);v,d=w.visibility(path,np.zeros(3),0);self.assertEqual(v.tolist(),[True,False,True,False]);v,_=w.visibility(path,np.zeros(3),math.pi);self.assertEqual(v.tolist(),[False,True,True,False])
 def test_visibility_still_needs_geometry(self):
  w=object.__new__(World);w.cfg=Config();w.vision=Mesh([[[-3,-1,2],[3,-1,2],[-3,5,2]],[[3,-1,2],[3,5,2],[-3,5,2]]]);v,d=w.visibility(np.array([[0,0,5]],float),np.zeros(3),0);self.assertFalse(v[0])
 def test_stationary_prefix_prune_requires_actual_two_shot_contact(self):
  w=object.__new__(World);w.cfg=Config();w.vision=Mesh(np.empty((0,3,3)));w.field=Mesh(np.empty((0,3,3)));w.flight={'windup_coefficients':[23.,.4]};w.graph={'ground':np.array([[0.,0.,5.],[0.,0.,-5.]]),'edge_source':np.array([0,1]),'edge_distance':np.array([10.,10.])}
  self.assertIsNotNone(w.initial_stationary_death(0,np.zeros(3),0));self.assertIsNone(w.initial_stationary_death(1,np.zeros(3),0))
 def test_zero_hook_path_includes_activation_without_air_jump(self):
  w=object.__new__(World);w.cfg=Config();w.graph={'ground':np.array([[1.,2.,3.]])};term={'node':0,'post':np.repeat([[1.,2.,3.]],5,axis=0)};path,arrival,events=w.route_path({'edges':[]},term);self.assertEqual(arrival,30);self.assertEqual(len(path),35);self.assertTrue(np.all(path==[1,2,3]))
 def test_twenty_full_precharge_not_fabricated(self):
  self.assertEqual(schedule(20,'full-light'),[]);self.assertEqual(schedule(20,'light3'),[(20,'light'),(50,'light'),(80,'light')]);self.assertEqual(schedule(40,'full-light'),[(40,'full'),(76,'light')])
 def test_falloff_does_not_still_claim_two_shot_lethal(self):
  self.assertEqual(damage_at_distance(8),52.);self.assertLess(2*damage_at_distance(13.4),100.)
if __name__=='__main__':unittest.main()
