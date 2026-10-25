"""Recorder guard, warm-manifest inheritance and native mapping fail-closed."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from .capture import DemoSession
from .periodic_ink import normalize


class PeriodicTests(unittest.TestCase):
    def test_bc_sampling_phase_observes_periodic_source_tick(self):
        from .bc_sync import sampling_phase

        self.assertEqual(sampling_phase(2, [dict(frame=0), dict(frame=30)]), 1)
        self.assertEqual(sampling_phase(2, []), 0)
        self.assertEqual(sampling_phase(2, [dict(frame=0)], 0), 0)
        with self.assertRaises(ValueError):
            sampling_phase(2, [], 2)

    def test_warm_chain_retains_inherited_and_new_pipelines(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            prior = root / "prior"
            (prior / "player-0").mkdir(parents=True)
            (prior / "warm-0.tsv").write_text("S\tINHERITED\t0\n")
            (prior / "player-0/pso_user.tsv").write_text("C\tNEW\nS\tINHERITED\t0\n")
            (prior / "player-1").mkdir()
            (prior / "player-1/pso_user.tsv").write_text("C\tPEER\n")
            s = DemoSession.__new__(DemoSession)
            s.demo_native_survey = False
            s.demo_ink_every = 30
            s.demo_warm_session = prior
            s.demo_warm_chain = [prior]
            s.out = root / "next"
            s.out.mkdir()
            s.demo_resolution = None
            s.demo_predicate = "async"
            s.demo_present_link = 0
            with patch("rl.demo.capture.NativeSession.host_options", return_value={}):
                options = s.host_options(0)
            lines = (s.out / "warm-0.tsv").read_text().splitlines()
            self.assertIn("S\tINHERITED\t0", lines)
            self.assertIn("C\tNEW", lines)
            self.assertIn("C\tPEER", lines)
            self.assertEqual(lines.count("S\tINHERITED\t0"), 1)
            self.assertEqual(options["DM_DEMO_INK_EVERY"], "30")
            self.assertEqual(options["DM_HEADLESS"], "0")
            self.assertNotIn("DM_TEST_AIM", options)
            self.assertEqual(options["DM_NVN_PROF"], "1")

    def test_different_native_panel_table_is_never_qualified(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src = root / "rec"
            ref = root / "ref"
            src.mkdir()
            ref.mkdir()
            host = root / "host"
            host.with_suffix(".build.json").write_text(
                json.dumps(dict(periodic_ink_panels=True))
            )
            (src / "session/player-0").mkdir(parents=True)
            (src / "session/player-0/host.log").write_text("")
            (src / "result.json").write_text(
                json.dumps(
                    dict(map="Yunohana", host=str(host), session=str(src / "session"))
                )
            )
            np.savez(ref / "panels.npz", basis=np.array([1.0]))

            def extract(_src, out):
                out.mkdir()
                np.savez(out / "panels.npz", basis=np.array([2.0]))

            with patch("rl.demo.periodic_ink.extract", side_effect=extract):
                with self.assertRaisesRegex(ValueError, "differs"):
                    normalize(src, ref)
            self.assertFalse((src / "native-ink.json").exists())


if __name__ == "__main__":
    unittest.main()
