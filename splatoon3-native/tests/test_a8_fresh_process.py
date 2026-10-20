import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from arena import native_runtime
from test_a8 import continuous_fallback_basis


class FreshProcessTests(unittest.TestCase):
    def test_default_cannot_hide_a_continuity_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);arena=root/'arena';arena.mkdir();host=root/'host';host.write_bytes(b'fixture')
            modules=root/'modules';modules.mkdir();(modules/'main.obs.tsv').write_text('fixture')
            host.with_suffix('.build.json').write_text(json.dumps(dict(render_mode='camera',copy_mode='none')))
            mode=arena/'default-runtime.json';certificate=root/'accepted.json'
            digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            mode.write_text(json.dumps(dict(host='host',patched='modules',host_sha256=digest(host),patched_sha256={'main.obs.tsv':digest(modules/'main.obs.tsv')},acceptance='accepted.json',session_lifecycle='fresh_per_match')))
            accepted=dict(passed=True,full_a8_passed=True,comparison=dict(equivalence_passed=True),host_build=dict(output_sha256=digest(host)))
            certificate.write_text(json.dumps(accepted))
            with patch.object(native_runtime,'DEFAULT_RUNTIME',mode),patch.object(native_runtime,'validate_runtime',return_value=(host,modules)):
                with self.assertRaisesRegex(ValueError,'lifecycle'):native_runtime.default_runtime()
                accepted['session_lifecycle']='fresh_per_match';certificate.write_text(json.dumps(accepted))
                with self.assertRaisesRegex(ValueError,'known issue'):native_runtime.default_runtime()
                accepted['continuous_fallback']=dict(accepted_known_issue=True);certificate.write_text(json.dumps(accepted))
                self.assertEqual(native_runtime.default_runtime()['host'],str(host))

    def test_fresh_factory_never_retains_a_native_room(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);host=root/'host';modules=root/'modules';mode=root/'mode.json'
            mode.write_text(json.dumps(dict(session_lifecycle='fresh_per_match')))
            host.with_suffix('.build.json').write_text(json.dumps(dict(render_mode='camera')))
            with patch.object(native_runtime,'DEFAULT_RUNTIME',mode),patch.object(native_runtime,'validate_runtime',return_value=(host,modules)),patch.object(native_runtime,'NativeSession') as session,patch.object(native_runtime,'NativeSessionPool') as pool:
                first,second=object(),object();session.side_effect=[first,second]
                options=native_runtime.env_options(dict(host=str(host),patched=str(modules)))
                self.assertIsNone(options['session_releaser']);self.assertFalse(options['pixels'])
                self.assertIs(options['session_factory'](players=2),first)
                self.assertIs(options['session_factory'](players=2),second)
                self.assertEqual(session.call_count,2);pool.assert_not_called()

    def test_invalid_lifecycle_cannot_silently_enable_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            mode=Path(directory)/'mode.json';mode.write_text(json.dumps(dict(session_lifecycle='typo')))
            with patch.object(native_runtime,'DEFAULT_RUNTIME',mode):
                with self.assertRaisesRegex(ValueError,'lifecycle'):native_runtime.env_options(dict(host='unused',patched='unused'))

    def test_fallback_requires_all_three_experiments(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);host=root/'host';host.write_bytes(b'fixture');diagnostic=root/'diagnostic.json';bo3=root/'bo3.json';decision=root/'decision.json'
            diagnostic.write_text(json.dumps(dict(completed=True,fix_validated=False,cases={'immediate':{}})));bo3.write_text('{}')
            sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            record=dict(schema='arena.a8.continuous-fallback.v1',decision='user_acceptance_with_fresh_processes',decision_date='2026-10-21',host_sha256=sha(host),session_lifecycle='fresh_per_match',diagnostics=dict(path=str(diagnostic),sha256=sha(diagnostic)),bo3=dict(path=str(bo3),sha256=sha(bo3)))
            decision.write_text(json.dumps(record))
            def read(path):
                if Path(path)==Path(__file__).resolve().parents[1]/'arena/default-runtime.json':return dict(session_lifecycle='fresh_per_match')
                return json.loads(Path(path).read_text())
            with patch('test_a8.read',side_effect=read):
                with self.assertRaisesRegex(AssertionError,'three diagnostic experiments incomplete'):continuous_fallback_basis(decision,host)
            record['host_sha256']='wrong';decision.write_text(json.dumps(record))
            with self.assertRaisesRegex(AssertionError,'host/lifecycle'):continuous_fallback_basis(decision,host)


if __name__=='__main__':unittest.main()
