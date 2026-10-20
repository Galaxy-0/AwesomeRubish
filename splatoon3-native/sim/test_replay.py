"""Prove time alignment, no teacher forcing and input-gap rejection offline."""
import unittest

from .engine import Simulator, neutral
from .parameters import Parameters
from .replay import compare
from .test_core import fixture


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.params = Parameters.local()
        cls.terrain = fixture()

    def env(self):
        return Simulator(parameters=self.params, terrain=self.terrain, duration_frames=20)

    def recording(self):
        e = self.env()
        actions = {'player_0': neutral(), 'player_1': neutral()}
        actions['player_0']['sticks'][1] = 1.
        barriers = []
        for frame in range(11):
            infos = {}
            for i, p in enumerate(e.players):
                origin = 1000 + i * 5000  # independent native host origins
                infos[f'player_{i}'] = dict(frame=origin + frame,
                    position_sample_frame=origin + frame, position=p.position.tolist(),
                    position_valid=1, heading=p.heading, own_view=dict(yaw=p.yaw, pitch=p.pitch),
                    hp=p.hp, hp_valid=1, ink=p.ink, ink_valid=1, alive=int(p.alive), alive_valid=1,
                    special=p.special, special_valid=1,
                    referee_motion=dict(form_squid=0, ground_contact=0))
            barriers.append(dict(frame=frame, infos=infos))
            if frame < 10:
                e.step(actions, observe=False)
        intervals = [dict(frame_interval=[0, 10], actions=actions)]
        return intervals, barriers

    def test_independent_native_frame_origins_and_duplicates(self):
        inputs, barriers = self.recording()
        # Repeated packet at the same sample timestamp must not count twice.
        barriers.insert(4, barriers[3])
        result = compare(self.env(), inputs, barriers, 0, 10)
        self.assertEqual(result['players']['player_0']['position_world_units']['samples'], 10)
        self.assertLess(result['players']['player_0']['position_world_units']['maximum'], 1e-8)

    def test_native_observations_do_not_correct_simulated_positions(self):
        inputs, barriers = self.recording()
        for row in barriers[5:]:
            row['infos']['player_0']['position'][0] += 5
        result = compare(self.env(), inputs, barriers, 0, 10)
        self.assertGreater(result['players']['player_0']['position_world_units']['mean'], 2.9)
        curve = result['sampled_curves']['players']['player_0']
        self.assertEqual(curve[-1][4], 1.)  # sim_x stayed at initialization

    def test_missing_input_and_empty_windows_fail(self):
        inputs, barriers = self.recording()
        inputs[0]['frame_interval'] = [2, 10]
        with self.assertRaisesRegex(ValueError, 'gap'):
            compare(self.env(), inputs, barriers, 0, 10)
        with self.assertRaisesRegex(ValueError, 'empty'):
            compare(self.env(), inputs, barriers, 0, 0)


if __name__ == '__main__':
    unittest.main()
