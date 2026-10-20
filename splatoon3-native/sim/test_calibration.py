"""Offline plan and opt-in gate tests. Never import/start a native collector."""
import contextlib
import io
import sys
import unittest
from unittest.mock import patch

from .calibration.__main__ import main
from .calibration.plan import LEVELS,loadout,suite


class CalibrationTests(unittest.TestCase):
    def test_exact_ap_valid_config_and_unique_case_ids(self):
        from rl.loadout import encode_loadout
        for ap in LEVELS:
            gear=loadout('run_speed_up',ap)
            encode_loadout(gear)
            actual=sum(10*(v['main']=='run_speed_up')+3*v['subs'].count('run_speed_up') for v in gear.values())
            self.assertEqual(actual,ap)
        plan=suite();ids=[c['id'] for c in plan['cases']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual({c['stage'] for c in plan['cases']},{1,2,3})
        self.assertFalse(plan['active_native_execution'])
        self.assertEqual(plan['priority_followups'][0]['id'],'opening-and-observation-protocol')
        self.assertTrue(all(p['priority']=='P0' and p['status'].startswith('pending') for p in plan['priority_followups']))

    def test_default_entry_does_not_import_native_collector(self):
        with patch.dict(sys.modules,{'sim.calibration.native':None}):
            with contextlib.redirect_stdout(io.StringIO()) as output:self.assertEqual(main([]),0)
        self.assertIn('"native_started": false',output.getvalue())

    def test_execute_without_scheduled_window_rejected_before_import(self):
        with patch.dict(sys.modules,{'sim.calibration.native':None}):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:main(['--execute-native'])
        self.assertEqual(error.exception.code,2)

    def test_activity_inventory_only_reads_ps_and_detects_host_variants(self):
        from .calibration.native import active_native
        text='12 /tmp/dmhost-a7 /tmp/dmhost-a7 game\n13 /usr/bin/python python -m sim.ranking\n'
        with patch('subprocess.check_output',return_value=text) as call:
            self.assertEqual(len(active_native()),1)
        self.assertEqual(call.call_args.args[0][0],'ps')


if __name__=='__main__':unittest.main()
