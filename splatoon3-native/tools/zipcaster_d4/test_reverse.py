import unittest,numpy as np
from tools.zipcaster_d4.reverse import Reverse,grade
class ReverseTests(unittest.TestCase):
 def test_losing_shortest_path_does_not_hide_successful_route(self):
  r=Reverse([0,0],[0,1],[.1,.2],1,2,[dict(node=0,cost=.1),dict(node=1,cost=.1)]);routes=list(r.candidates(0));self.assertAlmostEqual(routes[0]['cost'],.2);self.assertAlmostEqual(routes[1]['cost'],.3);winner=next(x for x in routes if x['terminal']==1);self.assertEqual(winner['edges'],(1,))
 def test_reverse_lower_bound_and_three_hook_path(self):
  r=Reverse([0,1,2],[0,1,2],[.1,.1,.1],1,3,[dict(node=2,cost=.1)]);routes=list(r.candidates(0));self.assertEqual(len(routes),1);self.assertEqual(routes[0]['edges'],(0,1,2));self.assertAlmostEqual(routes[0]['cost'],.4)
 def test_more_than_three_hooks_not_invented(self):
  r=Reverse([0,1,2,3],[0,1,2,3],[.1]*4,1,4,[dict(node=3,cost=.1)]);self.assertEqual(list(r.candidates(0)),[])
 def test_strict_zero_cutoff_and_boundary_grades(self):
  r=Reverse([0],[0],[.7],1,1,[dict(node=0,cost=.3)]);self.assertEqual(list(r.candidates(0)),[])
  self.assertEqual([grade(x)for x in [0,.0001,.0999,.1,.3,.3001]],['unreachable','extreme','extreme','normal','normal','stable'])
 def test_every_ground_node_can_be_queried(self):
  r=Reverse([0,1,2],[0,0,0],[.1,.2,.3],3,1,[dict(node=0,cost=.1)]);self.assertTrue(all(list(r.candidates(i))for i in range(3)))
 def test_no_terminal_is_proven_unreachable_in_declared_graph(self):
  r=Reverse([0],[0],[.1],1,1,[]);self.assertTrue(np.isinf(r.lower[3][0]));self.assertEqual(list(r.candidates(0)),[])
 def test_multiple_programs_and_cycles_are_cost_ordered(self):
  r=Reverse([0,1,2],[0,1,0],[.1,.1,.1],1,2,[dict(node=0,cost=.3),dict(node=1,cost=.1)]);rows=list(r.candidates(0));self.assertGreater(len(rows),2);self.assertEqual([round(x['cost'],6)for x in rows],sorted(round(x['cost'],6)for x in rows));self.assertTrue(all(len(x['edges'])<=3 for x in rows))
 def test_zero_hook_ground_terminal_competes_without_hook_charge(self):
  r=Reverse([0],[0],[.2],1,1,[dict(node=0,ground=True,cost=.15),dict(node=0,cost=.1)]);rows=list(r.candidates(0));self.assertEqual(rows[0]['edges'],());self.assertAlmostEqual(rows[0]['cost'],.15);self.assertEqual(rows[1]['edges'],(0,))
 def test_ground_terminal_cannot_be_used_at_another_source(self):
  r=Reverse([],[],[],2,0,[dict(node=0,ground=True,cost=.1)]);self.assertEqual(list(r.candidates(1)),[])
 def test_negative_cost_rejected(self):
  with self.assertRaises(ValueError):Reverse([0],[0],[-.1],1,1,[])
if __name__=='__main__':unittest.main()
