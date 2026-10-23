"""Resource safety must survive moving CLI polling off the control thread."""

import threading
import time
import unittest
from unittest.mock import patch
from rl.demo.capture import AsyncDemoMonitor, DemoMonitor


def monitor():
    m = object.__new__(AsyncDemoMonitor)
    m.worker = None
    m.error = None
    m.worker_started = None
    m.latest = None
    return m


class MonitorTests(unittest.TestCase):
    def test_collect_does_not_block_input_thread_and_joins(self):
        m = monitor()
        release = threading.Event()
        entered = threading.Event()

        def sample(self, hosts):
            entered.set()
            release.wait(2)
            return dict(hosts=hosts)

        with patch.object(DemoMonitor, "sample", sample):
            self.assertIsNone(m.sample(["owned"]))
            self.assertTrue(entered.wait(1))
            self.assertTrue(m.worker.is_alive())
            release.set()
            m.finish()
            self.assertEqual(m.latest, dict(hosts=["owned"]))
            self.assertFalse(m.worker.is_alive())

    def test_original_limit_failure_reaches_control_and_close(self):
        m = monitor()
        with patch.object(
            DemoMonitor,
            "sample",
            side_effect=RuntimeError("additional swapout exceeds 2 GiB"),
        ):
            m.sample([])
            m.worker.join(2)
            with self.assertRaisesRegex(RuntimeError, "2 GiB"):
                m.check_error()
            with self.assertRaisesRegex(RuntimeError, "2 GiB"):
                m.finish()

    def test_stale_sampler_fails_closed(self):
        m = monitor()
        release = threading.Event()
        with patch.object(
            DemoMonitor, "sample", side_effect=lambda hosts: release.wait(2)
        ):
            m.sample([])
            m.worker_started = time.monotonic() - 6
            with self.assertRaisesRegex(RuntimeError, "stale"):
                m.check_error()
            release.set()
            m.finish()


if __name__ == "__main__":
    unittest.main()
