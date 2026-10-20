"""Offline advanced state transitions and scalar/vector differential checks."""
import unittest

import numpy as np

from .advanced import AdvancedModel, build
from .batch import VectorBatchSimulator
from .engine import Simulator, BatchSimulator, neutral
from .parameters import Parameters, ROOT
from .test_core import fixture
from .test_motion import model_fixture
from .weapon import WeaponModel


def pair(a=None, b=None):
    return {'player_0': a or neutral(), 'player_1': b or neutral()}


class AdvancedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.params = Parameters.local()
        cls.model = AdvancedModel(build(ROOT/'work/sim/tests/advanced.json'))

    def env(self, **kwargs):
        return Simulator(parameters=self.params, terrain=kwargs.pop('terrain',fixture()),
                         motion_model=model_fixture(), weapon_model=WeaponModel(),
                         advanced_model=self.model, **kwargs)

    def test_roll_needs_own_ink_speed_reversal_and_b_edge(self):
        for own, reverse, speed, expected in [(True,True,.19,True),(False,True,.19,False),
                                             (True,False,.19,False),(True,True,.03,False)]:
            e=self.env();p=e.players[0];p.yaw=0.;p.velocity[2]=speed
            if own:e.paint.disk(p.position,5,0)
            a=neutral();a['buttons'][1]=a['buttons'][4]=1;a['sticks'][1]=-1. if reverse else 1.
            e.step(pair(a),observe=False)
            self.assertEqual(any(v['kind']=='squid_roll' for v in e.events),expected)
            if expected:
                e.step(pair(a),12,observe=False)
                self.assertLess(p.position[2],-1.)
                self.assertGreater(p.position[1],1.)
                self.assertEqual(sum(v['kind']=='squid_roll' for v in e.events),1)

    def test_surge_requires_inked_real_wall_and_charge_release(self):
        for painted,frames,expected in [(False,60,None),(True,1,'wall_jump'),(True,60,'squid_surge')]:
            e=self.env(terrain=fixture(wall=True));p=e.players[0];p.position[:]=[1,1,2.5];p.yaw=0.;p.grounded=False
            if painted:self.model.paint_wall(e,[1,1.7,3],0,3.)
            a=neutral();a['buttons'][1]=a['buttons'][4]=1
            e.step(pair(a),frames,observe=False)
            a['buttons'][4]=0;a['sticks'][1]=1.
            e.step(pair(a),24,observe=False)
            events=[v['kind'] for v in e.events if v['kind'] in ('squid_surge','wall_jump')]
            self.assertEqual(events,[] if expected is None else [expected])
            if expected=='squid_surge':self.assertGreater(p.position[1],6.)

    def test_dash_has_displacement_and_own_release_timing(self):
        e=self.env();p=e.players[0];p.yaw=0.
        a=neutral();a['buttons'][0]=1;a['sticks'][1]=1.
        e.step(pair(a),21,observe=False);start=p.position.copy()
        a['buttons'][0]=0
        e.step(pair(a),12,observe=False)
        self.assertGreater(p.position[2]-start[2],2.9)
        after=p.position.copy()
        e.step(pair(),20,observe=False)
        self.assertLess(np.linalg.norm((p.position-after)[[0,2]]),.3)
        self.assertTrue(any(v['kind']=='dash' for v in e.events))
        self.assertFalse(e.unsupported.get('dash_as_ordinary_charge'))

    def test_bomb_release_cost_insufficient_ink_wall_and_los(self):
        for wall in (False,True):
            e=self.env(terrain=fixture(wall=wall));p=e.players[0];p.yaw=0.;e.players[1].position[:]=[1,0,6.]
            a=neutral();a['buttons'][2]=1
            e.step(pair(a),3,observe=False);self.assertEqual(len(e.bombs),0);self.assertEqual(p.ink,1.)
            e.step(pair(),40,observe=False)
            self.assertAlmostEqual(p.ink,.55,places=6)
            damages=[v for v in e.events if v['kind']=='damage' and 'burst_bomb' in v['cause']]
            if wall:self.assertFalse(damages)
            else:self.assertTrue(damages)
        e=self.env();e.players[0].ink=.1
        e.step(pair(a),observe=False);e.step(pair(),observe=False)
        self.assertTrue(any(v['kind']=='dry_bomb' for v in e.events));self.assertFalse(e.bombs)

    def test_zip_gate_drain_hook_unknown_and_death_cleanup(self):
        e=self.env();p=e.players[0]
        a=neutral();a['buttons'][3]=1
        e.step(pair(a),observe=False);self.assertFalse(p.special_active)
        e.step(pair(),observe=False);p.special=1.
        e.step(pair(a),observe=False);self.assertTrue(p.special_active)
        a['buttons'][3]=0;a['buttons'][2]=1
        e.step(pair(a),90,observe=False)
        self.assertAlmostEqual(p.special,.86,delta=.01)
        self.assertTrue(e.unsupported['zipcaster_hook_displacement'])
        e._kill(0,1,'test');self.assertFalse(p.special_active);self.assertEqual(p.roll_left,0)

    def test_advanced_batch_matches_scalar_including_last_override_frame(self):
        args=dict(parameters=self.params,terrain=fixture(),motion_model=model_fixture(),
                  weapon_model=WeaponModel(),advanced_model=self.model,duration_frames=150)
        scalar=BatchSimulator(2,**args);batch=VectorBatchSimulator(2,**args)
        for env in [*scalar.envs,*batch.envs]:
            env.players[0].yaw=0.;env.paint.disk(env.players[0].position,5.,0)
            env.players[0].velocity[2]=.19
        for frame in range(120):
            a=neutral()
            a['buttons'][1]=int(frame<30);a['buttons'][4]=int(frame==0)
            a['sticks'][1]=-1. if frame<30 else (1. if 35<=frame<69 else 0.)
            a['buttons'][0]=int(35<=frame<56);a['buttons'][2]=int(frame==90)
            actions=[pair(a) for _ in range(2)]
            for env,action in zip(scalar.envs,actions):env.step(action,observe=False)
            batch.step(actions,observe=False)
            for s,b in zip(scalar.envs,batch.envs):
                self.assertEqual(s.events,b.events)
                for p,q in zip(s.players,b.players):
                    np.testing.assert_allclose(p.position,q.position,atol=1e-9)
                    np.testing.assert_allclose(p.velocity,q.velocity,atol=1e-9)
                    self.assertAlmostEqual(p.hp,q.hp);self.assertAlmostEqual(p.ink,q.ink)


if __name__=='__main__':unittest.main()
