"""Fresh demo-only native survey, preserving accepted and production hosts."""

import argparse, json, shutil, subprocess
from pathlib import Path
from rl.demo.build_host import ROOT, sha
from rl.demo.build_profile import replace
from rl.native_start import validate_runtime
from tools.build_a7_host import build_inputs


def build(out):
    out = Path(out).resolve()
    parent = ROOT / "work/rl-demo/render-host-r2"
    host = parent / "dmhost-demo"
    if out.exists() or not out.is_relative_to(ROOT / "work/rl-demo"):
        raise ValueError("fresh private demo path required")
    validate_runtime(host, parent / "modules", allow_demo=True)
    rec = json.loads(host.with_suffix(".build.json").read_text())
    protected = json.loads((parent / "protected.json").read_text()) | {
        str(host.relative_to(ROOT)): sha(host)
    }
    out.mkdir(parents=True)
    header = Path(__file__).with_name("capture_sensors.inc")
    shutil.copyfile(header, out / header.name)
    for name in ["hle_rl.c", "test_aim.h", "sensor.h", "bullet_sensor.h"]:
        source = ROOT / "work/rl-demo/host-r5" / name
        (out / name).write_text(
            source.read_text().replace(str(source.parent), str(out))
        )
    text = (out / "hle_rl.c").read_text()
    text = replace(
        text,
        "static void own_player(const uint64_t *r) {",
        f'#include "{out / header.name}"\nstatic void own_player(const uint64_t *r) {{',
    )
    text = replace(
        text,
        "    d3_bullets(player);",
        "    demo_native_update(player,slot,health);\n    d3_bullets(player);",
    )
    (out / "hle_rl.c").write_text(text)
    # Forward declaration: existing live-velocity callback precedes the survey header.
    text = (out / "test_aim.h").read_text()
    text = "static void demo_native_projectile(uintptr_t,uintptr_t);\n" + text
    text = replace(
        text,
        " float v[3],pos[3];",
        " demo_native_projectile(p,off);\n float v[3],pos[3];",
    )
    (out / "test_aim.h").write_text(text)
    text = (parent / "nvn_mtl.m").read_text()
    text = replace(
        text,
        "    if (g_td_frame < 0 || g_td_done) return;",
        '    if(getenv("DM_DEMO_INK_DIR")){id<MTLTexture> t=nc?pd.colorAttachments[0].texture:nil;if(!t || t.width!=1600 || t.height!=1600)return;}\n    if (g_td_frame < 0 || g_td_done) return;',
    )
    text = replace(
        text,
        "void mtl_set_frame(uint64_t f) { demo_pred_frame(f);",
        "static void demo_ink_frame(uint64_t f);\nvoid mtl_set_frame(uint64_t f) { demo_pred_frame(f); demo_ink_frame(f);",
    )
    marker = "static long g_td_frame = -2; static const char *g_td_path; static NSMutableArray *g_td_list; static int g_td_done;"
    text = replace(
        text,
        marker,
        marker
        + "\n"
        + 'static void demo_ink_frame(uint64_t f){\n    static uint64_t ink_base=UINT64_MAX;static char ink_path[4096];const char *ink_dir=getenv("DM_DEMO_INK_DIR");\n    if(ink_dir && getenv("DM_TEST_DEMO") && dm_rl_active() && dm_rl_match_phase()==1){\n        if(ink_base==UINT64_MAX)ink_base=f;\n        if(f-ink_base==600 || f-ink_base==1200){\n            snprintf(ink_path,sizeof ink_path,"%s/frame-%llu-target-%%d.png",ink_dir,f-ink_base);\n            g_td_frame=(long)f;g_td_path=ink_path;g_td_done=0;g_td_list=[NSMutableArray array];\n        }\n    }\n}',
    )
    (out / "nvn_mtl.m").write_text(text)
    command = list(rec["command"])
    command[command.index("-o") + 1] = str(out / "dmhost-demo")
    command = [
        str(out / "nvn_mtl.m")
        if v == str(parent / "nvn_mtl.m")
        else str(out / "hle_rl.c")
        if v == str(ROOT / "work/rl-demo/host-r5/hle_rl.c")
        else v
        for v in command
    ]
    sources = (
        set(build_inputs(command))
        | {ROOT / p for p in rec["source_sha256"]}
        | {
            header,
            Path(__file__).resolve(),
            *(
                out / n
                for n in [
                    "test_aim.h",
                    "sensor.h",
                    "bullet_sensor.h",
                    "capture_sensors.inc",
                ]
            ),
        }
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
    new = out / "dmhost-demo"
    rec.update(
        output=str(new.relative_to(ROOT)),
        output_sha256=sha(new),
        command=command,
        source_sha256=frozen,
        native_capture_survey=True,
    )
    new.with_suffix(".build.json").write_text(json.dumps(rec, indent=2) + "\n")
    assert all(sha(ROOT / p) == h for p, h in protected.items())
    (out / "protected.json").write_text(json.dumps(protected, indent=2) + "\n")
    print(new)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    build(p.parse_args().out)
