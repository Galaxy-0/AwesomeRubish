#!/usr/bin/env python3
"""Regression: policy cadence 1 must not leave both peers at Judging."""
from pathlib import Path
import sys
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.runner import settlement_steps


class JudgingEnv:
    def __init__(self,stride=1,winners_after=360):
        self.frame_skip=stride;self.timed_out=False;self.elapsed=0
        self.winners_after=winners_after;self.steps=[]
        self.process_infos={'player_0':dict(frame=500,phase=2),'player_1':dict(frame=900,phase=2)}

    def advance_settlement(self):
        self.steps.append(self.frame_skip);self.elapsed+=self.frame_skip
        for p,start in (('player_0',500),('player_1',900)):
            self.process_infos[p]=dict(frame=start+self.elapsed,phase=3 if self.elapsed>=self.winners_after else 2)


class SettlementTests(unittest.TestCase):
    def test_step_one_regression_and_all_policy_cadences_have_same_game_budget(self):
        for stride in (1,12,60):
            env=JudgingEnv(stride)
            # Reproduce the original loop's failure at cadence one.
            if stride==1:
                for _ in range(120):env.advance_settlement()
                self.assertTrue(all(i['phase']==2 for i in env.process_infos.values()))
                env=JudgingEnv(stride)
            list(settlement_steps(env))
            self.assertEqual(env.elapsed,360);self.assertEqual(env.steps,[30]*12)
            self.assertEqual(env.frame_skip,stride)
            self.assertTrue(all(i['phase']==3 for i in env.process_infos.values()))

    def test_budget_is_measured_in_presents_and_does_not_overshoot(self):
        env=JudgingEnv(1,winners_after=1000)
        with self.assertRaisesRegex(TimeoutError,'95 settlement presents'):list(settlement_steps(env,max_frames=95))
        self.assertEqual(env.steps,[30,30,30,5]);self.assertEqual(env.elapsed,95)
        self.assertEqual(env.frame_skip,1)

    def test_winners_at_budget_boundary_succeeds_and_already_winners_does_not_step(self):
        env=JudgingEnv(12,winners_after=90);list(settlement_steps(env,max_frames=90))
        self.assertEqual(env.elapsed,90);self.assertEqual(env.frame_skip,12)
        list(settlement_steps(env,max_frames=90));self.assertEqual(len(env.steps),3)

    def test_cancel_wall_deadline_and_bad_barrier_restore_stride(self):
        stop=threading.Event();stop.set();env=JudgingEnv(1)
        with self.assertRaises(InterruptedError):list(settlement_steps(env,stop))
        self.assertEqual(env.steps,[]);self.assertEqual(env.frame_skip,1)
        env=JudgingEnv(12);env.timed_out=True
        with self.assertRaises(TimeoutError):list(settlement_steps(env))
        self.assertEqual(env.frame_skip,12)
        env=JudgingEnv(1);env.advance_settlement=lambda:None
        with self.assertRaisesRegex(AssertionError,'barrier'):list(settlement_steps(env))
        self.assertEqual(env.frame_skip,1)


if __name__=='__main__':unittest.main()
