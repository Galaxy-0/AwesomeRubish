import unittest,numpy as np
from model_v2 import Config,hook_path
from budget import Gauge
class PathTests(unittest.TestCase):
 def test_jump_and_landing(self):
  path,es=hook_path([0,0,0],[[0,10,20]],[[0,9.4,19.4]],ground_landings=[[0,2,19.4]])
  b=next(e['frame']for e in es if e['event']=='B跳离');a=next(e['frame']for e in es if e['event']=='开始蓄力')
  self.assertGreater(path[b+16,1],path[b,1]+2);self.assertAlmostEqual(path[a,1],2.)
  self.assertEqual(a-b,117);self.assertAlmostEqual(es[-1]['spent'],Gauge().cost(len(path)-1,hooks=1,fulls=1,lights=1))
 def test_multiple_hooks_cost_wait_and_jump(self):
  path,es=hook_path([0,0,0],[[0,10,10],[10,10,10]],[[0,9.4,9.4],[9.4,9.4,10]])
  self.assertIsNotNone(path);firstB=next(e['frame']for e in es if e['event']=='B跳离');arrival=next(e['frame']for e in es if e['event']=='到达');self.assertEqual(firstB-arrival,146)
 def test_excess_budget_rejects(self):
  path,_=hook_path([0,0,0],[[0,10,10],[10,10,10],[10,10,0]],[[0,9.4,9.4],[9.4,9.4,10],[10,9.4,.6]])
  self.assertIsNone(path)
if __name__=='__main__':unittest.main()
