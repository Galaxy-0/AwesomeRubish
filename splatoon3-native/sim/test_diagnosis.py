"""Protocol-clock and route-counter semantics; no native execution."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

from arena.referee import PlayerTruth, RefereeSnapshot
from .diagnosis import route_summary, typed_record
from .observation_clock import RecordedClock


class DiagnosticTests(unittest.TestCase):
    def test_report_rejects_missing_conditional_grid(self):
        import tempfile
        from .diagnosis_report import groups
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'incomplete prefix-clock grid'):
                groups(directory,'prefix-clock',6)

    def fixture(self):
        players=tuple(PlayerTruth(f'player_{i}',i,8000,True,(float(i),0.,0.),0.,1.,1.,False,0,False,True,0.,0.) for i in (0,1))
        truth=RefereeSnapshot('fixture',0,players,180.)
        env=SimpleNamespace(frame=0,duration=12,players=[SimpleNamespace(velocity=np.zeros(3),special=0.) for _ in (0,1)])
        env.truth=lambda:replace(truth,frame=env.frame,players=tuple(replace(p,position=(float(env.frame),0.,0.),sample_frame=env.frame) for p in players))
        return env

    def test_clock_uses_past_sim_values_and_rejects_future_stamp(self):
        env=self.fixture();stamps=np.zeros((13,2),int);clock=RecordedClock(env,stamps)
        env.frame=4;clock.capture()
        self.assertEqual(clock.truth().players[0].position,(0.,0.,0.))
        self.assertEqual(clock.truth().frame,4)
        stamps[4]=4;self.assertEqual(clock.truth().players[0].position,(4.,0.,0.))
        stamps[1]=2
        with self.assertRaisesRegex(ValueError,'future sample'):RecordedClock(env,stamps)

    def test_missing_clock_does_not_expose_live_position(self):
        env=self.fixture();clock=RecordedClock(env,np.full((13,2),-1,int))
        self.assertIsNone(clock.truth().players[0].position)
        self.assertIsNone(clock.special(0).value)

    def test_route_dwell_does_not_fill_long_sample_gaps_or_infer_area(self):
        states=np.full((41,2,12),np.nan);actions=np.zeros((40,2,13))
        states[[0,4,40],:]=[0,0,0,0,0,0,1,1,0,4,1,0]
        actions[:4,:,7]=1
        atlas=SimpleNamespace(region=lambda name:(0.,0.,0.))
        with patch('arena.lib.atlas.MapAtlas.load',return_value=atlas):rows=route_summary(states,actions,1)
        self.assertEqual(rows[0]['high_dwell_sample_hold_frames'],4)
        self.assertEqual(rows[0]['high_ZR_sample_hold_frames'],4)
        self.assertEqual(rows[0]['release_inputs'],1)
        self.assertFalse(rows[0]['native_paint_area_or_painting_duration_measured'])

    def test_reordered_prefix_only_rebuilds_policy_allowlist(self):
        public=lambda i:dict(player_id=f'player_{i}',team=i,weapon=8000,alive=True)
        obs=dict(match_id='native',frame=12,stage_id=3,remaining_seconds=179.,
            own=dict(public=public(1),position=[1,2,3],heading=0.,hp=1.,ink=.5,sample_frame=9,private_truth='must drop'),
            enemies=[dict(public=public(0),visible=False,position=None,heading=None,sample_frame=None,last_seen_position=None,last_seen_frame=None)])
        typed=typed_record(obs,[1,0],'conditional')
        self.assertEqual(typed.own.public.player_id,'player_0')
        self.assertEqual(typed.enemies[0].public.player_id,'player_1')
        self.assertEqual(typed.own.sample_frame,9)
        self.assertFalse(hasattr(typed.own,'private_truth'))


if __name__=='__main__':unittest.main()
