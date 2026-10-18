"""Exercise production Unix transport, delayed consumers and strict frame ACKs."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rl.protocol import Client


def neutral():return dict(sticks=np.zeros(4,np.float32),gyro=np.zeros(3,np.float32),buttons=np.zeros(6,np.int8))


class TransportTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='s3-rl-test-');self.path=Path(self.tmp.name)/'p.sock'
        self.process=None;self.client=None

    def start(self,skip=False):
        self.process=subprocess.Popen([str(ROOT/'upstream/dm/host/tests/build/t_rl'),str(self.path)]+(['skip'] if skip else []),stderr=subprocess.PIPE)
        deadline=time.monotonic()+5
        while not self.path.exists():
            if self.process.poll() is not None:raise RuntimeError(self.process.stderr.read())
            if time.monotonic()>deadline:raise TimeoutError('test socket')
            time.sleep(.01)
        self.client=Client(self.path,5);return self.client.receive()

    def tearDown(self):
        if self.client:self.client.close()
        if self.process:
            if self.process.poll() is None:self.process.terminate()
            self.process.wait(5);self.process.stderr.close()
        self.tmp.cleanup()

    def test_exact_steps_and_policy_delay(self):
        _,initial=self.start();frame=initial['frame']
        self.assertEqual(os.stat(self.path).st_mode&0o777,0o600)
        for k in (1,7,31,2):
            time.sleep(.05)
            action=neutral();action['buttons'][0]=1
            self.client.send_step(action,k);obs,info=self.client.receive()
            frame+=k;self.assertEqual(info['frame'],frame);self.assertEqual(info['advanced'],k)
            self.assertEqual(obs['pixels'].shape,(72,128,3));self.assertEqual(obs['pixels'].dtype,np.uint8)
        # The synthetic render loop encodes input in pixels; this is a transport
        # assertion only. Actual game action effects are checked in test_m6.py.
        self.assertTrue(np.all(obs['pixels']==191))

    def test_reject_invalid_client_action(self):
        self.start();action=neutral();action['sticks'][0]=float('nan')
        with self.assertRaises(ValueError):self.client.send_step(action,3)

    def test_native_reject_out_of_order_sequence(self):
        self.start();self.client.socket.sendall(b'STEP 2 3 0 0 0 0 0 0 0 0\n')
        self.assertNotEqual(self.process.wait(5),0)
        self.assertIn(b'RL invalid STEP',self.process.stderr.read())

    def test_native_reject_skipped_input_frame(self):
        self.start(skip=True);self.client.send_step(neutral(),3)
        self.assertNotEqual(self.process.wait(5),0)
        self.assertIn(b'RL input/present boundary mismatch',self.process.stderr.read())


if __name__=='__main__':unittest.main()
