"""User acceptance never waives equivalence or changes the automatic 20% gate."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import contextlib
import io
import importlib.util
import sys
from unittest.mock import patch

from test_a8 import acceptance_basis
from arena import native_runtime
from analyze_a8_capacity import overlap_windows


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        # The production auditor records repository-relative paths. These
        # contract fixtures live in the OS temporary directory instead.
        fixture_reference=patch('test_a8.reference',side_effect=lambda p:dict(path=str(p),sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest()))
        fixture_reference.start();self.addCleanup(fixture_reference.stop)

    def test_below_threshold_needs_bound_decision_and_equivalence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);host=root/'host';host.write_bytes(b'fixture')
            build=dict(render_mode='camera',copy_mode='none')
            manifest=host.with_suffix('.build.json');manifest.write_text(json.dumps(build))
            digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            decision=dict(schema='arena.a8.user-decision.v1',decision='user_acceptance_below_20_percent',
                decision_date='2026-10-20',automatic_fps_ratio_threshold=1.2,
                host_sha256=digest(host),host_build_sha256=digest(manifest))
            path=root/'decision.json';path.write_text(json.dumps(decision))
            comparison=dict(passed=False,equivalence_passed=True,significant_speedup=False,performance=dict(fps_ratio=1.19179))
            with self.assertRaisesRegex(AssertionError,'significant speedup'):acceptance_basis(comparison,host,build)
            result=acceptance_basis(comparison,host,build,path)
            self.assertTrue(result['accepted_by_user']);self.assertFalse(result['automatic_performance_passed'])
            self.assertFalse(comparison['passed'])
            for changed in (dict(equivalence_passed=False),dict(performance=dict(fps_ratio=.99))):
                with self.assertRaisesRegex(AssertionError,'equivalence'):acceptance_basis(comparison|changed,host,build,path)
            for changed in (dict(copy_mode='coalesce'),dict(experimental_hdr=True),dict(test_only=True)):
                with self.assertRaisesRegex(AssertionError,'camera production'):acceptance_basis(comparison,host,build|changed,path)
            for changed in (dict(automatic_fps_ratio_threshold=1.19),dict(host_sha256='wrong')):
                path.write_text(json.dumps(decision|changed))
                with self.assertRaises(AssertionError):acceptance_basis(comparison,host,build,path)

    def test_default_selection_is_pinned_and_cannot_be_a_test_or_copy_host(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);arena=root/'arena';arena.mkdir();host=root/'host';host.write_bytes(b'fixture')
            modules=root/'modules';modules.mkdir();(modules/'main.obs.tsv').write_text('fixture')
            build=dict(render_mode='camera',copy_mode='none');manifest=host.with_suffix('.build.json')
            manifest.write_text(json.dumps(build));record=arena/'default-runtime.json'
            value=dict(host='host',patched='modules',host_sha256=hashlib.sha256(host.read_bytes()).hexdigest(),patched_sha256={'main.obs.tsv':hashlib.sha256((modules/'main.obs.tsv').read_bytes()).hexdigest()},acceptance='arena/accepted.json')
            record.write_text(json.dumps(value))
            certificate=arena/'accepted.json'
            certificate.write_text(json.dumps(dict(passed=True,full_a8_passed=True,comparison=dict(equivalence_passed=True),host_build=dict(output_sha256=value['host_sha256']))))
            with patch.object(native_runtime,'DEFAULT_RUNTIME',record),patch.object(native_runtime,'validate_runtime',return_value=(host,root/'modules')):
                self.assertEqual(native_runtime.default_runtime(),dict(host=str(host),patched=str(root/'modules')))
                for changed in (dict(test_only=True),dict(copy_mode='scatter'),dict(experimental_hdr=True),dict(render_mode='none')):
                    manifest.write_text(json.dumps(build|changed))
                    with self.assertRaisesRegex(ValueError,'camera-only production'):native_runtime.default_runtime()
                manifest.write_text(json.dumps(build));certificate.unlink()
                with self.assertRaisesRegex(ValueError,'not activated'):native_runtime.default_runtime()
                self.assertEqual(native_runtime.default_runtime(require_accepted=False)['host'],str(host))
                certificate.write_text(json.dumps(dict(passed=False)))
                with self.assertRaisesRegex(ValueError,'invalid'):native_runtime.default_runtime()
                host.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'selected revision'):native_runtime.default_runtime()

    def test_all_three_cli_entries_select_the_pinned_default(self):
        from arena import runner
        selected=native_runtime.default_runtime(require_accepted=False)
        with patch.object(native_runtime,'default_runtime',return_value=selected),patch.object(runner,'tournament',return_value=dict(passed=True)) as run,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(['--games','2','--parallel','1']),0)
        self.assertEqual(run.call_args.kwargs['native_runtime'],selected)
        root=Path(__file__).resolve().parents[1]
        for name,argv,call in [('t1_round',['--policy-a','arena/policies/rush','--policy-b','arena/policies/high-ground','--round','0','--out','work/not-started'],'run_round'),('proficiency',['--policy','arena/policies/rush','--out','work/not-started'],'run')]:
            spec=importlib.util.spec_from_file_location('selection_'+name,root/'tests'/(name+'.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            result=dict(passed=True,errors=[])
            with patch.object(native_runtime,'default_runtime',return_value=selected),patch.object(module,call,return_value=result) as run,patch.object(sys,'argv',[name,*argv]),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(),0)
            self.assertEqual(run.call_args.args[-1],selected)

    def test_four_room_capacity_requires_real_overlap_and_distinct_hosts(self):
        matches=[dict(round=n,attempt=0,host_pids=[2*n,2*n+1],controlled_start_wall=10+n,last_progress_wall=20+n) for n in range(4)]
        windows=overlap_windows(matches,4)
        self.assertEqual(len(windows),1);self.assertEqual(windows[0]['hosts'],8)
        self.assertEqual(windows[0]['overlap_seconds'],7)
        matches[-1]['controlled_start_wall']=30;matches[-1]['last_progress_wall']=40
        self.assertEqual(overlap_windows(matches,4),[])
        matches[-1].update(controlled_start_wall=13,last_progress_wall=23,host_pids=[0,1])
        with self.assertRaisesRegex(AssertionError,'PIDs overlap'):overlap_windows(matches,4)


if __name__=='__main__':unittest.main()
