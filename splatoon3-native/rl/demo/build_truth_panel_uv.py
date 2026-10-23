"""Bounded second panel survey: dereference native UV transform, same gates."""

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
    parent=ROOT / "work/rl-demo/truth-host-panels-r2";out=Path(out).resolve()
    validate_runtime(parent / "dmhost-truth",parent / "modules")
    if out.exists() or not out.is_relative_to(ROOT / "work/rl-demo"):raise ValueError("fresh private path required")
    out.mkdir(parents=True)
    rec=json.loads((parent / "dmhost-truth.build.json").read_text())
    old=parent / "truth_panels.inc"
    text=old.read_text()
    needle='        demo_hex(after?"panel_after":"panel_before",p,0x180,dm_guest_frame());'
    text=replace(text,needle,needle+'\n        uintptr_t uv=0;if(d2b_read(p+0x18,&uv,8))demo_hex(after?"panel_uv_after":"panel_uv_before",uv,0x80,dm_guest_frame());')
    (out / old.name).write_text(text)
    command=list(rec["command"])
    old_rl=Path(next(v for v in command if Path(v).name=="hle_rl.c"))
    (out / "hle_rl.c").write_text(old_rl.read_text().replace(str(old),str(out / old.name)))
    command=[str(out / "hle_rl.c")if v==str(old_rl)else v for v in command]
    command[command.index("-o")+1]=str(out / "dmhost-truth")
    inputs=set(build_inputs(command)) | {ROOT / p for p in rec["source_sha256"]} | {Path(__file__).resolve(),out / old.name}
    frozen={str(p.relative_to(ROOT)):sha(p)for p in inputs}
    with(out / "build.log").open("w")as f:subprocess.run(command,cwd=ROOT / "upstream/dm/host",stdout=f,stderr=subprocess.STDOUT,check=True)
    shutil.copytree(parent / "modules",out / "modules")
    host=out / "dmhost-truth"
    rec.update(output=str(host.relative_to(ROOT)),output_sha256=sha(host),source_sha256=frozen,command=command,native_truth_panel_uv=True)
    host.with_suffix(".build.json").write_text(json.dumps(rec,indent=2)+"\n")
    protected=json.loads((parent / "protected.json").read_text()) | {str((parent / "dmhost-truth").relative_to(ROOT)):sha(parent / "dmhost-truth")}
    assert all(sha(ROOT / p)==h for p,h in protected.items())
    (out / "protected.json").write_text(json.dumps(protected,indent=2)+"\n")
    print(host,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--out",required=True);build(p.parse_args().out)
