import unittest
from tools.zipcaster_d4.reverse_v2 import Reverse
class PrefixTests(unittest.TestCase):
 def test_dead_prefix_drops_all_suffixes_not_more_expensive_alternative(self):
  checked=[]
  def alive(path):checked.append(path);return path[0]!=0
  r=Reverse([0,0,1,1,2],[0,1,0,1,0],[.1,.2,.1,.1,.1],1,2,[dict(node=0,cost=.1),dict(node=1,cost=.1)],prefix_check=alive);rows=list(r.candidates(0));self.assertTrue(rows);self.assertTrue(all(x['edges'][0]==1 for x in rows));self.assertNotIn((0,2),checked)
 def test_ground_zero_hook_does_not_depend_on_hook_prefix(self):
  r=Reverse([0],[0],[.1],1,1,[dict(node=0,ground=True,cost=.1),dict(node=0,cost=.1)],prefix_check=lambda path:False);rows=list(r.candidates(0));self.assertEqual(len(rows),1);self.assertEqual(rows[0]['edges'],())
if __name__=='__main__':unittest.main()
