#!/usr/bin/env python3
"""Repeat actual filesystem/socket/deadline attacks in the A6 sandbox."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import test_a3_process
from arena.proficiency_process import ProficiencyProcess
from arena.config import PolicySpec
from arena.policy import OwnState,PublicPlayer,EnemyView,PolicyObservation
from arena.control_process import OwnSpecial,encode_control
import json


class Boundary(unittest.TestCase):
    def test_tournament_refuses_test_special_override(self):
        from arena.runner import tournament
        with patch.dict('os.environ', {'DM_TEST_SPECIAL': 'full'}):
            with self.assertRaisesRegex(ValueError, 'forbidden'):
                tournament(ROOT/'arena/policies/rush', ROOT/'arena/policies/high-ground')

    def test_existing_baselines_accept_control_wire(self):
        import test_a5_process
        from arena.control_process import ControlProcess
        with patch.object(test_a5_process,'PolicyProcess',ControlProcess):
            test_a5_process.ExamplePolicyProcesses().test_two_examples_accept_only_public_observation()

    def test_own_special_rejects_foreign_and_stale(self):
        from test_a3_components import snapshot
        from arena.visibility import PolicyProjector
        obs=PolicyProjector('match').observe(snapshot(),'a')
        with self.assertRaises(TypeError):encode_control(snapshot())
        with self.assertRaises(ValueError):encode_control(obs,OwnSpecial('b',obs.frame,1.))
        with self.assertRaises(ValueError):encode_control(obs,OwnSpecial('a',obs.frame,float('nan')))
        payload=json.loads(encode_control(obs,OwnSpecial('a',obs.frame-9,1.)))
        self.assertIsNone(payload['own']['special'])
        payload=json.loads(encode_control(obs,OwnSpecial('a',obs.frame,1.)))
        self.assertEqual(payload['own']['special'],1.)
        self.assertNotIn('special',payload['enemies'][0])
    def test_staging_keeps_private_files_and_sockets_denied(self):
        with patch.object(test_a3_process,'PolicyProcess',ProficiencyProcess):
            test_a3_process.ChildBoundary().test_actual_child_denied_truth_socket_and_other_policy()

    def test_staging_deadline(self):
        with patch.object(test_a3_process,'PolicyProcess',ProficiencyProcess):
            test_a3_process.ChildBoundary().test_deadline_kills_busy_policy()

    def test_reference_imports_both_libraries(self):
        spec=PolicySpec.load(ROOT/'arena/proficiency-reference')
        own=OwnState(PublicPlayer('player_0',0,8000,True),(0.,3.,8.),0.,1.,1.,10,
                     form_squid=False,submerged=False,view_yaw=0.,view_pitch=0.)
        obs=PolicyObservation('test',10,own,(EnemyView(PublicPlayer('player_1',1,8000,True),False),),175.,1)
        with tempfile.TemporaryDirectory(dir=ROOT/'work/tests',prefix='a6-process-') as temp:
            with ProficiencyProcess(spec.root,Path(temp)/'worker.log') as worker:
                self.assertEqual(worker.act(obs)['buttons'],[0]*6)


if __name__=='__main__':unittest.main()
