import json,unittest
from pathlib import Path
import numpy as np
from tools.zipcaster_d4.blade_only import contact_exclusion
from tools.zipcaster_d4.attack_geometry import basis,contact_overlap
from tools.zipcaster_d4.contact_shape import native_shape

class ExclusionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.params=json.loads(Path('work/a6/parameters.json').read_text())
 def test_near_route_is_unknown_not_safe_zero(self):
  r=contact_exclusion(self.params,np.zeros((4,3)),np.tile([0,0,2.6],(4,1)),'full')
  self.assertFalse(r['certified_disjoint']);self.assertEqual(r['contact_damage_interval'],[0,140])
 def test_remote_route_separates_all_orientations(self):
  rng=np.random.default_rng(52240)
  for style,key in [('full','vertical'),('light','horizontal')]:
   source=np.zeros((4,3));target=np.tile([0,0,6.],(4,1));r=contact_exclusion(self.params,source,target,style)
   self.assertTrue(r['certified_disjoint'])
   shape=native_shape(self.params[key+'_contact']['ShapeParam']);off=self.params['swing']['ShotSlashOffset_Vertical'if style=='full'else'ShotSlashOffset_L'];off=np.array([off[k]for k in 'XYZ'])
   for _ in range(40):
    yaw,el=rng.uniform(-np.pi,np.pi),rng.uniform(-np.pi/2,np.pi/2)
    origin=basis(yaw,0)@off
    self.assertFalse(contact_overlap(origin,basis(yaw,el),shape,target[0],.6,.6,1.3)['hit'])
 def test_one_late_frame_contact_possibility_rejects_route(self):
  target=np.tile([0.,0.,6.],(4,1));target[3,2]=3
  self.assertFalse(contact_exclusion(self.params,np.zeros((4,3)),target,'light')['certified_disjoint'])
 def test_height_does_not_make_a_near_route_safe(self):
  self.assertFalse(contact_exclusion(self.params,np.zeros((4,3)),np.tile([0,20,2],(4,1)),'full')['certified_disjoint'])

if __name__=='__main__':unittest.main()
