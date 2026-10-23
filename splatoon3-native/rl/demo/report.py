"""Export numeric-only preparation results; never copy corpus, grids or videos."""

import argparse, hashlib, json
from pathlib import Path


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def report(root, out):
    root = Path(root)
    out = Path(out)
    load = lambda name: json.loads((root / name).read_text())
    native = load("smoke-final-r11/result.json")
    bc = load("bc-final-r11/report.json")
    latency = load("smoke-final-r11/latency.json")
    telemetry = load("smoke-final-r11/telemetry-summary.json")
    result = dict(
        schema="inklab.rl.demo.preparation.v1",
        training_started=False,
        ready_for_human_demonstration=False,
        ready_for_bc=False,
        status="capture/conversion chain verified; realtime60, physical controls and dense native observation gaps remain",
        controller=load("controller-final-r3/summary.json"),
        native_smoke={
            k: native[k]
            for k in [
                "passed",
                "complete",
                "source",
                "stage",
                "map",
                "loadout_mode",
                "weapons",
                "frames",
                "controlled_wall_seconds",
                "controlled_presents_per_second",
                "errors",
                "score_by_role",
                "turf_ratio_by_role",
                "host_sha256",
                "host",
            ]
        },
        native_corpus_audit=load("corpus-audit-final.json"),
        bc_audit=load("bc-audit-final.json"),
        native_telemetry=telemetry,
        tests=dict(
            demo_components=11,
            existing_t1_components=11,
            real_policy_workers=2,
            observation_schedule=load("observation-schedule-parity.json"),
        ),
        policy_workers=[
            {k: r[k] for k in ["policy", "source_sha256", "passed"]}
            for r in load("policy-wire.json")
        ],
        bc={
            k: bc[k]
            for k in [
                "samples",
                "first_ground_frame",
                "last_frame",
                "decision_stride",
                "button_semantics",
                "quantization_scope",
                "quantization",
                "open_loop_native_error",
                "source_state_age_frames",
                "final_native_turf_ratio",
                "free_rollout_turf_ratio",
                "turf_error_percentage_points",
                "limitations",
            ]
        },
        camera_fit=dict(
            samples=bc["camera_response"]["samples"],
            rank=bc["camera_response"]["rank"],
            input_dimensions=5,
            rmse_radians_per_frame=bc["camera_response"]["rmse_radians_per_frame"],
            scope=bc["camera_response"]["scope"],
        ),
        performance={},
        renderer_attempts=[
            dict(
                candidate="DM_3D_SCALE .25-.5",
                outcome="existing implementation only targets D2R build; not applicable to Splatoon, no verified scale change",
            ),
            dict(
                candidate="DM_GAME_RES800x450",
                outcome="native output still1280x720; requested640x360 not confirmed, attempt rejected; not a valid low-resolution performance result",
            ),
            dict(
                candidate="generic FXAA/bloom/shadow off",
                outcome="no qualified Splatoon-specific toggle found; generic shader keys do not match known Splatoon map; not implemented or claimed as disabled",
            ),
            dict(
                candidate="remove exploratory heap dumps/avoid growing-log rescans",
                outcome="implemented; bounded scalar sensors and original memory stop limits retained",
            ),
            dict(
                candidate="headless peer camera elision",
                outcome="measured; human camera stays fully rendered and protected query semantics retained",
            ),
            dict(
                candidate="script-only RPCchunk8",
                average_presents_per_second=load("perf-chunk-r6/result.json")[
                    "presents_per_second"
                ],
                outcome="no speed win; not offered as human control or BC recording",
            ),
            dict(
                candidate="immediate drawable presentation link0",
                outcome="lower software input-to-present latency, realtime60 still not attained",
            ),
        ],
        latency_scope=latency["scope"],
        full_native_paint=False,
        weapon_phase_complete=False,
        native_projectile_set_complete=False,
        physical_button_to_photon_latency_measured=False,
        limitations=[
            "Manual physical buttons/gyro sign validation pending.",
            "FOV55vertical assumption/coarse geometry remain.",
            "Native RNG unknown; simulated spread is not native replay equivalence.",
            "Free rollout drifts; native-anchored BC still has approximate paint/projectiles/action state.",
            "Performance runs include different navigation fixes/cache histories; not strict causal A/B speedup claims.",
        ],
        artifacts=dict(
            native="work/rl-demo/smoke-final-r11",
            bc="work/rl-demo/bc-final-r11",
            instructions="rl/demo/README.md",
        ),
        source_sha256={
            str(p): sha(p)
            for p in [
                root / "smoke-final-r11/result.json",
                root / "smoke-final-r11/latency.json",
                root / "bc-final-r11/report.json",
                root / "controller-final-r3/summary.json",
                root / "corpus-audit-final.json",
                root / "bc-audit-final.json",
            ]
        },
    )
    for name in ["perf-lean-r4", "perf-peer-r5", "smoke-link0-r7", "smoke-final-r11"]:
        d = load(name + "/latency.json")
        result["performance"][name] = {
            k: d[k]
            for k in [
                "warm_logic_frame_rates",
                "warm_display_frame_rates",
                "software_input_to_corresponding_drawable_presented_ms",
                "zero_presented_time_frames",
                "display_rate_scope",
                "warmup_exclusion_frames",
                "cpu_gpu_profile",
            ]
        }
    res_path = Path(native["session"]) / "resources-summary.json"
    if res_path.exists():
        d = json.loads(res_path.read_text())
        values = [v for v in d.get("gpu_util_percent", []) if v is not None]
        result["resource_scope"] = (
            "whole native session including boot/settlement, not GPU allocator memory"
        )
        result["resources"] = {
            k: d[k]
            for k in [
                "max_rss_sum_mib",
                "max_footprint_sum_mib",
                "max_new_swapout_bytes",
                "max_pressure",
            ]
        }
        result["resources"]["gpu_util_percent_mean"] = (
            sum(values) / len(values) if values else None
        )
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default="work/rl-demo")
    p.add_argument("--out", default="notes/rl-demo-20261023.json")
    a = p.parse_args()
    report(a.root, a.out)
