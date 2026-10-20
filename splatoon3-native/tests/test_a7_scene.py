#!/usr/bin/env python3
"""Build-gated scene adapter contracts; does not launch the game."""
import os
from pathlib import Path
import subprocess
import tempfile
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

    def test_native_match_configuration_validates_maps_rules_teams_and_payload(self):
        cases=[(b'', 'Vss_District00 0 0 1'),
               (b'A7v1 Vss_Yagara 0 1 0\n','Vss_Yagara 0 1 0'),
               (b'A7v1 Vss_Yunohana 4 0 1\n','Vss_Yunohana 4 0 1'),
               *[(payload,None) for payload in (
                   b'A7v1 Plaza 0 0 1',b'A7v1 Vss_Yagara 5 0 1',
                   b'A7v1 Vss_Yagara 0 1 1',b'A7v1 Vss_Yagara 0 -1 1',
                   b'A7v1 Vss_Yagara 0 0 1 extra',b'A7v1 Vss_Yagara 0 0',
                   b'A7v1 Vss_Yagara 0 0 1\0junk',b'x'*256)]]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'control'
            for payload,expected in cases:
                with self.subTest(payload=payload):
                    path.write_bytes(payload)
                    result=subprocess.run([str(self.binary),'parse',str(path)],capture_output=True,text=True)
                    if expected is None:self.assertNotEqual(result.returncode,0)
                    else:
                        self.assertEqual(result.returncode,0,result.stderr)
                        self.assertEqual(result.stdout.strip(),expected)

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

    def test_upper_and_match_prototypes_require_explicit_dependencies(self):
        for target,mode,error in [(None,'upper-no-boot','require DM_SCENE_BOOT'),
                                  ('trace','upper-no-direct','requires DM_SCENE_DIRECT'),
                                  ('trace','upper-invalid','must be 0 or 1'),
                                  (None,'match-no-boot','require DM_SCENE_BOOT'),
                                  ('trace','match-relative','absolute control path'),
                                  ('trace','match-no-upper','requires upper create/join')]:
            with self.subTest(target=target,mode=mode):
                result=self.call(target,mode);self.assertNotEqual(result.returncode,0)
                self.assertIn(error,result.stderr)

    def test_flow_trace_preserves_memory_registers_and_deduplicates(self):
        result=self.call('trace','flow');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(result.stderr.count('A7_FLOW kind='),4)

    def test_private_setting_diagnostic_is_read_only_bounded_and_deduplicates(self):
        result=self.call('trace','flow-setting');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(result.stderr.count('A7_PRIVATE_SETTING '),2)
        self.assertIn('header=25,',result.stderr);self.assertIn('header=0,',result.stderr)
        self.assertIn('slots=0,1,3,3,3,3,3,3,3,3',result.stderr)

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
