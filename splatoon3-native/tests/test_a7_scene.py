#!/usr/bin/env python3
"""Build-gated scene adapter contracts; does not launch the game."""
import os
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]


class SceneAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary=ROOT/'work/a7/t_spl3_scene';cls.binary.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['clang','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function',
                        '-I'+str(ROOT/'upstream/dm/host'),'-I'+str(ROOT/'upstream/dm/host/gen/0100C2500FC20000'),
                        str(ROOT/'upstream/dm/host/tests/t_spl3_scene.c'),'-o',str(cls.binary)],check=True)

    def call(self,target=None,mode=None):
        env={k:v for k,v in os.environ.items() if not k.startswith('DM_')}
        if target is not None:env['DM_SCENE_BOOT']=target
        return subprocess.run([str(self.binary),*([mode] if mode else [])],env=env,capture_output=True,text=True)

    def test_disabled_has_no_callbacks(self):self.assertEqual(self.call().returncode,0)

    def test_trace_and_one_shot_targets_preserve_native_strings_and_other_registers(self):
        for target in ('trace','ShootingRange','LobbyLocal'):
            with self.subTest(target=target):
                result=self.call(target);self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_unknown_build_or_missing_gates_fail_closed(self):
        for mode in ('unknown','missing'):
            with self.subTest(mode=mode):self.assertNotEqual(self.call('ShootingRange',mode).returncode,0)

    def test_bad_targets_or_unreadable_native_arguments_fail_closed(self):
        self.assertNotEqual(self.call('Versus').returncode,0)
        for mode in ('bad-string','bad-object'):
            with self.subTest(mode=mode):self.assertNotEqual(self.call('ShootingRange',mode).returncode,0)

    def test_direct_prototype_requires_scene_flow_and_verified_native_helpers(self):
        for target,mode in [(None,'direct-no-flow'),('LobbyLocal','direct-invalid'),('LobbyLocal','direct-no-flow'),
                            ('ShootingRange','direct-helper'),('LobbyLocal','direct-helper')]:
            with self.subTest(target=target,mode=mode):self.assertNotEqual(self.call(target,mode).returncode,0)

    def test_flow_trace_preserves_memory_registers_and_deduplicates(self):
        result=self.call('trace','flow');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(result.stderr.count('A7_FLOW kind='),4)

    def test_flow_trace_requires_valid_flag_and_gates(self):
        for mode in ('flow-missing','flow-invalid'):
            with self.subTest(mode=mode):self.assertNotEqual(self.call('trace',mode).returncode,0)

    def test_network_tracing_preserves_native_arguments_and_registers(self):
        result=self.call('trace','network');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('kind=create',result.stderr);self.assertIn('kind=join',result.stderr)

    def test_unavailable_network_diagnostic_does_not_interrupt_native_flow(self):
        result=self.call('trace','network-unavailable');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('argument_unavailable=1',result.stderr)

    def test_network_tracing_requires_valid_flag_and_matching_gates(self):
        for mode in ('network-missing','network-invalid'):
            with self.subTest(mode=mode):self.assertNotEqual(self.call('trace',mode).returncode,0)


if __name__=='__main__':unittest.main()
