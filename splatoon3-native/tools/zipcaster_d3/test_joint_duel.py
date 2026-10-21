import unittest,numpy as np
from joint_duel import simulate
class JointTests(unittest.TestCase):
 def case(self,front=False,style='full-light'):
  n=16;h=330;path=np.zeros((h,3));enemy=np.zeros((h,n,2,3));enemy[:,:,:,2]=8;heading=np.full((n,2),np.pi if front else 0.);clear=np.ones((h,n,2),bool)
  return simulate(path,[dict(frame=0,event='开始蓄力')],enemy,heading,np.zeros((n,2),bool),clear,clear,lambda a,b:np.ones(len(a),bool),seed=1,style=style)
 def test_distinct_kills_and_budget(self):
  r=self.case();self.assertTrue((r['kills']==2).all());self.assertTrue((r['spent']>=0).all());self.assertTrue((r['spent']<=1).all())
 def test_crossfire_has_shared_hp(self):
  r=self.case(front=True);self.assertLess(r['kills'].mean(),self.case()['kills'].mean());self.assertFalse(r['attacker_alive'].any())
 def test_three_lights(self):self.assertTrue((self.case(style='triple-light')['kills']==2).all())
if __name__=='__main__':unittest.main()
