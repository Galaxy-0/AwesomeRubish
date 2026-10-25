"""Decision labels must not substitute for actual input or native samples."""

import json
from pathlib import Path
import tempfile
import unittest
from .opponent_audit import audit
from . import test_opponent_report as fixtures


class AuditTests(unittest.TestCase):
    def test_actual_shooting_is_measured_independently_of_debug_fire(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures.ReportTests().fixture(root)
            path = root / "opponent-decisions.jsonl"
            path.write_text(
                json.dumps(dict(frame=0, mode="paint_advance", fire=False)) + "\n"
            )
            (root / "timing.jsonl").write_text(
                json.dumps(
                    dict(
                        sample_ns=0,
                        send_ns=2_000_000,
                        ack_ns=20_000_000,
                    )
                )
                + "\n"
            )
            r = audit(root)
            self.assertEqual(
                r["mode_effects"]["paint_advance"]["actual_ZR_fraction"], 1
            )
            self.assertEqual(r["combat_fire_decisions"], 0)
            self.assertEqual(r["python_input_work_ms"]["50"], 2)
