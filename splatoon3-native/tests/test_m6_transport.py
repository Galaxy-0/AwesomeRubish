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

    def start(self,mode='',invalid=False):
        self.process=subprocess.Popen([str(ROOT/'upstream/dm/host/tests/build/t_rl'),str(self.path)]+(['invalid'] if invalid else [mode] if mode else []),stderr=subprocess.PIPE)
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
        observation,initial=self.start();frame=initial['frame']
        self.assertEqual(observation['position_valid'],1)
        self.assertEqual(observation['hp_valid'],1);self.assertEqual(observation['hp'][0],1)
        self.assertEqual(observation['time_valid'],1);self.assertGreater(observation['remaining_time'][0],179)
        self.assertEqual(observation['heading_valid'],1);self.assertAlmostEqual(float(observation['heading'][0]),np.pi,places=6)
        np.testing.assert_array_equal(observation['position'],[13.25,-2,7])
        np.testing.assert_array_equal(observation['ink'],[.625]);self.assertEqual(observation['ink_valid'],1)
        self.assertEqual(os.stat(self.path).st_mode&0o777,0o600)
        for k in (1,7,31,2):
            time.sleep(.05)
            action=neutral();action['buttons'][0]=1
            self.client.send_step(action,k);obs,info=self.client.receive()
            frame+=k;self.assertEqual(info['frame'],frame);self.assertEqual(info['advanced'],k);self.assertEqual(info['frames_without_input'],0)
            self.assertEqual(obs['pixels'].shape,(72,128,3));self.assertEqual(obs['pixels'].dtype,np.uint8)
        # The synthetic render loop encodes input in pixels; this is a transport
        # assertion only. Actual game action effects are checked in test_m6.py.
        self.assertTrue(np.all(obs['pixels']==191))

    def test_damage_and_recovery_reach_official_observation(self):
        observation,_=self.start(mode='damage')
        self.assertEqual(observation['hp'][0],1)
        for health in (.57,0,1):
            self.client.send_step(neutral(),1);observation,_=self.client.receive()
            self.assertEqual(observation['hp_valid'],1)
            self.assertAlmostEqual(float(observation['hp'][0]),health,places=6)

    def test_reject_invalid_client_action(self):
        self.start();action=neutral();action['sticks'][0]=float('nan')
        with self.assertRaises(ValueError):self.client.send_step(action,3)

    def test_invalid_native_position_is_masked(self):
        observation,info=self.start(invalid=True)
        self.assertEqual(observation['position_valid'],0)
        self.assertEqual(observation['hp_valid'],0);self.assertEqual(observation['hp'][0],0)
        self.assertEqual(observation['time_valid'],0);self.assertEqual(observation['remaining_time'][0],0)
        self.assertEqual(observation['heading_valid'],0);self.assertEqual(observation['heading'][0],0)
        self.assertEqual(observation['ink_valid'],0);self.assertEqual(observation['ink'][0],0)
        self.assertTrue(np.isfinite(observation['position']).all())
        self.assertLessEqual(info['position_sample_frame'],info['frame'])

    def test_native_reject_out_of_order_sequence(self):
        self.start();self.client.socket.sendall(b'STEP 2 3 0 0 0 0 0 0 0 0\n')
        self.assertNotEqual(self.process.wait(5),0)
        self.assertIn(b'RL invalid STEP',self.process.stderr.read())

    def test_no_input_frames_still_complete_exact_steps(self):
        _,info=self.start(mode='no-input');frame=info['frame']
        for k in (1,7,31):
            self.client.send_step(neutral(),k);_,info=self.client.receive();frame+=k
            self.assertEqual(info['frame'],frame);self.assertEqual(info['frames_without_input'],k)

    def test_settled_native_controller_ignores_later_actions(self):
        self.start(mode='settled');action=neutral();action['buttons'][0]=1
        self.client.send_step(action,7);obs,info=self.client.receive()
        self.assertEqual(info['phase'],2);self.assertEqual(info['action_ignored'],1)
        self.assertTrue(np.all(obs['pixels']==17))
        self.client.send_step(action,7);obs,info=self.client.receive()
        self.assertTrue(np.all(obs['pixels']==17))

    def test_repeated_input_returns_one_latched_action(self):
        self.start(mode='duplicate');action=neutral();action['buttons'][0]=1
        for k in (1,7,31):
            self.client.send_step(action,k);obs,info=self.client.receive()
            self.assertEqual(info['input_repeats'],k);self.assertEqual(info['advanced'],k)
            self.assertTrue(np.all(obs['pixels']==191))

    def test_query_at_paused_boundary_waits_for_next_budget(self):
        _,initial=self.start(mode='boundary')
        self.client.send_step(neutral(),1);_,first=self.client.receive()
        time.sleep(.05)
        self.client.send_step(neutral(),7);_,second=self.client.receive()
        self.assertEqual(first['frame'],initial['frame']+1)
        self.assertEqual(second['frame'],first['frame']+7)

    def test_native_reject_input_beyond_step_budget(self):
        self.start(mode='future');self.client.send_step(neutral(),3)
        self.assertNotEqual(self.process.wait(5),0)
        self.assertIn(b'RL input frame outside budget/backwards',self.process.stderr.read())

    def test_native_reject_input_from_earlier_frame(self):
        self.start(mode='early');self.client.send_step(neutral(),3)
        self.assertNotEqual(self.process.wait(5),0)
        self.assertIn(b'RL input frame outside budget/backwards',self.process.stderr.read())


class EnvironmentLifecycleTest(unittest.TestCase):
    def test_asynchronous_agent_settlement_keeps_all_processes_advancing(self):
        from rl.env import NativeParallelEnv
        env=NativeParallelEnv(players=2);calls=[]
        class Clock:
            def pause(self):return 0
            def resume(self):pass
        class Session:
            clock=Clock()
            def tick(self,sleep=False):pass
        class Peer:
            def __init__(self,name,phases):self.name=name;self.phases=iter(phases);self.sent=[]
            def send_step(self,action,k):
                self.sent.append(action);calls.append(('send',self.name,k))
            def receive(self):
                calls.append(('receive',self.name));return {},dict(phase=next(self.phases))
        first=Peer('player_0',[2,3]);second=Peer('player_1',[1,2])
        env.clients={'player_0':first,'player_1':second};env.session=Session();env.agents=env.possible_agents[:]
        try:
            with self.assertRaises(RuntimeError):env.reset()
            _,_,terms,_,_=env.step({a:neutral() for a in env.agents})
            self.assertEqual(terms,{'player_0':True,'player_1':False});self.assertEqual(env.agents,['player_1'])
            env.step({'player_1':neutral()})
            self.assertEqual(env.agents,[]);self.assertEqual(len(first.sent),2)
            self.assertTrue(all(not np.any(v) for v in first.sent[-1].values()))
            self.assertEqual([c[0] for c in calls],['send','send','receive','receive']*2)
        finally:env.session=None;env.clients={}


if __name__=='__main__':unittest.main()
