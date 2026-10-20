"""Offline contracts for the coordinator-only native startup adapter."""
from pathlib import Path
import sys
import tempfile
import json
import os
import subprocess
import time
import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rl import NativeParallelEnv
from rl.native_start import room_ready,write_control,NativeSessionPool,NativeSession
from arena import native_runtime
from rl.clock import SharedClock
from rl.protocol import Client
from rl.session import NativeProcessExitError


class NativeStartTests(unittest.TestCase):
    def test_pair_requires_membership_session_and_native_idle(self):
        pair=['LDN state=3 node=0 nodes=2 session=abcdef\nA7_NET_ROOT state=34',
              'LDN state=5 node=1 nodes=2 session=abcdef\nA7_NET_ROOT state=34']
        self.assertTrue(room_ready(pair))
        for bad in [pair[:1],[pair[0],pair[1].replace('abcdef','123456')],
                    [pair[0],pair[1].replace('state=34','state=15')],
                    [pair[0],pair[1]+'\nLDN state=1 node=-1 nodes=0 session=000000']]:
            with self.subTest(bad=bad):self.assertFalse(room_ready(bad))

    def test_parameter_writer_replaces_complete_payload_and_rejects_unproven_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'go'
            write_control(path,3);self.assertEqual(path.read_text(),'A7v1 Vss_Yagara 0 0 1\n')
            write_control(path,1);self.assertEqual(path.read_text(),'A7v1 Vss_Yunohana 0 0 1\n')
            self.assertEqual(list(Path(directory).iterdir()),[path])
            for stage,mode in [(0,0),(2,1)]:
                with self.assertRaises(ValueError):write_control(path,stage,mode)

    def test_environment_releases_after_clients_and_closes_on_releaser_error(self):
        order=[];session=Mock();session.clock.resume.side_effect=lambda:order.append('resume')
        client=Mock();client.close.side_effect=lambda:order.append('release-client')
        infos={'player_0':{'phase':3},'player_1':{'phase':3}}
        def release(s,i):
            self.assertIs(s,session);self.assertIs(i,infos);order.append('return-session')
        env=NativeParallelEnv(players=2,session_releaser=release)
        env.session=session;env.clients={'player_0':client};env.process_infos=infos
        env.close();self.assertEqual(order,['resume','release-client','return-session'])
        session.close.assert_not_called();self.assertIsNone(env.session)
        env.session=session;env.session_releaser=Mock(side_effect=RuntimeError('failed release'))
        with self.assertRaisesRegex(RuntimeError,'failed release'):env.close()
        session.close.assert_called_once()

    def test_pool_only_retains_complete_native_winners(self):
        with patch('rl.native_start.validate_runtime',return_value=(Path('/host'),Path('/modules'))):
            pool=NativeSessionPool('/host','/modules')
        session=Mock();process=Mock();process.poll.return_value=None;session.hosts=[(0,process,None),(1,process,None)]
        for infos in ({},{'p0':{'phase':3,'score_valid':1}},
                      {'p0':{'phase':2,'score_valid':1},'p1':{'phase':3,'score_valid':1}},
                      {'p0':{'phase':3,'score_valid':0},'p1':{'phase':3,'score_valid':1}}):
            pool.release(session,infos);self.assertIsNone(pool.held)
        infos={p:{'phase':3,'score_valid':1} for p in ('p0','p1')}
        pool.release(session,infos);self.assertIs(pool.held,session)
        pool.close();self.assertIsNone(pool.held)

    def test_pool_reuses_only_compatible_equipment(self):
        with patch('rl.native_start.validate_runtime',return_value=(Path('/host'),Path('/modules'))):
            pool=NativeSessionPool('/host','/modules')
        config=dict(players=2,mode=0,stage_id=2,weapons=[8000,8000],timeout=900)
        session=Mock(closed=False);session.hosts=[(0,Mock(poll=Mock(return_value=None)),None)]
        pool.held=session;pool.identity=pool.equipment(config)
        self.assertIs(pool.acquire(**(config|dict(stage_id=3))),session)
        self.assertEqual(session.native_stage,3);self.assertTrue(session.pending_repeat)
        pool.held=session
        with patch('rl.native_start.NativeSession') as constructor:
            pool.acquire(**(config|dict(loadouts=[None,None])))
            constructor.assert_called_once();session.close.assert_called_once()

    def test_dead_retained_room_rebuilds_but_save_integrity_never_gets_swallowed(self):
        with patch('rl.native_start.validate_runtime',return_value=(Path('/host'),Path('/modules'))):
            pool=NativeSessionPool('/host','/modules')
        config=dict(players=2,mode=0,stage_id=2,weapons=[8000,8000],timeout=900)
        stale=Mock(closed=False);stale.hosts=[(0,Mock(poll=Mock(return_value=-6)),None)]
        stale.close.side_effect=NativeProcessExitError('unclean exit -6');pool.held=stale
        with patch('rl.native_start.NativeSession') as constructor:
            self.assertIs(pool.acquire(**config),constructor.return_value)
            self.assertEqual(len(pool.rebuilds),1);self.assertEqual(stale.check_saves.call_count,1)
        stale.check_saves.side_effect=RuntimeError('reference hash changed');pool.held=stale
        with self.assertRaisesRegex(RuntimeError,'reference hash changed'):pool.acquire(**config)

    def test_enabling_pixels_rebuilds_instead_of_reusing_elided_temporal_history(self):
        with patch('rl.native_start.validate_runtime',return_value=(Path('/host'),Path('/modules'))):
            pool=NativeSessionPool('/host','/modules')
        config=dict(players=2,mode=0,stage_id=2,weapons=[8000,8000],timeout=900,pixels=False)
        previous=Mock(closed=False);previous.hosts=[(0,Mock(poll=Mock(return_value=None)),None)]
        pool.held=previous;pool.identity=pool.equipment(config)
        with patch('rl.native_start.NativeSession') as constructor:
            self.assertIs(pool.acquire(**(config|dict(pixels=True))),constructor.return_value)
            previous.close.assert_called_once();constructor.assert_called_once()
            self.assertTrue(constructor.call_args.kwargs['pixels'])

    def test_status_keeps_native_scene_and_last_match_phase_distinct(self):
        session=NativeSession.__new__(NativeSession);session.generation=1
        session.hosts=[(0,Mock(pid=17),None)]
        session.text=lambda n:'PROBE main+0x3dd9370 #1\nA7_SCENE request=4 destination=LobbyLocal'
        status=session.status()['players'][0]
        self.assertEqual(status['scene'],'LobbyLocal');self.assertEqual(status['last_match_phase'],'winners')

    def test_native_opt_in_requires_a_pair_and_never_changes_default_environment(self):
        self.assertIsNone(native_runtime.from_args(SimpleNamespace(native_host=None,native_patched=None)))
        self.assertEqual(native_runtime.env_options(None),{})
        for host,patched in [('/host',None),(None,'/modules')]:
            with self.assertRaises(ValueError):native_runtime.from_args(SimpleNamespace(native_host=host,native_patched=patched))
        with patch.object(native_runtime,'validate_runtime',return_value=(Path('/host'),Path('/modules'))):
            self.assertEqual(native_runtime.from_args(SimpleNamespace(native_host='/host',native_patched='/modules')),
                             dict(host='/host',patched='/modules'))

    def test_coordinator_pool_is_process_local_and_explicitly_owned(self):
        native_runtime.close_pools()
        with patch.object(native_runtime,'NativeSessionPool') as constructor,patch.object(native_runtime,'Finalize'), \
             patch.object(Path,'read_text',return_value='{"render_mode":"camera"}'):
            pool=constructor.return_value;pool.patched=Path('/modules')
            runtime=dict(host='/host',patched='/modules')
            first=native_runtime.env_options(runtime);second=native_runtime.env_options(runtime)
            constructor.assert_called_once();self.assertEqual(first,second)
            self.assertEqual(first['session_factory'],pool.acquire)
            self.assertFalse(first['pixels'])
            native_runtime.close_pools();pool.close.assert_called_once()

    def test_scorecard_cannot_cross_runtime_even_with_identical_policy(self):
        from arena.proficiency import matching_card
        runtime=dict(host='/native-host',patched='/native-modules')
        spec=SimpleNamespace(name='fixture',source_sha256='same-policy',loadout={},step_frames=12)
        card=dict(schema='arena.proficiency.v1',policy=spec.name,source_sha256=spec.source_sha256,
                  loadout={},policy_step_frames=12,library_sha256={},evaluation_sha256={'route':'native'},native_runtime=runtime)
        with tempfile.TemporaryDirectory() as directory,patch('arena.proficiency.library_hashes',return_value={}),\
             patch('arena.proficiency.evaluation_hashes',side_effect=lambda r=None:{'route':'native' if r else 'menu'}):
            path=Path(directory)/'card.json';path.write_text(json.dumps(card))
            self.assertEqual(matching_card(path,spec,runtime)['status'],'available')
            self.assertEqual(matching_card(path,spec)['status'],'unavailable')
            card['native_runtime']=None;path.write_text(json.dumps(card))
            self.assertEqual(matching_card(path,spec,runtime)['status'],'unavailable')


class AttachBarrierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(['make','-C',str(ROOT/'upstream/dm/host/tests'),'GAME=0100C2500FC20000','build/t_rl'],check=True,stdout=subprocess.DEVNULL)

    def test_first_native_present_waits_for_delayed_attachment(self):
        starts=[]
        for delay in (.1,.35):
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory);clock=SharedClock(path/'clock');client=None
                env={k:v for k,v in os.environ.items() if not k.startswith('DM_')}
                env.update(DM_RL_WAIT_INGAME='1',DM_RL_CLOCK_MODE='fixed60',DM_RL_CLOCK_FILE=str(clock.path))
                process=subprocess.Popen([str(ROOT/'upstream/dm/host/tests/build/t_rl'),str(path/'p.sock')],env=env,stderr=subprocess.PIPE)
                try:
                    deadline=time.monotonic()+5
                    while not (path/'p.sock').exists():
                        if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('barrier fixture failed')
                        time.sleep(.01)
                    time.sleep(delay);client=Client(path/'p.sock',3)
                    _,info=client.receive();starts.append(info['frame'])
                    self.assertEqual(info['phase'],1)
                    from test_m6_transport import neutral
                    client.send_step(neutral(),7);_,after=client.receive()
                    self.assertEqual(after['frame']-info['frame'],7);self.assertEqual(after['advanced'],7)
                finally:
                    if client:client.close()
                    process.terminate();process.communicate(timeout=5);clock.close()
        self.assertEqual(starts,[1,1])


if __name__=='__main__':unittest.main()
