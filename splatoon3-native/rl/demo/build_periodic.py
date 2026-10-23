"""Fresh demo-only asynchronous periodic ink host; accepted hosts stay frozen."""
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
    out = Path(out).resolve()
    parent = ROOT / 'work/rl-demo/data-host-r3'
    old = parent / 'dmhost-demo'
    validate_runtime(old, parent / 'modules', allow_demo=True)
    if out.exists() or not out.is_relative_to(ROOT / 'work/rl-demo'):
        raise ValueError('fresh private demo path required')
    out.mkdir(parents=True)
    rec = json.loads(old.with_suffix('.build.json').read_text())
    metal_parent = ROOT / 'work/rl-demo/data-host-r2/nvn_mtl.m'
    metal = metal_parent.read_text()
    # Completely remove the historical two synchronous survey snapshots.
    start = metal.index('static void demo_ink_frame(uint64_t f){')
    end = metal.index('// DM_NVN_TEXDUMP=size=', start)
    metal = metal[:start] + 'static void demo_ink_frame(uint64_t f){(void)f;}\nstatic void td_dump(void);\n' + metal[end:]
    header = Path(__file__).with_name('periodic_ink.inc')
    shutil.copyfile(header, out / header.name)
    metal = replace(metal, 'void mtl_exec(const uint8_t *p) {', 'static void demo_periodic_begin(void);\nvoid mtl_exec(const uint8_t *p) {\n    demo_periodic_begin();')
    metal = replace(metal, 'void td_note(MTL4RenderPassDescriptor *pd, NSUInteger nc) {', f'#include "{out / header.name}"\nvoid td_note(MTL4RenderPassDescriptor *pd, NSUInteger nc) {{\n    demo_periodic_note(pd,nc);')
    (out / 'nvn_mtl.m').write_text(metal)
    command = [str(out / 'nvn_mtl.m') if x == str(metal_parent) else x for x in rec['command']]
    command[command.index('-o') + 1] = str(out / 'dmhost-demo')
    sources = set(build_inputs(command)) | {ROOT / p for p in rec['source_sha256']} | {header, out / header.name, Path(__file__).resolve()}
    frozen = {str(p.relative_to(ROOT)):sha(p) for p in sources}
    with (out / 'build.log').open('w') as stream:
        subprocess.run(command, cwd=ROOT / 'upstream/dm/host', stdout=stream, stderr=subprocess.STDOUT, check=True)
    shutil.copytree(parent / 'modules', out / 'modules')
    host = out / 'dmhost-demo'
    rec.update(output=str(host.relative_to(ROOT)), output_sha256=sha(host), command=command, source_sha256=frozen, periodic_ink_async=True)
    host.with_suffix('.build.json').write_text(json.dumps(rec, indent=2)+'\n')
    protected = json.loads((parent / 'protected.json').read_text()) | {str(old.relative_to(ROOT)):sha(old)}
    assert all(sha(ROOT / p)==h for p,h in protected.items())
    (out / 'protected.json').write_text(json.dumps(protected,indent=2)+'\n')
    print(host,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True)
    build(p.parse_args().out)
