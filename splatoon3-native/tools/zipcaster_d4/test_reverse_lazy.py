import unittest
from tools.zipcaster_d4.reverse_v2 import Reverse
from tools.zipcaster_d4.reverse_lazy import LazyReverse


class LazyTests(unittest.TestCase):
    def test_actual_cost_order_matches_eager_without_false_terminal(self):
        src=[0,0,1,2,3];dst=[0,1,1,2,2];cost=[.05,.1,.07,.08,.09]
        optimistic=[dict(node=0,cost=.01),dict(node=1,cost=.02),dict(node=2,cost=.01)]
        actual=[dict(node=0,cost=.3),None,dict(node=2,cost=.08)]
        calls=[]
        def resolve(i):calls.append(i);return actual[i]
        lazy=LazyReverse(src,dst,cost,2,3,optimistic,resolver=resolve)
        eager=Reverse(src,dst,cost,2,3,[actual[0],actual[2]])
        for start in range(2):
            got=list(lazy.candidates(start));expected=list(eager.candidates(start))
            self.assertEqual(sorted((r['edges'],round(r['cost'],10))for r in got),sorted((r['edges'],round(r['cost'],10))for r in expected))
            self.assertEqual([r['cost']for r in got],sorted(r['cost']for r in got))
        self.assertEqual(len(calls),len(set(calls)))


if __name__=='__main__':unittest.main()
