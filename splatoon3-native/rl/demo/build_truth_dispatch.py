"""Fresh build fixing inherited dispatch-source selection, preserving failed boot."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
from .build_host import ROOT, sha
from rl.native_start import validate_runtime
from tools.build_a7_host import build_inputs


def build(parent,out):
    parent=Path(parent).resolve();out=Path(out).resolve()
    validate_runtime(parent / "dmhost-truth",parent / "modules")
    if out.exists() or not out.is_relative_to(ROOT / "work/rl-demo"):
        raise ValueError("fresh private path required")
    out.mkdir(parents=True)
    rec=json.loads((parent / "dmhost-truth.build.json").read_text())
    shutil.copyfile(parent / "hle.c",out / "hle.c")
    command=list(rec["command"])
    candidates=[i for i,v in enumerate(command)if Path(v).name=="hle.c"]
    if len(candidates)!=1:raise ValueError("unambiguous dispatch C input required")
    command[candidates[0]]=str(out / "hle.c")
    command[command.index("-o")+1]=str(out / "dmhost-truth")
    with(out / "build.log").open("w")as f:
        subprocess.run(command,cwd=ROOT / "upstream/dm/host",stdout=f,stderr=subprocess.STDOUT,check=True)
    shutil.copytree(parent / "modules",out / "modules")
    inputs=set(build_inputs(command)) | {ROOT / p for p in rec["source_sha256"]} | {Path(__file__).resolve()}
    host=out / "dmhost-truth"
    rec.update(output=str(host.relative_to(ROOT)),output_sha256=sha(host),command=command,
        source_sha256={str(p.relative_to(ROOT)):sha(p)for p in inputs},
        dispatch_source_corrected=True)
    host.with_suffix(".build.json").write_text(json.dumps(rec,indent=2)+"\n")
    protected=json.loads((parent / "protected.json").read_text())
    assert all(sha(ROOT / p)==h for p,h in protected.items())
    (out / "protected.json").write_text(json.dumps(protected,indent=2)+"\n")
    print(host,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--parent",required=True);p.add_argument("--out",required=True);a=p.parse_args();build(a.parent,a.out)
