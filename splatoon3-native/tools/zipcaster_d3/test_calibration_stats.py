import unittest
from calibration_stats import ranks,spearman,kendall,beta_interval,fit_reliability
class StatsTests(unittest.TestCase):
 def test_ties(self):self.assertEqual(list(ranks([4,1,1,7])),[3,1.5,1.5,4])
 def test_rank_extremes(self):
  self.assertAlmostEqual(spearman([1,2,3],[6,5,4]),-1);self.assertEqual(kendall([1,2,3],[6,5,4]),-1)
  self.assertEqual(kendall([1,1,2],[3,3,4]),1);self.assertIsNone(spearman([1,2],[0,0]));self.assertIsNone(kendall([1,2],[0,0]))
 def test_beta(self):
  lo,hi=beta_interval(0,3);self.assertAlmostEqual(lo,1-.975**.25);self.assertAlmostEqual(hi,1-.025**.25)
 def test_surrogate_fit(self):
  self.assertAlmostEqual(fit_reliability([1]*10,[1]+[0]*9),.1,places=3)
if __name__=='__main__':unittest.main()
