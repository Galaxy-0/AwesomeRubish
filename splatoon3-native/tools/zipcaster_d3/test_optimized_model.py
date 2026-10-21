import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[2])]
import unittest,numpy as np
from calibrated_model import Config,duel_batch as old
from optimized_model import duel_batch as new
class OptimizedTests(unittest.TestCase):
 def test_symmetric_pair_grouping_matches_original_collision(self):
  from arena.geometry import CollisionMesh
  from batch_geometry import BatchMesh
  from paired_rays import clear_pairs
  triangles=np.array([[[0,-10,-10],[0,10,-10],[0,10,10]],[[0,-10,-10],[0,10,10],[0,-10,10]]],float);oracle=CollisionMesh(triangles);mesh=BatchMesh(triangles);rng=np.random.default_rng(423)
  starts=rng.uniform([-8,-12,-12],[8,12,12],(423,3));ends=np.repeat(rng.uniform([-8,-12,-12],[8,12,12],(9,3)),47,axis=0)
  expected=np.array([oracle.clear(a,b)for a,b in zip(starts,ends)])
  np.testing.assert_array_equal(clear_pairs(mesh,starts,ends),expected);np.testing.assert_array_equal(clear_pairs(mesh,ends,starts),expected)
 def test_sparse_ray_identity(self):
  rng=np.random.default_rng(3);path=np.c_[np.linspace(0,7,190),np.sin(np.arange(190)/30)*3,np.zeros(190)];enemy=rng.uniform([-20,0,-20],[20,9,20],(31,3));headings=rng.uniform(-3.14,3.14,31);forms=rng.random(31)>.5;clear=rng.random((190,31))>.25;cfg=Config(full_reliability=.25,light_reliability=.5,defender_pitch_sigma_degrees=2.)
  def rays(a,b):return np.sin(a[:,0]+b[:,2])>.1
  for seed in range(5):
   args=(path,80,enemy,headings,forms,clear);kw=dict(cfg=cfg,samples=8,seed=seed,ballistic_clear=rays)
   a=old(*args,**kw);b=new(*args,**kw)
   for k in a:self.assertTrue(np.array_equal(a[k],b[k]),k)
if __name__=='__main__':unittest.main()
