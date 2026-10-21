"""Model invariants, not claims of native calibration."""
import unittest,sys,math
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from model import Config,hook_path,duel_batch,wilson
class ModelTests(unittest.TestCase):
 def case(self,heading=0,clear=True,distance=10,samples=256):
  path=np.zeros((110,3));enemy=np.array([[0,0,distance]])
  return duel_batch(path,0,enemy,np.array([heading]),np.array([False]),np.full((len(path),1),clear),samples=samples)
 def test_unseen_behind_two_hits_kill(self):
  r=self.case();self.assertTrue(r['kills'].all());self.assertTrue((r['first_seen']==-1).all());self.assertTrue((r['def_ko']==74).all())
 def test_reacting_front_reduces_kills(self):
  r=self.case(math.pi);self.assertLess(r['kills'].mean(),.2);self.assertTrue((r['first_seen']==0).all())
 def test_cover_blocks_both_weapons(self):
  r=self.case(math.pi,False);self.assertFalse(r['kills'].any());self.assertTrue((r['atk_ko']==-1).all())
 def test_outside_sword_range(self):self.assertFalse(self.case(distance=25)['kills'].any())
 def test_seed_reproducible(self):
  a=self.case(math.pi);b=self.case(math.pi)
  for k in a:np.testing.assert_array_equal(a[k],b[k])
 def test_hook_range_budget(self):
  self.assertIsNone(hook_path([0,0,0],[[36,1.1,0]],[[35,0,0]])[0])
  p,e=hook_path([0,0,0],[[20,5,0]],[[19,3,0]])
  self.assertIsNotNone(p);self.assertLessEqual(np.linalg.norm(np.diff(p,axis=0),axis=1).max(),65/60+1e-9)
  self.assertEqual([v['event']for v in e],['出钩','挂住','到达','开始蓄力'])
 def test_probability_bounds(self):
  self.assertEqual(wilson(0,0),[None,None]);self.assertLess(wilson(0,100)[1],.04);self.assertGreater(wilson(100,100)[0],.96)
if __name__=='__main__':unittest.main()
