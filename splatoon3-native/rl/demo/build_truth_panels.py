"""Fresh read-only ColPaint UV-boundary survey host; production untouched."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from .build_host import ROOT, sha
from .build_profile import replace
from rl.native_start import validate_runtime
from tools.build_a7_host import build_inputs


def build(out):
    parent=ROOT / "work/rl-demo/truth-host-r2c";out=Path(out).resolve()
    validate_runtime(parent / "dmhost-truth",parent / "modules")
    if out.exists() or not out.is_relative_to(ROOT / "work/rl-demo"):raise ValueError("fresh private path required")
    out.mkdir(parents=True)
    rec=json.loads((parent / "dmhost-truth.build.json").read_text())
    header=Path(__file__).with_name("truth_panels.inc");shutil.copyfile(header,out / header.name)
    command=list(rec["command"])
    old_rl=Path(next(v for v in command if Path(v).name=="hle_rl.c"))
    text=old_rl.read_text()
    text=replace(text,"static void own_player(const uint64_t *r) {",f'#include "{out / header.name}"\nstatic void own_player(const uint64_t *r) {{')
    text=replace(text,"    d3r_init();","    gate_obs_set(56,truth_panels_before);gate_obs_set(57,truth_panels_after);\n    d3r_init();")
    (out / "hle_rl.c").write_text(text)
    old_dispatch=Path(next(v for v in command if Path(v).name=="hle.c"))
    (out / "hle.c").write_text(replace(old_dispatch.read_text(),"#define OBS_MAX 56","#define OBS_MAX 58"))
    command=[str(out / "hle_rl.c")if v==str(old_rl)else str(out / "hle.c")if v==str(old_dispatch)else v for v in command]
    command[command.index("-o")+1]=str(out / "dmhost-truth")
    rewrite=out / "rewrite.py"
    base=(ROOT / "work/rl-demo/truth-host-r2b/rewrite.py").read_text()
    needle="'28c4287aee36f7499da60f3e68b54c70': [\n"
    rewrite.write_text(replace(base,needle,needle+"    (0x36e5ae8,56,'d104c3ff','truth: ColPaint native panel UV input boundary; readonly'),\n    (0x36a5710,57,'f94002a8','truth: ColPaint native panel UV output boundary; readonly'),\n"))
    shutil.copytree(parent / "modules",out / "modules")
    env={k:v for k,v in os.environ.items()if not k.startswith("DM_")};env["DM_RULESET"]="native"
    with(out / "rewrite.log").open("w")as f:subprocess.run([sys.executable,str(rewrite),str(ROOT / "work/data/v720896/ExeFS/main"),str(out / "modules"),"main"],env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    inputs=set(build_inputs(command)) | {ROOT / p for p in rec["source_sha256"]} | {header,Path(__file__).resolve(),rewrite,out / header.name}
    frozen={str(p.relative_to(ROOT)):sha(p)for p in inputs}
    with(out / "build.log").open("w")as f:subprocess.run(command,cwd=ROOT / "upstream/dm/host",stdout=f,stderr=subprocess.STDOUT,check=True)
    host=out / "dmhost-truth"
    rec.update(output=str(host.relative_to(ROOT)),output_sha256=sha(host),command=command,source_sha256=frozen,native_truth_panels=True,private_module_sha256={p.name:sha(p)for p in(out / "modules").iterdir()if p.is_file()})
    host.with_suffix(".build.json").write_text(json.dumps(rec,indent=2)+"\n")
    protected=json.loads((parent / "protected.json").read_text()) | {str((parent / "dmhost-truth").relative_to(ROOT)):sha(parent / "dmhost-truth")}
    assert all(sha(ROOT / p)==h for p,h in protected.items())
    (out / "protected.json").write_text(json.dumps(protected,indent=2)+"\n")
    print(host,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--out",required=True);build(p.parse_args().out)
