import unittest,numpy as np
from model_v2 import duel_batch as prior,Config as PriorConfig
from calibrated_model import duel_batch,Config,hook_path
class CalibratedTests(unittest.TestCase):
 def test_identity_when_parameters_default_and_rays_clear(self):
  path=np.zeros((120,3));positions=np.array([[0.,0.,10.],[5.,0.,4.]]);heading=np.array([3.14,0.]);forms=np.array([False,False]);clear=np.ones((120,2),bool);args=(path,0,positions,heading,forms,clear);kw=dict(samples=64,seed=19,ballistic_clear=lambda a,b:np.ones(len(a),bool))
  a=prior(*args,cfg=PriorConfig(),**kw);b=duel_batch(*args,cfg=Config(),**kw)
  for k in a:self.assertTrue(np.array_equal(a[k],b[k]),k)
 def test_zero_controller_reliability(self):
  path=np.zeros((120,3));p=np.array([[0.,0.,10.]]);r=duel_batch(path,0,p,np.array([0.]),np.array([False]),np.ones((120,1),bool),cfg=Config(full_reliability=0,light_reliability=0),samples=64)
  self.assertFalse(r['kills'].any())
 def test_post_emission_return_does_not_erase_tactic(self):
  p,e=hook_path([0,0,0],[[0,2,10]],[[0,2,9]],Config(arrival_setup=360),ground_landings=[[0,0,9]])
  self.assertIsNotNone(p);self.assertLess(e[-1]['required_until_last_emission'],.96)
  self.assertTrue(any(v['event']=='预算归零开始回程'for v in e))
  self.assertLessEqual(e[-1]['spent'],.96)
 def test_emission_outside_resource_budget_is_rejected(self):
  p,e=hook_path([0,0,0],[[0,2,10]],[[0,2,9]],Config(arrival_setup=510))
  self.assertIsNone(p)
if __name__=='__main__':unittest.main()
