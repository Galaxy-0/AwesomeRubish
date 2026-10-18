"""Standalone policy worker: stdio JSON only; no referee/native imports."""
import contextlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
root=Path(sys.argv[1]);public_lib=Path(sys.argv[2])
sys.path.insert(0,str(public_lib));sys.path.insert(0,str(root))
wire=sys.stdout
with contextlib.redirect_stdout(sys.stderr):
    spec=importlib.util.spec_from_file_location('arena_user_policy',root/'policy.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
wire.write('{"ready":true}\n');wire.flush()
for line in sys.stdin:
    obs=json.loads(line)
    if obs.get('schema')!='arena.policy.v1':raise ValueError('policy schema required')
    with contextlib.redirect_stdout(sys.stderr):action=module.act(obs)
    wire.write(json.dumps(action,allow_nan=False,separators=(',',':'))+'\n');wire.flush()
