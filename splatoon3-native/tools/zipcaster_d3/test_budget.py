import unittest
from budget import Gauge,Action,optimize
class BudgetTests(unittest.TestCase):
    def test_natural_zero(self):
        r=Gauge().exhaust([]);self.assertEqual(r['zero_frame'],599);self.assertEqual(r['return_end_frame'],695)
    def test_action_costs(self):
        g=Gauge();self.assertAlmostEqual(g.cost(60,hooks=1,lights=1,fulls=1),.1+(.04+.052+.117)/1.5)
        self.assertLess(g.exhaust([(30,g.full_ink/g.capacity)])['zero_frame'],599)
    def test_count_distinct_targets(self):
        actions=[Action('a',0,0,60,full=1,target=0,kill=(1.,)),Action('b',0,0,60,full=1,target=1,kill=(1.,))]
        self.assertAlmostEqual(optimize(actions,0,2)['expected_kills'],2.)
    def test_budget_rejects_two(self):
        actions=[Action('a',0,0,180,full=1,target=0,kill=(1.,)),Action('b',0,0,180,full=1,target=1,kill=(1.,))]
        self.assertEqual(optimize(actions,0,2,budget=.7)['expected_kills'],1.)
    def test_worst_behavior_and_death(self):
        a=Action('a',0,1,30,target=0,kill=(.9,.1),survival=(0.,0.))
        b=Action('b',1,1,30,target=1,kill=(1.,1.),survival=(1.,1.))
        self.assertAlmostEqual(optimize([a,b],0,2)['expected_kills'],.5)
        self.assertAlmostEqual(optimize([a,b],0,2,mode='worst')['expected_kills'],.1)
    def test_repeated_uncertain_attempt_is_one_kill(self):
        a=Action('a',0,0,200,target=0,kill=(.5,))
        self.assertAlmostEqual(optimize([a],0,1)['expected_kills'],.75)
if __name__=='__main__':unittest.main()
