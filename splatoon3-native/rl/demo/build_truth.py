"""Isolated controlled-combat truth survey. Never a human/arena runtime.

Preserves run67/68 binaries. Aim writes require all three fixture flags;
the rest of the added instrumentation is read-only and default-off.
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from .build_host import ROOT, sha
from .build_profile import replace
from rl.native_start import validate_runtime
from tools.build_a7_host import build_inputs


def build(out):
    out = Path(out).resolve()
    parent = ROOT / "work/rl-demo/data-host-r3"
    validate_runtime(parent / "dmhost-demo", parent / "modules", allow_demo=True)
    if out.exists() or not out.is_relative_to(ROOT / "work/rl-demo"):
        raise ValueError("fresh private truth build required")
    out.mkdir(parents=True)
    rec = json.loads((parent / "dmhost-demo.build.json").read_text())
    previous = ROOT / "work/rl-demo/data-host-r2"
    for name in ["test_aim.h", "sensor.h", "bullet_sensor.h", "capture_sensors.inc"]:
        shutil.copyfile(previous / name, out / name)
    shutil.copyfile(parent / "capture_live.inc", out / "capture_live.inc")
    header = Path(__file__).with_name("truth_sensors.inc")
    shutil.copyfile(header, out / header.name)
    aim = (out / "test_aim.h").read_text()
    aim = replace(aim, 'd3r_file=NULL;', 'd3r_file=getenv("DM_TEST_AIM_FILE");')
    aim = replace(aim,
        'if(getenv("DM_TEST_AIM")||getenv("DM_TEST_AIM_FILE"))die("demo forbids direct aim");',
        'if(!getenv("DM_TEST_DEMO_TRUTH") || strcmp(getenv("DM_TEST_DEMO_TRUTH"),"1") || !getenv("DM_TEST_AIM") || strcmp(getenv("DM_TEST_AIM"),"1") || !d3r_file || d3r_file[0]!=\'/\')die("controlled truth requires explicit private aim fixture");')
    aim = replace(aim, "static void demo_native_projectile(uintptr_t,uintptr_t);",
        "static void demo_native_projectile(uintptr_t,uintptr_t);\nstatic void truth_projectile(uintptr_t,uintptr_t);")
    aim = replace(aim, " demo_native_projectile(p,off);", " demo_native_projectile(p,off);truth_projectile(p,off);")
    (out / "test_aim.h").write_text(aim)
    text = (parent / "hle_rl.c").read_text()
    for source in [ROOT / "work/rl-demo/host-r5", previous, parent]:
        for name in ["test_aim.h", "sensor.h", "bullet_sensor.h", "capture_sensors.inc", "capture_live.inc"]:
            text = text.replace(str(source / name), str(out / name))
    text = replace(text, "static void own_player(const uint64_t *r) {",
        f'#include "{out / header.name}"\nstatic void own_player(const uint64_t *r) {{')
    text = replace(text, "    demo_live_update(player,slot,health);",
        "    demo_live_update(player,slot,health);\n    truth_update(player,slot);")
    (out / "hle_rl.c").write_text(text)
    metal_parent = ROOT / "work/rl-demo/data-host-r2/nvn_mtl.m"
    metal = metal_parent.read_text()
    # A finite absolute-present schedule, supplied before the owned room starts.
    metal = replace(metal, "if(f-ink_base==600 || f-ink_base==1200){", "int take=0;const char *schedule=getenv(\"DM_DEMO_INK_SCHEDULE\");if(schedule){FILE *sf=fopen(schedule,\"r\");if(sf){unsigned long long want;while(fscanf(sf,\"%llu\",&want)==1)if(want==f)take=1;fclose(sf);}}\n        if(take){")
    metal = replace(metal, "ink_dir,f-ink_base);", "ink_dir,f);")
    (out / "nvn_mtl.m").write_text(metal)
    command = list(rec["command"])
    command[command.index("-o") + 1] = str(out / "dmhost-truth")
    command = [str(out / "hle_rl.c") if v == str(parent / "hle_rl.c") else str(out / "nvn_mtl.m") if v == str(metal_parent) else v for v in command]
    sources = set(build_inputs(command)) | {ROOT / p for p in rec["source_sha256"]} | {Path(__file__).resolve(), header} | set(out.glob("*.inc")) | set(out.glob("*.h"))
    frozen = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    with (out / "build.log").open("w") as stream:
        subprocess.run(command, cwd=ROOT / "upstream/dm/host", stdout=stream, stderr=subprocess.STDOUT, check=True)
    shutil.copytree(parent / "modules", out / "modules")
    host = out / "dmhost-truth"
    rec.update(output=str(host.relative_to(ROOT)), output_sha256=sha(host), source_sha256=frozen,
        command=command, test_only=True, test_feature="direct_aim_upper_bound", direct_aim=True,
        diagnostic="controlled native truth only; not a human demonstration", native_truth_survey=True)
    host.with_suffix(".build.json").write_text(json.dumps(rec, indent=2) + "\n")
    protected = json.loads((parent / "protected.json").read_text()) | {str((parent / "dmhost-demo").relative_to(ROOT)): sha(parent / "dmhost-demo")}
    assert all(sha(ROOT / p) == h for p, h in protected.items())
    (out / "protected.json").write_text(json.dumps(protected, indent=2) + "\n")
    print(host, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    build(parser.parse_args().out)
