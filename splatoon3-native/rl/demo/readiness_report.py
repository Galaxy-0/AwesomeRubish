"""Aggregate numeric-only run70 evidence. No images, poses, grids or samples ship."""

import argparse
import json
from pathlib import Path
import numpy as np
from .build_host import ROOT, sha
from .capture import write


def generate(root, out):
    root = Path(root)
    load = lambda p: json.loads(Path(p).read_text())
    performance = {}
    for name in (
        "perf-final-baseline-r3",
        "perf-final-ink30-r3",
        "periodic-full-r1",
        "periodic-full-baseline-r1",
    ):
        r = load(root / name / "result.json")
        d = load(root / name / "latency.json")
        performance[name] = dict(
            frames=r["frames"],
            complete=r["complete"],
            errors=r["errors"],
            controlled_wall_seconds=r["controlled_wall_seconds"],
            warm_logic=d["warm_logic_frame_rates"],
            warm_native=d["warm_native_present_call_rates"],
            warm_display=d["warm_display_frame_rates"],
            display_coverage=d["warm_display_coverage"],
            software_input_to_presented_ms=d["warm_software_input_to_presented_ms"],
            source_sha256={
                n: sha(root / name / n)
                for n in ("result.json", "latency.json", "inputs-per-present.jsonl")
            },
        )
    full = load(root / "periodic-full-r1/result.json")
    cadence = load(root / "periodic-full-r1/periodic-ink.json")
    resources = load(Path(full["session"]) / "resources-summary.json")
    bc = load(root / "bc-periodic-full-r1/report.json")
    coverage = dict(
        samples=0, minimap_frames=0, ink_ray_frames=0, minimap_cells=0, ray_cells=0
    )
    for file in (root / "bc-periodic-full-r1").glob("bc-*.npz"):
        with np.load(file) as z:
            n = len(z["frame"])
            coverage["samples"] += n
            coverage["minimap_frames"] += int(
                z["minimap_valid"].reshape(n, -1).any(-1).sum()
            )
            coverage["ink_ray_frames"] += int(
                z["screen_channel_valid"][..., 2].reshape(n, -1).any(-1).sum()
            )
            coverage["minimap_cells"] += int(z["minimap_valid"].sum())
            coverage["ray_cells"] += int(z["screen_channel_valid"][..., 2].sum())
    dynamics = {}
    paths = dict(
        original_before=ROOT
        / "work/rl-demo/data-ready/dynamics-original-r11-final/report.json",
        original_ground_only=root / "dynamics-ground-r1/report.json",
        original_after=root / "dynamics-final-r11/report.json",
        heldout_before=root / "dynamics-heldout-baseline-r1/report.json",
        heldout_after=root / "dynamics-final-heldout/report.json",
    )
    for name, path in paths.items():
        d = load(path)
        dynamics[name] = dict(
            source=d["source"],
            first_ground_frame=d["first_ground_frame"],
            last_frame=d["last_frame"],
            variants=d["variants"],
            report_sha256=sha(path),
            source_report=str(path),
        )
    camera = load(root / "camera-nonlinear-r2.json")
    host = ROOT / "work/rl-demo/ink-recording-host-r1/dmhost-demo"
    gpu_dir = root / "gpu-final-r4"
    result = dict(
        schema="inklab.rl.demo.readiness-progress.v1",
        date="2026-10-24",
        training_started=False,
        ready_for_training=False,
        native_rooms_max=1,
        scope="Periodic native ink and bounded physics fixes; physical controller test deferred to user; no training/T1/S1",
        host=dict(
            path=str(host.relative_to(ROOT)),
            sha256=sha(host),
            default_arena_host_changed=False,
            direct_aim=False,
            periodic_default_command_frames=30,
        ),
        performance=performance,
        performance_limits=[
            "Warm excludes first600frames; no long frames removed afterwards",
            "1percent low is reciprocal of mean slowest1percent intervals",
            "Display uses only adjacent positive callbacks; missing callbacks listed",
            "Latency is software send-to-presentedTime, excludes USB and photon response",
            "Full live-opponent run has display jitter; no full-lock60 claim",
        ],
        cadence=cadence,
        resources={
            k: resources[k]
            for k in (
                "max_footprint_sum_mib",
                "swap_growth_mib",
                "max_new_swapout_bytes",
                "max_pressure",
            )
        },
        bc=dict(
            **coverage,
            sample_offset=bc["sample_offset"],
            camera_codebook=bc["camera_codebook"],
            physics_steps=bc["physics_steps_for_bc"],
            blocked_gates=bc["blocked_gates"],
            source_sha256=sha(root / "bc-periodic-full-r1/report.json"),
        ),
        dynamics=dynamics,
        dynamics_limits=[
            "Position and HP initialized once, never corrected later",
            "Camera-conditioned variants are attribution, not autonomous free replay",
            "17-way move and9-way camera remain lossy",
            "Side collision, dynamic terrain, paint/weapon motion, gyro cross-axis/transients remain approximate",
            "Launcher mechanism port is opt-in; this drift audit begins grounded, not a new native launch qualification",
        ],
        camera=dict(
            kind=camera["kind"],
            stick_yaw_exponent=camera["stick_yaw_exponent"],
            full_stick_rad_frame=camera["stick_full_yaw_rate"],
            groups=camera["groups"],
            validation=camera["validation"],
            source_sha256=sha(root / "camera-nonlinear-r2.json"),
        ),
        gpu=dict(
            benchmark=load(gpu_dir / "benchmark-result.json"),
            random=load(gpu_dir / "random-result.json"),
            archive_sha256=sha(root / "gpu-verify-r4.tar.gz"),
        ),
        tests=dict(
            local_run=85,
            local_passed=84,
            local_cuda_skipped=1,
            t1_components_passed=11,
            local_log_sha256=sha(root / "all-tests-final.log"),
            t1_log_sha256=sha(root / "t1-components-final.log"),
            cuda_ground_log_sha256=sha(gpu_dir / "ground-cuda-tests.log"),
        ),
        protected_sha256=load(root / "protected-final.json"),
        source_sha256={
            str(p.resolve().relative_to(ROOT)): sha(p)
            for p in [
                *Path("rl/demo").glob("*.py"),
                *Path("rl/demo").glob("*.inc"),
                *Path("rl/gpu").rglob("*.py"),
            ]
        },
    )
    write(Path(out), result)
    print(out, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default="work/rl-demo/run70")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    generate(a.root, a.out)
