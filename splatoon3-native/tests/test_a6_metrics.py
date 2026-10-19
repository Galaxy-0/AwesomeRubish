#!/usr/bin/env python3
"""Slow damage and duplicate packets cannot become a weapon-range hit."""
import unittest
from a6_metrics import large_hp_drops,roll_witness


class DamageTransitions(unittest.TestCase):
    def test_slow_loss_and_duplicate_sample_do_not_count_as_direct_hit(self):
        def sample(frame,hp):
            return dict(frame=frame,position_sample_frame=frame,hp=hp,hp_valid=True)
        before=sample(0,1.)
        slow=[sample(i,1.-i*.02) for i in range(1,21)]
        self.assertEqual(large_hp_drops(before,slow),[])
        self.assertEqual(large_hp_drops(before,slow+[sample(20,0.)]),[])
        events=large_hp_drops(before,slow+[sample(21,.25)])
        self.assertEqual(len(events),1)
        self.assertAlmostEqual(events[0]['hp_loss'],.35)

    def test_roll_requires_undamaged_boost_and_reversal_after_real_run_up(self):
        def sample(frame,position,hp=1.):
            return dict(frame=frame,position_sample_frame=frame,position=position,position_valid=True,
                        hp=hp,hp_valid=True,alive=True,referee_motion=dict(form_squid=1,ground_contact=0))
        start=sample(100,(0.,3.,0.));edge=sample(130,(3.5,3.,0.))
        arc=sample(138,(2.5,4.5,0.))
        self.assertTrue(roll_witness([start,edge],edge,[arc])['verified'])
        self.assertFalse(roll_witness([start,edge],edge,[sample(138,(4.,3.84,0.))])['verified'])
        self.assertFalse(roll_witness([start,edge],edge,[sample(138,(2.5,4.5,0.),.65)])['verified'])
        self.assertFalse(roll_witness([start,sample(130,(.2,3.,0.))],edge,[arc])['verified'])


if __name__=='__main__':unittest.main()
