"""Causality, contact semantics and metric angle regression checks."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from .corpus import Trace
from .corpus import WORK
from .engine import Simulator
from .horizon import angle_error, reset_native
from .horizon import evaluate
from .horizon import measure
from .horizon_batch import evaluate_vector
from .parameters import Parameters
from .test_core import fixture
from .test_motion import model_fixture


class HorizonTests(unittest.TestCase):
    def trace(self):
        trace = object.__new__(Trace)
        trace.states = np.full((21, 2, 12), np.nan)
        trace.available = np.full((21, 2), 99)
        for t in (0, 4, 8, 12, 16, 20):
            for role in range(2):
                trace.states[t, role] = [role+1., 0., t*.1, 0., 0., 0., 1., 1., 1., 0., 1., 0.]
                trace.available[t, role] = t+1
        trace.actions = np.zeros((20, 2, 13))
        trace.actions[:, :, 8] = 1
        trace.samples = [np.arange(0, 21, 4)]*2
        return trace

    def test_future_sample_not_used_for_velocity_or_position(self):
        trace = self.trace()
        # Sample at t=8 is not available to the reset until ACK=9.
        self.assertEqual(trace.past(8, 0).tolist(), [0, 4])
        env = Simulator(parameters=Parameters.local(), terrain=fixture())
        reset_native(env, trace, 8)
        expected = env.players[0].position.copy()
        trace.states[8:, :, :3] += 1000
        reset_native(env, trace, 8)
        np.testing.assert_array_equal(env.players[0].position, expected)
        self.assertAlmostEqual(expected[2], .8)

    def test_contact_zero_submerged_four_not_submerged(self):
        trace = self.trace()
        env = Simulator(parameters=Parameters.local(), terrain=fixture())
        reset_native(env, trace, 8)
        self.assertTrue(env.players[0].submerged)
        trace.states[4, 0, 9] = 4
        reset_native(env, trace, 8)
        self.assertFalse(env.players[0].submerged)

    def test_landing_interval_velocity_cannot_extrapolate_grounded_packet_under_floor(self):
        trace=self.trace()
        trace.states[0,:,1]=.4
        trace.states[4,:,1]=0.
        trace.states[4,:,9]=4
        env=Simulator(parameters=Parameters.local(),terrain=fixture())
        reset_native(env,trace,8)
        self.assertAlmostEqual(env.players[0].position[1],0.)
        self.assertEqual(env.players[0].velocity[1],0.)
        self.assertTrue(env.players[0].grounded)

    def test_air_packet_extrapolation_lands_on_intervening_support(self):
        trace=self.trace()
        trace.states[0,:,1]=.6
        trace.states[4,:,1]=.2
        trace.states[4,:,9]=5
        env=Simulator(parameters=Parameters.local(),terrain=fixture())
        reset_native(env,trace,8)
        self.assertAlmostEqual(env.players[0].position[1],0.)
        self.assertTrue(env.players[0].grounded)

    def test_angular_difference_wraps_at_pi(self):
        self.assertAlmostEqual(angle_error(np.pi-.01, -np.pi+.01), .02)

    def test_scalar_vector_metrics_and_json_serialization(self):
        trace = self.trace()
        WORK.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=WORK, prefix='unit-horizon-') as directory:
            directory = Path(directory)
            cache = directory/'trace.npz'
            np.savez(cache, states=trace.states, actions=trace.actions, available=trace.available)
            from .parameters import ROOT
            entry = dict(stage=1, cache=str(cache.relative_to(ROOT)), path='synthetic fixture', loadouts=None)
            with patch('sim.horizon.Terrain.load', return_value=fixture()), patch('sim.horizon_batch.Terrain.load', return_value=fixture()):
                scalar = evaluate([entry], (4,), model=model_fixture(), out=directory/'scalar.json')
                vector = evaluate_vector([entry], (4,), model=model_fixture(), weapon_model=None,
                                         batch_size=2, out=directory/'vector.json')
            a, b = scalar['results'][0], vector['results'][0]
            self.assertEqual(a['counts'], b['counts'])
            for metric in a['all_samples']:
                for statistic in ('mean', 'rmse', 'p95', 'maximum'):
                    self.assertAlmostEqual(a['all_samples'][metric][statistic], b['all_samples'][metric][statistic], places=10)
            self.assertIs(type(json.loads((directory/'scalar.json').read_text())['results'][0]['windows'][0]['moving']), bool)

    def test_unknown_contact_does_not_enter_identification(self):
        from .identify import collect
        trace = self.trace()
        trace.frames = len(trace.actions)
        corpus = dict(games=[dict(split='train')])
        with patch('sim.identify.Trace', return_value=trace):
            valid_count = len(collect(corpus)['train'])
            trace.states[8, :, 9] = -1
            filtered_count = len(collect(corpus)['train'])
        self.assertEqual(valid_count, 8)
        self.assertEqual(filtered_count, 2)

    def test_unknown_form_is_not_a_boolean_error_sample(self):
        env = Simulator(parameters=Parameters.local(), terrain=fixture())
        row = np.array([1.,0.,0.,0.,0.,0.,1.,1.,-1.,-1.,np.nan,0.])
        values = measure(env.players[0], row)
        self.assertNotIn('squid', values)
        self.assertNotIn('submerged', values)
        self.assertNotIn('alive', values)
        row[8] = 0
        self.assertIn('submerged', measure(env.players[0], row))


if __name__ == '__main__':
    unittest.main()
