"""Periodic human recording plus per-session read-only native panel identity.

Direct aim remains forbidden. Lifecycle probes in the inherited private module
are disabled (no callbacks); panel hooks are bounded to stage construction.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from .build_host import ROOT, sha
from .build_profile import replace
from rl.native_start import validate_runtime
from tools.build_a7_host import build_inputs


def build(out):
    out=Path(out).resolve()
    parent=ROOT/'work/rl-demo/periodic-host-r2'
    old=parent/'dmhost-demo'
    validate_runtime(old,parent/'modules',allow_demo=True)
    if out.exists() or not out.is_relative_to(ROOT/'work/rl-demo'):raise ValueError('fresh private demo path required')
    out.mkdir(parents=True)
    rec=json.loads(old.with_suffix('.build.json').read_text())
    panel_parent=ROOT/'work/rl-demo/truth-host-panel-uv-r1'
    panels=(panel_parent/'truth_panels.inc').read_text().replace('!getenv("DM_TEST_DEMO_TRUTH") || !demo_capture_enabled()', '!getenv("DM_DEMO_INK_EVERY") || !getenv("DM_TEST_DEMO")')
    (out/'recording_panels.inc').write_text(panels)
    hle_parent=ROOT/'work/rl-demo/data-host-r3/hle_rl.c'
    text=hle_parent.read_text()
    text=replace(text,'static void own_player(const uint64_t *r) {',f'#include "{out / "recording_panels.inc"}"\nstatic void own_player(const uint64_t *r) {{')
    text=replace(text,'    d3r_init();','    gate_obs_set(56,truth_panels_before);gate_obs_set(57,truth_panels_after);\n    d3r_init();')
    (out/'hle_rl.c').write_text(text)
    dispatch=ROOT/'work/rl-demo/truth-host-panels-r2/hle.c'
    command=[str(out/'hle_rl.c') if x==str(hle_parent) else str(dispatch) if Path(x).name=='hle.c' else x for x in rec['command']]
    command[command.index('-o')+1]=str(out/'dmhost-demo')
    inputs=set(build_inputs(command)) | {ROOT/p for p in rec['source_sha256']} | {Path(__file__).resolve(),out/'recording_panels.inc'}
    frozen={str(p.relative_to(ROOT)):sha(p)for p in inputs}
    with(out/'build.log').open('w')as f:subprocess.run(command,cwd=ROOT/'upstream/dm/host',stdout=f,stderr=subprocess.STDOUT,check=True)
    shutil.copytree(panel_parent/'modules',out/'modules')
    host=out/'dmhost-demo'
    rec.update(output=str(host.relative_to(ROOT)),output_sha256=sha(host),command=command,source_sha256=frozen,periodic_ink_panels=True,private_module_sha256={p.name:sha(p)for p in(out/'modules').iterdir()if p.is_file()})
    host.with_suffix('.build.json').write_text(json.dumps(rec,indent=2)+'\n')
    protected=json.loads((parent/'protected.json').read_text()) | {str(old.relative_to(ROOT)):sha(old)}
    assert all(sha(ROOT/p)==h for p,h in protected.items())
    (out/'protected.json').write_text(json.dumps(protected,indent=2)+'\n')
    print(host,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True)
    build(p.parse_args().out)
