#!/usr/bin/env python3
"""Censoring and score provenance; synthetic fixtures are never native proof."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.proficiency import scorecard,write_card,matching_card,merge_cards,report_cards


class Scores(unittest.TestCase):
    def setUp(self):
        # Numeric fixture checks must not depend on local licensed binaries.
        self.runtime=patch('arena.proficiency.evaluation_hashes',return_value={'numeric_fixture':'not-native'})
        self.runtime.start();self.addCleanup(self.runtime.stop)
    def test_missing_or_malformed_optional_report_card_is_unavailable(self):
        spec=SimpleNamespace(name='fixture',root=Path('/fixture/policy'),source_sha256='sha',loadout={},step_frames=None)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(report_cards([spec],tmp)['fixture']['status'],'unavailable')
            (Path(tmp)/'policy.json').write_text('{bad')
            self.assertEqual(report_cards([spec],tmp)['fixture']['status'],'unavailable')
    def test_censored_time_is_null_and_unverified_roll_not_zero(self):
        rows=[dict(scenario='stationary',status='measured',budget_frames=240,down_frame=None,
                   target_hp_loss=.7,native_evidence='numeric-fixture'),
              dict(scenario='approach',status='measured',budget_frames=240,down_frame=40,
                   target_hp_loss=1.,native_evidence='numeric-fixture',roll_verified=False)]
        card=scorecard('fixture','sha',{},rows)
        self.assertEqual(card['measured'],1)
        self.assertIsNone(card['trials'][0]['time_to_down_frames'])
        self.assertTrue(card['trials'][0]['right_censored'])
        self.assertEqual(card['trials'][1]['status'],'unsupported')
        self.assertIsNone(card['trials'][1]['score'])
        self.assertIsNone(card['approach_down_rate'])

    def test_revision_mismatch_and_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'card.json';card=scorecard('fixture','sha',{},[]);write_card(path,card)
            spec=SimpleNamespace(name='fixture',source_sha256='changed',loadout={},step_frames=None)
            self.assertEqual(matching_card(path,spec)['status'],'unavailable')
            spec.source_sha256='sha'
            self.assertEqual(matching_card(path,spec)['status'],'available')
            with patch('arena.proficiency.evaluation_hashes',return_value={'numeric_fixture':'changed'}):
                self.assertEqual(matching_card(path,spec)['status'],'unavailable')
            other=Path(tmp)/'other.json';write_card(other,dict(card,source_sha256='changed'))
            with self.assertRaises(ValueError):merge_cards([path,other])

    def test_same_native_trial_cannot_be_counted_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'card.json'
            card=scorecard('fixture','sha',{},[dict(scenario='stationary',status='measured',
                budget_frames=240,down_frame=None,target_hp_loss=0.,native_evidence='numeric-fixture')])
            path.write_text(__import__('json').dumps(card))
            with self.assertRaises(ValueError):merge_cards([path,path])


if __name__=='__main__':unittest.main()
