import unittest
import numpy as np
from tools.zipcaster_d4.geometry import Mesh
from tools.zipcaster_d4.model_v3 import World,Config,schedule
from tools.zipcaster_d4 import test_attack_sequence_v2 as fixture


class ModelTests(unittest.TestCase):
    def world(self):
        w=object.__new__(World);w.cfg=Config();w.shots=fixture.FixtureShots();w.recoil=fixture.SequenceTests().profiles()
        w.graph={'ground':np.array([[0.,0.,-2.5],[0.,0.,2.5]]),'edge_source':np.array([],int)}
        w.field=w.vision=Mesh(np.empty((0,3,3)))
        return w
    def test_contact_includes_activation_and_strict_first_death(self):
        w=self.world();enemy=np.zeros(3)
        term=w.terminal(0,enemy,40,'full1',True)
        path,arrival,_=w.route_path(dict(edges=[]),term)
        r=w.simulate(path,arrival,term,enemy,0.)
        self.assertTrue(r['kill']);self.assertTrue(r['stealth'])
        self.assertEqual(r['enemy_down'],79)
        self.assertAlmostEqual(term['cost'],.19133333333333333)
        term=w.terminal(1,enemy,40,'full1',True)
        path,arrival,_=w.route_path(dict(edges=[]),term)
        r=w.simulate(path,arrival,term,enemy,0.)
        self.assertFalse(r['kill']);self.assertLess(r['attacker_down'],31)
    def test_moving_enemy_keeps_heading_but_moves_cone_origin(self):
        w=self.world()
        visible,_=w.visibility(np.array([[0,0,2],[0,0,2]]),np.array([[0,0,0],[0,0,4]]),0.)
        self.assertEqual(visible.tolist(),[True,False])
    def test_single_full_requires_actual_charge_budget(self):
        self.assertEqual(schedule(20,'full1'),[])
        self.assertEqual(schedule(40,'full1'),[(40,'full')])
        self.assertEqual(schedule(20,'light2'),[(20,'light'),(50,'light')])


if __name__=='__main__':unittest.main()
