#!/usr/bin/env python3
"""Temporal and information-boundary checks; no native claims from fixtures."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'arena/lib_a6'), str(ROOT/'arena/lib')]
from stamper import (FULL_CHARGE_FRAMES, charge_slash, emerge_charge,
                     light_combo, burst_bomb, zipcaster, squid_roll,
                     PredictiveAim,FastTurn)


def observation(frame=100):
    return dict(match_id='fixture', frame=frame,
                own=dict(public=dict(alive=True, weapon=8000), position=[0., 0., 0.],
                         sample_frame=frame, view_yaw=0., view_pitch=0., ink=1.,
                         submerged=True, special=1.),
                enemies=[dict(public=dict(player_id='target'), visible=True,
                              position=[0., 0., 8.], sample_frame=frame)])


class Tests(unittest.TestCase):
    def execute(self, factory):
        obs = observation()
        plan = factory(obs)
        frames = []
        for _ in range(300):
            result = plan.tick(obs)
            if result.done:
                self.assertEqual(result.status, 'complete')
                return frames
            self.assertTrue(1 <= result.frames <= 6)
            for _ in range(result.frames):
                frames.append((obs['frame'], deepcopy(result.action), result.phase))
                obs['frame'] += 1
                obs['own']['sample_frame'] = obs['frame']
        self.fail('macro did not terminate')

    def test_release_edges_and_dash(self):
        frames = self.execute(lambda o: charge_slash(o, dash=True))
        self.assertEqual(sum(a['buttons'][0] for _, a, _ in frames), FULL_CHARGE_FRAMES)
        self.assertEqual(frames[FULL_CHARGE_FRAMES][2], 'release')
        self.assertEqual(frames[FULL_CHARGE_FRAMES][1]['sticks'][1], 1.)
        self.assertTrue(all(a['buttons'][1] == 0 for _, a, _ in frames))

    def test_combo_does_not_turn_into_charge(self):
        frames = self.execute(lambda o: light_combo(o, 3, after=(1., 0.)))
        presses = [f for f, a, _ in frames if a['buttons'][0]]
        self.assertEqual(presses, [100, 130, 160])
        self.assertEqual(frames[-1][1]['sticks'], [0., 0., 0., 0.])

    def test_late_caller_cancels_instead_of_faking_release(self):
        obs = observation()
        plan = charge_slash(obs)
        result = plan.tick(obs)
        obs['frame'] += result.frames + 1
        obs['own']['sample_frame'] = obs['frame']
        self.assertEqual(plan.tick(obs).status, 'missed_boundary')

    def test_dead_stale_new_match_stop(self):
        for kind in ('dead', 'stale', 'match'):
            obs = observation()
            plan = charge_slash(obs)
            if kind == 'dead': obs['own']['public']['alive'] = False
            if kind == 'stale': obs['own']['sample_frame'] -= 9
            if kind == 'match': obs['match_id'] = 'next'
            result = plan.tick(obs)
            self.assertTrue(result.done)
            self.assertFalse(any(result.action['buttons']))

    def test_resource_gates_and_swim_emerge(self):
        obs = observation()
        obs['own']['special'] = None
        self.assertEqual(zipcaster(obs).tick(obs).status, 'requires_full_special')
        obs['own']['special'] = .999
        self.assertEqual(zipcaster(obs).tick(obs).status, 'requires_full_special')
        obs['own']['ink'] = .449
        self.assertEqual(burst_bomb(obs).tick(obs).status, 'insufficient_ink')
        obs['own']['ink'] = 1.
        result = emerge_charge(obs).tick(obs)
        self.assertEqual(result.action['buttons'][:2], [1, 0])
        obs['own']['submerged'] = False
        self.assertEqual(squid_roll(obs).tick(obs).status, 'requires_own_ink')

    def test_hidden_and_last_seen_are_never_current_velocity(self):
        aim = PredictiveAim()
        obs = observation()
        aim.aim(obs, 'target')
        obs = observation(106)
        obs['enemies'][0]['position'][0] = .6
        aim.aim(obs, 'target')
        self.assertGreater(aim.target[0], .6)
        self.assertAlmostEqual(aim.velocity[0], .1)
        obs['enemies'][0].update(visible=False, position=None, sample_frame=None,
                                 last_seen_position=[999., 0., 0.], last_seen_frame=106)
        self.assertEqual(aim.aim(obs, 'target').status, 'target_unavailable')
        self.assertIsNone(aim.target)
        obs = observation(112)
        obs['enemies'][0]['position'][0] = 9.
        aim.aim(obs, 'target')
        self.assertEqual(aim.velocity, (0., 0., 0.))

    def test_teleport_reset_and_stale_enemy(self):
        aim = PredictiveAim()
        aim.aim(observation(), 'target')
        obs = observation(101)
        obs['enemies'][0]['position'][0] = 100.
        aim.aim(obs, 'target')
        self.assertEqual(aim.velocity, (0., 0., 0.))
        obs['enemies'][0]['sample_frame'] -= 9
        self.assertEqual(aim.aim(obs, 'target').status, 'target_unavailable')

    def test_lead_includes_age_of_current_visible_sample(self):
        aim=PredictiveAim();aim.aim(observation(),'target')
        obs=observation(106);obs['enemies'][0]['position'][0]=.6
        aim.aim(obs,'target');first=aim.target[0]
        obs['frame']=110;obs['own']['sample_frame']=110
        aim.aim(obs,'target')
        self.assertAlmostEqual(aim.target[0]-first,.4)

    def test_flick_learns_own_gyro_sign_and_resets(self):
        for sign in (-1,1):
            turn=FastTurn()
            for frame in range(15):
                obs=observation(100+frame)
                obs['own']['view_yaw']=sign*.12 if frame==14 else 0.
                result=turn.aim(obs,(5.,1.1,5.))
            self.assertEqual(turn.sign,sign)
            self.assertEqual(result.phase,'calibrated_gyro_turn')
            self.assertGreater(sign*result.action['gyro'][2],0.)
            obs=observation(116);obs['match_id']='next'
            self.assertEqual(turn.aim(obs,(5.,1.1,5.)).phase,'gyro_calibration')
            obs['own']['public']['alive']=False
            self.assertEqual(turn.aim(obs,(5.,1.1,5.)).action['gyro'],[0.,0.,0.])


if __name__ == '__main__':
    unittest.main()
