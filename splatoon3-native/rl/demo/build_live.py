"""Add passive per-frame pose/action candidates in a fresh private demo build."""

import argparse, json, shutil, subprocess
from pathlib import Path
from rl.demo.build_host import ROOT, sha
from rl.demo.build_profile import replace
from rl.native_start import validate_runtime
from tools.build_a7_host import build_inputs


def build(out):
    out = Path(out).resolve()
    parent = ROOT / "work/rl-demo/data-host-r2"
    old = parent / "dmhost-demo"
    if out.exists() or not out.is_relative_to(ROOT / "work/rl-demo"):
        raise ValueError("fresh demo path required")
    validate_runtime(old, parent / "modules", allow_demo=True)
    rec = json.loads(old.with_suffix(".build.json").read_text())
    out.mkdir(parents=True)
    header = Path(__file__).with_name("capture_live.inc")
    shutil.copyfile(header, out / header.name)
    text = (parent / "hle_rl.c").read_text()
    text = replace(
        text,
        "static void own_player(const uint64_t *r) {",
        f'#include "{out / header.name}"\nstatic void own_player(const uint64_t *r) {{',
    )
    text = replace(
        text,
        "    demo_native_update(player,slot,health);",
        "    demo_native_update(player,slot,health);\n    demo_live_update(player,slot,health);",
    )
    (out / "hle_rl.c").write_text(text)
    command = list(rec["command"])
    command[command.index("-o") + 1] = str(out / "dmhost-demo")
    command = [
        str(out / "hle_rl.c") if v == str(parent / "hle_rl.c") else v for v in command
    ]
    sources = (
        set(build_inputs(command))
        | {ROOT / p for p in rec["source_sha256"]}
        | {header, out / header.name, Path(__file__).resolve()}
    )
    frozen = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    with (out / "build.log").open("w") as f:
        subprocess.run(
            command,
            cwd=ROOT / "upstream/dm/host",
            stdout=f,
            stderr=subprocess.STDOUT,
            check=True,
        )
    shutil.copytree(parent / "modules", out / "modules")
    host = out / "dmhost-demo"
    rec.update(
        output=str(host.relative_to(ROOT)),
        output_sha256=sha(host),
        command=command,
        source_sha256=frozen,
        native_capture_live=True,
    )
    host.with_suffix(".build.json").write_text(json.dumps(rec, indent=2) + "\n")
    protected = json.loads((parent / "protected.json").read_text()) | {
        str(old.relative_to(ROOT)): sha(old)
    }
    assert all(sha(ROOT / p) == h for p, h in protected.items())
    (out / "protected.json").write_text(json.dumps(protected, indent=2) + "\n")
    print(host)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    build(p.parse_args().out)
