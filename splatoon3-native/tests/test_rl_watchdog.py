"""Production transport watchdog: policy time is excluded, actual stalls abort."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rl.clock import SharedClock
from rl.protocol import Client
from test_m6_transport import neutral


class WatchdogTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='s3-watch-');self.root=Path(self.tmp.name)
        self.clock=SharedClock(self.root/'clock');self.process=None;self.client=None

    def start(self,mode='',limit=.2):
        path=self.root/'p.sock'
        env=os.environ|dict(DM_RL_CLOCK_FILE=str(self.clock.path),DM_RL_CLOCK_MODE='fixed60',DM_RL_STALL_SECONDS=str(limit))
        self.process=subprocess.Popen([str(ROOT/'upstream/dm/host/tests/build/t_rl'),str(path),mode],env=env,stderr=subprocess.PIPE)
        deadline=time.monotonic()+5
        while not path.exists():
            if self.process.poll() is not None:raise RuntimeError(self.process.stderr.read())
            if time.monotonic()>deadline:raise TimeoutError('fixture socket')
            time.sleep(.01)
        self.client=Client(path,3);self.client.receive();self.clock.pause()

    def tearDown(self):
        if self.client:self.client.close()
        if self.process:
            if self.process.poll() is None:self.process.terminate()
            self.process.wait(5);self.process.stderr.close()
        self.clock.close();self.tmp.cleanup()

    def test_slow_progress_and_policy_pauses_outlive_limit(self):
        self.start()
        for _ in range(8):
            time.sleep(.15);self.clock.resume();self.client.send_step(neutral(),1)
            self.client.receive();self.clock.pause()
        self.assertIsNone(self.process.poll())

    def test_pause_with_outstanding_budget_is_excluded_then_real_stall_aborts(self):
        self.start('stall');self.client.send_step(neutral(),1)
        time.sleep(.65);self.assertIsNone(self.process.poll())
        self.clock.resume();self.assertNotEqual(self.process.wait(3),0)
        self.assertIn(b'RL_STALL no present progress',self.process.stderr.read())

    def test_long_step_with_progress_outlives_transport_and_stall_intervals(self):
        self.start('slow',limit=.4)
        self.client.socket.settimeout(.05)
        self.client.use_progress_watchdog()
        self.clock.resume();self.client.send_step(neutral(),10)
        started=time.monotonic();_,info=self.client.receive()
        self.assertGreater(time.monotonic()-started,.7)
        self.assertEqual(info['advanced'],10)
        self.assertIsNone(self.process.poll())

    def test_actual_stall_without_guest_wait_is_caught(self):
        self.start('stall');self.clock.resume();self.client.send_step(neutral(),1)
        self.assertNotEqual(self.process.wait(3),0)
        self.assertIn(b'RL_STALL no present progress',self.process.stderr.read())

    def test_long_policy_pause_can_resume_beyond_old_60_second_limit(self):
        self.start(limit=120)
        time.sleep(65)
        self.assertIsNone(self.process.poll())
        self.clock.resume();self.client.send_step(neutral(),1)
        _,info=self.client.receive();self.assertEqual(info['advanced'],1)

    def test_coordinator_default_allows_native_watchdog_to_report_first(self):
        from rl import NativeParallelEnv
        env=NativeParallelEnv(players=2)
        self.assertEqual(env.config['stall_timeout'],120)
        self.assertEqual(env.step_timeout,150)
        self.assertEqual(NativeParallelEnv(players=2,stall_timeout=7).step_timeout,37)
        for value in (0,-1,float('inf'),float('nan')):
            with self.assertRaises(ValueError):NativeParallelEnv(players=2,stall_timeout=value)

    def test_incremental_log_scans_keep_errors_across_frame_reads(self):
        from rl.session import Session
        session=Session.__new__(Session);session.out=self.root
        session._log_offsets={};session._log_tails={};session._log_frames={};session._log_failures={}
        (self.root/'player-0').mkdir();path=self.root/'player-0/host.log'
        path.write_text('RESOURCE_FRAME frame=41\nFA')
        self.assertEqual(session.frame(0),41)
        with path.open('a') as stream:stream.write('TAL failed\nRESOURCE_FRAME frame=42\n')
        self.assertEqual(session.frame(0),42)
        self.assertIsNotNone(session.scan_log(0))


if __name__=='__main__':unittest.main()
