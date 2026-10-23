"""Second isolated truth host: native projectile reset/tick/release gates."""

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
    out=Path(out).resolve()
    parent=ROOT / "work/rl-demo/truth-host-r1"
    validate_runtime(parent / "dmhost-truth", parent / "modules")
    if out.exists() or not out.is_relative_to(ROOT / "work/rl-demo"):
        raise ValueError("fresh private truth path required")
    out.mkdir(parents=True)
    rec=json.loads((parent / "dmhost-truth.build.json").read_text())
    for path in [*parent.glob("*.h"), *parent.glob("*.inc")]:
        shutil.copyfile(path,out / path.name)
    header=Path(__file__).with_name("truth_lifecycle.inc")
    shutil.copyfile(header,out / header.name)
    text=(parent / "hle_rl.c").read_text().replace(str(parent),str(out))
    text=replace(text,"static void own_player(const uint64_t *r) {",f'#include "{out / header.name}"\nstatic void own_player(const uint64_t *r) {{')
    text=replace(text,"    d3r_init();", "    gate_obs_set(52,truth_life_reset);gate_obs_set(53,truth_life_destroy);gate_obs_set(54,truth_life_tick);gate_obs_set(55,truth_life_release);\n    d3r_init();")
    (out / "hle_rl.c").write_text(text)
    old_dispatch=ROOT / "work/rl-stage0/camera-host-r9/hle.c"
    (out / "hle.c").write_text(replace(old_dispatch.read_text(),"#define OBS_MAX 52","#define OBS_MAX 56"))
    metal=(parent / "nvn_mtl.m").read_text()
    # High-resolution QA capture requests share the finite absolute schedule.
    metal=replace(metal, "if(take){", 'if(take){char shot[4096];snprintf(shot,sizeof shot,"%s/screen-%llu.png",ink_dir,f);dm_gfx_shot_at(0,shot);')
    (out / "nvn_mtl.m").write_text(metal)
    command=list(rec["command"])
    command[command.index("-o")+1]=str(out / "dmhost-truth")
    command=[str(out / "hle.c")if v==str(old_dispatch)else v.replace(str(parent),str(out))for v in command]
    rewrite=out / "rewrite.py"
    base=(ROOT / "work/rl-stage0/camera-host-r9/rewrite.py").read_text()
    needle="'28c4287aee36f7499da60f3e68b54c70': [\n"
    base=replace(base,needle,needle+"    (0x1a40970,52,'a9ba7bfd','truth: BulletMove reset entry; readonly'),\n    (0x1a408b8,53,'a9be7bfd','truth: BulletMove teardown entry; readonly'),\n    (0x1a41bbc,54,'d10303ff','truth: BulletMove tick entry; readonly'),\n    (0x18d15d0,55,'a9bc7bfd','truth: actor release entry; readonly'),\n")
    rewrite.write_text(base)
    shutil.copytree(parent / "modules",out / "modules")
    env={k:v for k,v in os.environ.items()if not k.startswith("DM_")};env["DM_RULESET"]="native"
    with(out / "rewrite.log").open("w")as f:
        subprocess.run([sys.executable,str(rewrite),str(ROOT / "work/data/v720896/ExeFS/main"),str(out / "modules"),"main"],env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    inputs=set(build_inputs(command)) | {ROOT / p for p in rec["source_sha256"]} | {header,Path(__file__).resolve(),rewrite} | set(out.glob("*.h")) | set(out.glob("*.inc"))
    frozen={str(p.relative_to(ROOT)):sha(p)for p in inputs}
    with(out / "build.log").open("w")as f:
        subprocess.run(command,cwd=ROOT / "upstream/dm/host",stdout=f,stderr=subprocess.STDOUT,check=True)
    host=out / "dmhost-truth"
    rec.update(output=str(host.relative_to(ROOT)),output_sha256=sha(host),source_sha256=frozen,command=command,
        native_truth_lifecycle=True,private_module_sha256={p.name:sha(p)for p in(out / "modules").iterdir()if p.is_file()})
    host.with_suffix(".build.json").write_text(json.dumps(rec,indent=2)+"\n")
    protected=json.loads((parent / "protected.json").read_text()) | {str((parent / "dmhost-truth").relative_to(ROOT)):sha(parent / "dmhost-truth")}
    assert all(sha(ROOT / p)==h for p,h in protected.items())
    (out / "protected.json").write_text(json.dumps(protected,indent=2)+"\n")
    print(host,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--out",required=True);build(p.parse_args().out)
