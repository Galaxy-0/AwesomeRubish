"""Build an isolated full-render demonstration host without changing any old host.

Reuse the qualified stage0 camera gate rewrite, never its direct-aim write mode.
Only volatile +5/gyro control options may be written; saves are cloned by Session.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from tools.build_a7_host import build_inputs

ROOT = Path(__file__).resolve().parents[2]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build(out, peer_elision=False):
    out = Path(out).resolve()
    parent = ROOT / "work/rl-stage0/camera-host-r9/dmhost-aim"
    rec = json.loads(parent.with_suffix(".build.json").read_text())
    if not out.is_relative_to(ROOT / "work") or out.exists():
        raise ValueError("fresh private work directory required")
    for p, h in rec["source_sha256"].items():
        if sha(ROOT / p) != h:
            raise ValueError("parent input identity changed: " + p)
    protected = {
        p: sha(p)
        for p in [
            parent,
            ROOT / "upstream/dm/host/dmhost",
            ROOT / "work/a8/dmhost-arena-v15",
            ROOT / "work/a8/dmhost-arena-special-v15",
        ]
    }
    out.mkdir(parents=True)

    def change(text, old, new):
        if text.count(old) != 1:
            raise ValueError("source shape changed: " + old[:100])
        return text.replace(old, new, 1)

    aim = (parent.parent / "test_aim.h").read_text()
    aim = change(
        aim,
        'const char *flag=getenv("DM_TEST_AIM");d3r_file=getenv("DM_TEST_AIM_FILE");',
        'const char *flag=getenv("DM_TEST_DEMO");d3r_file=NULL;\n if(getenv("DM_TEST_AIM")||getenv("DM_TEST_AIM_FILE"))die("demo forbids direct aim");\n if(flag&&strcmp(flag,"1"))die("DM_TEST_DEMO must be 1");',
    )
    aim = change(aim, "||!d3r_file||d3r_file[0]!='/'", "")
    aim = change(
        aim,
        "static void d3r_poll(uint64_t frame){",
        "static void d3r_poll(uint64_t frame){\n if(!d3r_file)return;",
    )
    aim = aim.replace(
        "DM_TEST_AIM requires explicit isolated",
        "DM_TEST_DEMO requires explicit isolated",
    )
    aim = aim.replace('LOG("D3R_TEST_AIM enabled=1', 'LOG("DEMO_SENSOR enabled=1')
    # Stage0 camera/option helper is appended in this header. Suppress exploratory heap dumps.
    aim = aim.replace("r0_camera_state();", "")
    (out / "test_aim.h").write_text(aim)
    sensor = (parent.parent / "sensor.h").read_text()
    sensor = sensor.replace("frame<last[i]+4", "frame<last[i]+1")
    # Keep only bounded scalar weapon telemetry, not exploratory heap hex dumps.
    start = sensor.index("static void d2b_damage(")
    end = sensor.index("static void d2b_init(", start)
    sensor = (
        sensor[:start]
        + "static void d2b_damage(uintptr_t p,int slot){(void)p;(void)slot;}\n"
        + sensor[end:]
    )
    sensor = sensor.replace(
        'd2b_hex("weapon",object,-1,0x5c0);',
        'uint32_t phase=0;d2b_read(object+0x40,&phase,4);LOG("DEMO_WEAPON frame=%llu object=%p phase40_candidate=%u readonly=1",frame,(void*)object,phase);',
    )
    (out / "sensor.h").write_text(sensor)
    (out / "bullet_sensor.h").write_text(
        (parent.parent / "bullet_sensor.h").read_text()
    )
    text = (parent.parent / "hle_rl.c").read_text()
    for name in ["test_aim.h", "sensor.h", "bullet_sensor.h"]:
        text = text.replace(str(parent.parent / name), str(out / name))
    text = text.replace("r0_camera_state();", "")
    # Own, immutable frame labels for latency accounting; does not change injection.
    text = change(
        text,
        "rl_latched=rl_pending;",
        'rl_latched=rl_pending;\n if(getenv("DM_TEST_DEMO"))LOG("DEMO_INPUT frame=%llu request=%llu buttons=%llx",frame,rl_request,rl_latched.buttons);',
    )
    text = change(text, "fabsf(gyro[i]) > 1", "fabsf(gyro[i]) > 8")
    (out / "hle_rl.c").write_text(text)
    (out / "hle.c").write_text((parent.parent / "hle.c").read_text())
    gfx = ROOT / "upstream/dm/gfx/nvn/nvn_mtl.m"
    mtl = gfx.read_text()
    mtl = change(
        mtl,
        "CFTimeInterval tt = d.presentedTime;",
        'CFTimeInterval tt = d.presentedTime;\n if(getenv("DM_TEST_DEMO"))MLOG("DEMO_DISPLAY frame=%llu ticket=%llu presented_ns=%.0f callback_ns=%.0f",frame,pn,tt*1e9,CACurrentMediaTime()*1e9);',
    )
    (out / "nvn_mtl.m").write_text(mtl)
    command = [x for x in rec["command"] if x != "-DSPL3_A8_CAMERA=1"]
    if peer_elision:
        command.insert(1, "-DSPL3_A8_CAMERA=1")
    command[command.index("-o") + 1] = str(out / "dmhost-demo")
    for i, v in enumerate(command):
        for name in ["hle_rl.c", "hle.c"]:
            if v == str(parent.parent / name):
                command[i] = str(out / name)
        if v == "../gfx/nvn/nvn_mtl.m" or v == str(gfx):
            command[i] = str(out / "nvn_mtl.m")
    # Moving an Objective-C source out of gfx/nvn requires its original quote include directory.
    command.insert(1, "-I" + str(gfx.parent))
    sources = set(build_inputs(command)) | {
        Path(__file__).resolve(),
        out / "test_aim.h",
        out / "sensor.h",
        out / "bullet_sensor.h",
    }
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
    import shutil

    shutil.copytree(parent.parent / "modules", out / "modules")
    record = rec | dict(
        output=str(host.relative_to(ROOT)),
        output_sha256=sha(host),
        command=command,
        source_sha256=frozen,
        render_mode="none",
        peer_camera_elision=peer_elision,
        human_full_render=True,
        test_only=True,
        test_feature="demonstration_capture",
        direct_aim=False,
        default_unchanged=True,
        private_module_sha256={
            p.name: sha(p) for p in (out / "modules").iterdir() if p.is_file()
        },
    )
    host.with_suffix(".build.json").write_text(json.dumps(record, indent=2) + "\n")
    for p, h in protected.items():
        if sha(p) != h:
            raise AssertionError("protected host changed: " + str(p))
    (out / "protected.json").write_text(
        json.dumps(
            {str(p.relative_to(ROOT)): h for p, h in protected.items()}, indent=2
        )
        + "\n"
    )
    print(host)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    p.add_argument(
        "--peer-elision",
        action="store_true",
        help="A8 only applies to headless peer; visible human still full render",
    )
    args = p.parse_args()
    build(args.out, args.peer_elision)
