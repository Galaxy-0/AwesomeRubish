import math,unittest
import numpy as np
from tools.zipcaster_d3r.ray_model import direction,inverse_pitch,predict
class RayTests(unittest.TestCase):
 def setUp(self):self.p=dict(tangent_scale=1.108,tangent_bias=-.00035,yaw_bias=0.,origin_coefficients=[1.1,0,0,0,0],effective_range=35.)
 def test_inverse_and_unit(self):
  for p in np.linspace(-.85,.85,31):
   v=direction(.7,p,self.p);self.assertAlmostEqual(np.linalg.norm(v),1);self.assertAlmostEqual(inverse_pitch(math.asin(v[1]),self.p),p)
 def test_first_cantbind_still_occludes(self):
  # Front material rejects binding; farther valid wall cannot be substituted.
  tri=np.array([[[-5,-5,5],[5,-5,5],[0,5,5]],[[-5,-5,10],[5,-5,10],[0,5,10]]]);normal=np.array([[0,0,-1]]*2)
  r=dict(map='test',source=[0,0,0],body_heading=0,command=dict(yaw=0,native_pitch=inverse_pitch(0,self.p)),anchor=None,tip_direction=None)
  geo={'test':(tri,normal,[dict(mat_flags=['SuperHookCantBind']),dict(mat_flags=[])])};x=predict(r,self.p,geo);self.assertFalse(x['eligible']);self.assertAlmostEqual(x['distance'],5)
 def test_native_outcome_not_prediction_input(self):
  tri=np.array([[[-5,-5,10],[5,-5,10],[0,5,10]]]);geo={'test':(tri,np.array([[0,0,-1]]),[dict(mat_flags=[])])}
  r=dict(map='test',source=[0,0,0],body_heading=0,command=dict(yaw=0,native_pitch=inverse_pitch(0,self.p)),anchor=None,tip_direction=None,native_bind=False)
  a=predict(r,self.p,geo);r['native_bind']=True;b=predict(r,self.p,geo);self.assertEqual(a,b)
if __name__=='__main__':unittest.main()
