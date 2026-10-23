"""Fresh private demo host: passive present/submit attribution, no pacing overrides."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from rl.native_start import validate_runtime
from rl.demo.build_host import ROOT, sha
from tools.build_a7_host import build_inputs


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError("source shape changed: " + old[:100])
    return text.replace(old, new, 1)


def build(out):
    out = Path(out).resolve()
    if not out.is_relative_to(ROOT / "work") or out.exists():
        raise ValueError("fresh private work directory required")
    parent = ROOT / "work/rl-demo/host-r5/dmhost-demo"
    validate_runtime(parent, parent.parent / "modules", allow_demo=True)
    record = json.loads(parent.with_suffix(".build.json").read_text())
    protected = json.loads((parent.parent / "protected.json").read_text())
    protected[str(parent.relative_to(ROOT))] = sha(parent)
    out.mkdir(parents=True)
    gfx = ROOT / "upstream/dm/gfx/nvn"
    text = (gfx / "hle_nvn.c").read_text()
    text = replace(
        text,
        "static _Atomic uint64_t g_sub_wall_ns, g_sub_cpu_ns, g_sub_instr;",
        "static _Atomic uint64_t g_demo_sub[4];\n"
        "static _Atomic uint64_t g_sub_wall_ns, g_sub_cpu_ns, g_sub_instr;",
    )
    text = replace(text, "    mtl_sub_begin();\n    mtl_sub_index", "    mtl_sub_begin();\n    uint64_t d1=now_ns();\n    mtl_sub_index")
    text = replace(text, "    for (int i = 0; i < n; i++) { mtl_exec_rest", "    uint64_t d2=now_ns();\n    for (int i = 0; i < n; i++) { mtl_exec_rest")
    text = replace(text, "    mtl_sub_commit();\n    uint64_t dw", "    uint64_t d3=now_ns();\n    mtl_sub_commit();\n    uint64_t d4=now_ns();\n    atomic_fetch_add(g_demo_sub,d1-t0);atomic_fetch_add(g_demo_sub+1,d2-d1);atomic_fetch_add(g_demo_sub+2,d3-d2);atomic_fetch_add(g_demo_sub+3,d4-d3);\n    uint64_t dw")
    text = replace(text, '    int itv = g_display_mode ? 1 :', '''    static uint64_t demo_frame=UINT64_MAX;
    if(getenv("DM_TEST_DEMO") && demo_frame!=g_frame){
        demo_frame=g_frame;
        LOG("DEMO_PACING frame=%llu mono_ns=%llu raw_interval=%d latched_interval=%d game_fps=%d target_fps=%d display_mode=%d hz=%d",g_frame,now_ns(),o->interval,atomic_load(&g_game_itv),nvn_game_fps(),mtl_fps_target(),g_display_mode,g_hz);
    }
    int itv = g_display_mode ? 1 :''')
    needle = 'trow(f, "@sub_instr", (double)atomic_exchange(&g_sub_instr, 0));'
    text = replace(text, needle, needle + '''
        static const char *dk[4]={"@demo_sub_begin_ms","@demo_sub_index_ms","@demo_sub_replay_ms","@demo_sub_commit_ms"};
        for(int j=0;j<4;j++)trow(f,dk[j],atomic_exchange(g_demo_sub+j,0)/1e6);''')
    text = replace(text, "        plib = lib_; ppso = pso_;", '        trow(f,"@demo_shader_make_ms",g_lf[f % LFN].make_ms);\n        plib = lib_; ppso = pso_;')
    (out / "hle_nvn.c").write_text(text)
    metal = (parent.parent / "nvn_mtl.m").read_text()
    metal = replace(metal, "void mtl_exec(const uint8_t *p) {", '''static uint64_t demo_op_frame=UINT64_MAX,demo_op_ns[OP_COUNT_],demo_op_cpu[OP_COUNT_],demo_op_n[OP_COUNT_];
static int demo_op_begin(void){
    uint64_t f=atomic_load(&g_cur_frame);
    if(f!=demo_op_frame){
        for(unsigned j=0;j<OP_COUNT_;j++)if(demo_op_n[j])MLOG("DEMO_OP frame=%llu op=%u calls=%llu wall_ns=%llu cpu_ns=%llu",demo_op_frame,j,demo_op_n[j],demo_op_ns[j],demo_op_cpu[j]);
        memset(demo_op_ns,0,sizeof demo_op_ns);memset(demo_op_cpu,0,sizeof demo_op_cpu);memset(demo_op_n,0,sizeof demo_op_n);demo_op_frame=f;
    }
    return f%300<12;
}
void mtl_exec(const uint8_t *p) {''')
    metal = replace(metal, "\n        const void *a = p + 8;\n", '''
        int demo_measure=demo_op_begin() && h.op!=OP_CALL && h.op!=OP_END && h.op!=OP_JUMP;
        uint64_t demo_t=demo_measure?clock_gettime_nsec_np(CLOCK_UPTIME_RAW):0,demo_c=demo_measure?clock_gettime_nsec_np(CLOCK_THREAD_CPUTIME_ID):0;
        const void *a = p + 8;
''')
    metal = replace(metal, "        p += h.size;\n    }\n}\n\n// ---------- Present:", '''        if(demo_measure){demo_op_ns[h.op]+=clock_gettime_nsec_np(CLOCK_UPTIME_RAW)-demo_t;demo_op_cpu[h.op]+=clock_gettime_nsec_np(CLOCK_THREAD_CPUTIME_ID)-demo_c;demo_op_n[h.op]++;}
        p += h.size;
    }
}

// ---------- Present:''')
    (out / "nvn_mtl.m").write_text(metal)
    command = list(record["command"])
    command[command.index("-o") + 1] = str(out / "dmhost-demo")
    command[command.index("../gfx/nvn/hle_nvn.c")] = str(out / "hle_nvn.c")
    command[command.index(str(parent.parent / "nvn_mtl.m"))] = str(out / "nvn_mtl.m")
    sources = set(build_inputs(command)) | {Path(__file__).resolve()}
    frozen = {str(p.relative_to(ROOT)): sha(p) for p in sorted(sources)}
    with (out / "build.log").open("w") as log:
        subprocess.run(command, cwd=ROOT / "upstream/dm/host", stdout=log, stderr=subprocess.STDOUT, check=True)
    host = out / "dmhost-demo"
    shutil.copytree(parent.parent / "modules", out / "modules")
    record.update(output=str(host.relative_to(ROOT)), output_sha256=sha(host), command=command, source_sha256=frozen, passive_present_profile=True)
    host.with_suffix(".build.json").write_text(json.dumps(record, indent=2) + "\n")
    assert all(sha(ROOT / p) == h for p, h in protected.items())
    (out / "protected.json").write_text(json.dumps(protected, indent=2) + "\n")
    print(host)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    build(p.parse_args().out)
