"""Reserve/refund, cancellation and delayed delivery, independent of fit data."""
import unittest

from .engine import Simulator, neutral
from .parameters import Parameters
from .test_core import fixture
from .weapon import WeaponModel


class WeaponTests(unittest.TestCase):
    def test_reserve_release_refund_and_cancel(self):
        p = Parameters.local()
        model = WeaponModel()
        for count, expected in ((1, 0.), (6, .035), (21, .117), (60, .117)):
            self.assertAlmostEqual(model.reserve(p, count), expected, places=6)
        e = Simulator(parameters=p, terrain=fixture(), weapon_model=model)
        a, n = neutral(), neutral(); a['buttons'][0] = 1
        e.step({'player_0':a,'player_1':n}, 20, observe=False)
        self.assertLess(e.players[0].ink, .9)
        e.step({'player_0':n,'player_1':n}, observe=False)
        self.assertAlmostEqual(e.players[0].ink, .948, places=6)
        self.assertEqual(e.players[0].reserved, 0.)
        e.reset(); e.step({'player_0':a,'player_1':n}, 15, observe=False)
        a['buttons'][1] = 1
        e.step({'player_0':a,'player_1':n}, observe=False)
        self.assertAlmostEqual(e.players[0].ink, 1.)
        self.assertEqual(e.players[0].charge, 0)

    def test_hp_delivery_delay_does_not_move_reference_frames(self):
        e = Simulator(parameters=Parameters.local(), terrain=fixture(), weapon_model=WeaponModel(
            dict(schema='sim.weapon.v2',damage_delay=4,contact_muzzle_anchor=True)))
        e._damage(1,.35,0,'ink_blade')
        self.assertEqual(e.players[1].hp,1.)
        n={'player_0':neutral(),'player_1':neutral()}
        e.step(n,3,observe=False); self.assertEqual(e.players[1].hp,1.)
        e.step(n,observe=False); self.assertAlmostEqual(e.players[1].hp,.65)
        self.assertEqual(e.events[-1]['frame'],4)


if __name__ == '__main__':
    unittest.main()
