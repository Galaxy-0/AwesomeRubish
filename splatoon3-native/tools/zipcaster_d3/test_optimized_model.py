import unittest,numpy as np
from calibrated_model import Config,duel_batch as old
from optimized_model import duel_batch as new
class OptimizedTests(unittest.TestCase):
 def test_per_node_behavior_worst_is_not_whole_map_reduction(self):
  from search_calibrated import enemy_results
  pp=np.repeat([[.7,.1],[.8,.4],[.2,.5]],16,axis=1)
  rows=enemy_results(pp,np.ones(32),[0,1],np.zeros((2,3)))
  self.assertAlmostEqual(rows[0]['expected'],1.7/3);self.assertAlmostEqual(rows[0]['worst'],.2)
  self.assertAlmostEqual(rows[1]['expected'],1/3);self.assertAlmostEqual(rows[1]['worst'],.1)
 def test_sparse_ray_identity(self):
  rng=np.random.default_rng(3);path=np.c_[np.linspace(0,7,190),np.sin(np.arange(190)/30)*3,np.zeros(190)];enemy=rng.uniform([-20,0,-20],[20,9,20],(31,3));headings=rng.uniform(-3.14,3.14,31);forms=rng.random(31)>.5;clear=rng.random((190,31))>.25;cfg=Config(full_reliability=.25,light_reliability=.5,defender_pitch_sigma_degrees=2.)
  def rays(a,b):return np.sin(a[:,0]+b[:,2])>.1
  for seed in range(5):
   args=(path,80,enemy,headings,forms,clear);kw=dict(cfg=cfg,samples=8,seed=seed,ballistic_clear=rays)
   a=old(*args,**kw);b=new(*args,**kw)
   for k in a:self.assertTrue(np.array_equal(a[k],b[k]),k)
if __name__=='__main__':unittest.main()
