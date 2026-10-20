"""Fresh damage proof cannot bypass runtime and evidence integrity checks."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from test_a4 import accepted_damage

class RegressionProofTests(unittest.TestCase):
    def test_fresh_damage_binds_native_result_and_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory);runtime=d/'host';runtime.write_bytes(b'fixture')
            proof=d/'result.json';proof.write_text(json.dumps(dict(a1_damage_passed=True,probe_completed=True,errors=[],damage=[{'paused':False,'loss':.35},{'paused':True,'loss':.35}])))
            sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            job=d/'job.json';payload=dict(passed=True,runtime_sha256={str(runtime):sha(runtime)},evidence=[dict(path=str(proof),sha256=sha(proof),a1_damage_passed=True)])
            job.write_text(json.dumps(payload));self.assertFalse(accepted_damage(job)['reused_accepted_partial'])
            runtime.write_bytes(b'changed')
            with self.assertRaisesRegex(AssertionError,'runtime changed'):accepted_damage(job)
            runtime.write_bytes(b'fixture');proof.write_text('{}')
            with self.assertRaisesRegex(AssertionError,'proof invalid'):accepted_damage(job)
    def test_failed_or_ambiguous_job_is_never_inherited(self):
        with tempfile.TemporaryDirectory() as directory:
            job=Path(directory)/'job.json'
            for payload in [dict(passed=False),dict(passed=True,runtime_sha256={},evidence=[])]:
                job.write_text(json.dumps(payload))
                with self.assertRaises(AssertionError):accepted_damage(job)

if __name__=='__main__':unittest.main()
