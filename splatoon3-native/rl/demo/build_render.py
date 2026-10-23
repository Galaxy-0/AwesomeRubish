"""Build a default-strict isolated renderer variant; production binaries untouched."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
from rl.native_start import validate_runtime
from rl.demo.build_host import ROOT, sha
from rl.demo.build_profile import replace
from tools.build_a7_host import build_inputs


def build(out):
    out = Path(out).resolve()
    if not out.is_relative_to(ROOT / "work/rl-demo") or out.exists():
        raise ValueError("fresh work/rl-demo directory required")
    parent = ROOT / "work/rl-demo/host-r5/dmhost-demo"
    validate_runtime(parent, parent.parent / "modules", allow_demo=True)
    record = json.loads(parent.with_suffix(".build.json").read_text())
    protected = json.loads((parent.parent / "protected.json").read_text()) | {
        str(parent.relative_to(ROOT)): sha(parent)
    }
    out.mkdir(parents=True)
    header = Path(__file__).with_name("render_predicate.inc")
    shutil.copyfile(header, out / header.name)
    text = (parent.parent / "nvn_mtl.m").read_text()
    text = replace(
        text,
        "void mtl_sub_begin(void) {",
        f'#include "{out / header.name}"\nvoid mtl_sub_begin(void) {{\n    demo_pred_begin();',
    )
    text = replace(
        text,
        "    NSArray<dispatch_block_t> *commit_blocks = [g_commit_blocks copy];",
        "    unsigned demo_n;uint64_t *demo_requests=demo_pred_take(&demo_n);\n    NSArray<dispatch_block_t> *commit_blocks = [g_commit_blocks copy];",
    )
    text = replace(
        text,
        "        free(ops);",
        "        free(ops);\n        demo_pred_publish(demo_requests,demo_n,fence);",
    )
    text = replace(
        text,
        "                const p_render_enable *c = a;",
        "                const p_render_enable *c = a;\n                if(demo_predicate(c->conditional,c->addr,c->mode,&g_render_enable))break;",
    )
    text = replace(text, "void mtl_set_frame(uint64_t f) {", "void mtl_set_frame(uint64_t f) { demo_pred_frame(f);")
    (out / "nvn_mtl.m").write_text(text)
    command = list(record["command"])
    command[command.index("-o") + 1] = str(out / "dmhost-demo")
    command[command.index(str(parent.parent / "nvn_mtl.m"))] = str(out / "nvn_mtl.m")
    sources = (
        set(build_inputs(command))
        | {ROOT / p for p in record["source_sha256"]}
        | {
            Path(__file__).resolve(),
            header,
            out / header.name,
            Path(__file__).with_name("build_profile.py"),
        }
    )
    frozen = {str(p.relative_to(ROOT)): sha(p) for p in sorted(sources)}
    with (out / "build.log").open("w") as log:
        subprocess.run(
            command,
            cwd=ROOT / "upstream/dm/host",
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    host = out / "dmhost-demo"
    shutil.copytree(parent.parent / "modules", out / "modules")
    record.update(
        output=str(host.relative_to(ROOT)),
        output_sha256=sha(host),
        command=command,
        source_sha256=frozen,
        predicate_experiment=True,
        predicate_default="strict",
        render_deviation_only=True,
    )
    host.with_suffix(".build.json").write_text(json.dumps(record, indent=2) + "\n")
    assert all(sha(ROOT / p) == v for p, v in protected.items())
    (out / "protected.json").write_text(json.dumps(protected, indent=2) + "\n")
    print(host)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    build(p.parse_args().out)
