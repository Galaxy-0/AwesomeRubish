#!/usr/bin/env python3
"""Exercise the coordinator's actual resource stop thresholds."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from m5_resources import Monitor

class ResourcePolicy(unittest.TestCase):
    def test_thresholds(self):
        baseline=dict(swapouts=100,page_size=16384,swap_mib=12000,pressure=1,compressor_mib=100,gpu={})
        with tempfile.TemporaryDirectory() as d, patch('m5_resources.system_sample',return_value=baseline):
            m=Monitor(d)
            warning=dict(baseline,pressure=2,swapouts=100+2**31//16384,swap_mib=14000)
            with patch('m5_resources.system_sample',return_value=warning):
                self.assertEqual(m.sample([])['new_swapout_bytes'],2**31)
            # Swap usage can fall while actual new swapout crosses the budget.
            with patch('m5_resources.system_sample',return_value=dict(warning,swapouts=warning['swapouts']+1,swap_mib=11000)):
                with self.assertRaisesRegex(RuntimeError,'swapout exceeds'):m.sample([])
            with patch('m5_resources.system_sample',return_value=dict(baseline,pressure=4)):
                with self.assertRaisesRegex(RuntimeError,'critical'):m.sample([])

if __name__=='__main__':unittest.main()
