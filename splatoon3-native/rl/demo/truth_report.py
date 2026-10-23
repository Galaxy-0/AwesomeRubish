"""Scalar/hash acceptance record only: no images, mesh, UV tables or samples."""

import argparse
import collections
import json
from pathlib import Path
import numpy as np
from .build_host import ROOT, sha
from .capture import write


def report(out):
    cases = {
        "firefight_r1": "work/a6/d3-truth-r1-20261024-031423-824512",
        "aux_lifecycle_r2": "work/a6/d3-truth-r2c-20261024-033016-640668",
        "firefight_r3": "work/a6/d3-truth-r3-20261024-033500-389230",
        "downward_ink_r4": "work/a6/d3-truth-ink-r4-20261024-034156-335379",
        "panels": "work/a6/d3-truth-panels-r1-20261024-041320-797974",
        "panel_uv": "work/a6/d3-truth-panel-uv-r1-20261024-042051-467143",
    }
    data = dict(
        schema="inklab.rl.demo.truth-report.v1",
        date="2026-10-24",
        training_started=False,
        ready_for_training=False,
        rooms_concurrent_max=1,
        cases={},
        bc={},
        protection={},
        passed_scope=[
            "controlled visible firefight/35/70/52/KO/squid",
            "owned primary Saber stage/charge/recovery",
            "native primary bullet reset/tick/release/owner, observer0",
            "native UV transform/V flip/finite two-height controls; partial upward-floor overlays",
        ],
        pending=[
            "continuous dense world paint and full surface membership/walls/ambiguous panels",
            "general all-weapon/all-observer projectile completeness; native post-calc pose and exact per-hit damage",
            ".52 full firing/recovery stage (Saber owned HUD only qualified)",
            "normal non-aim human demonstrations; native spectator camera after KO; accepted coarse geometry/FOV biases remain",
        ],
    )
    for name, path in cases.items():
        source = ROOT / path
        r = json.loads((source / "result.json").read_text())
        item = {
            k: r.get(k)
            for k in [
                "passed",
                "errors",
                "frames",
                "session",
                "host_sha256",
                "controlled_clip_complete",
                "controlled_ink_complete",
                "controlled_setup_complete",
            ]
        }
        item["source"] = path
        item["sha256"] = {
            p.name: sha(p)
            for p in [
                source / "result.json",
                source / "inputs-per-present.jsonl",
                source / "native-barriers.jsonl",
            ]
            if p.is_file()
        }
        if (source / "truth-report.json").exists():
            truth = json.loads((source / "truth-report.json").read_text())
            item["damage_edges"] = truth["damage_edges"]
            item["squid_frames"] = truth["squid_frames"]
            item["saber_stages"] = truth["saber_stages"]
        if (source / "projectile-truth.json").exists():
            p = json.loads((source / "projectile-truth.json").read_text())
            item["projectiles"] = {
                k: p.get(k)
                for k in [
                    "snapshots",
                    "positive_frames",
                    "qualified_frames",
                    "events",
                    "complete_general_projectile_sensor",
                ]
            }
            item["projectiles"]["closed_lifetimes"] = len(p["lifetimes"])
            item["projectiles"]["unclosed_lifetimes"] = len(p["unclosed_lifetimes"])
        resources = Path(r.get("session", "missing")) / "resources.jsonl"
        if resources.exists():
            rows = [json.loads(x) for x in resources.open()]
            item["resources"] = dict(
                peak_footprint_mib=max(x["footprint_sum_mib"] for x in rows),
                additional_swapout_bytes=max(x["new_swapout_bytes"] for x in rows),
                max_pressure=max(x["pressure"] for x in rows),
            )
        data["cases"][name] = item
    for name, path in [
        ("combat", "work/rl-demo/truth-bc-combat-qualified"),
        ("ink_controls", "work/rl-demo/truth-bc-ink-qualified"),
    ]:
        source = ROOT / cases["firefight_r3" if name == "combat" else "downward_ink_r4"]
        bc = ROOT / path
        r = json.loads((bc / "report.json").read_text())
        counts = collections.Counter()
        finite = True
        labels_masked = True
        for file in sorted(bc.glob("bc-*.npz")):
            with np.load(file) as z:
                counts["samples"] += len(z["frame"])
                counts["weapon_valid_samples"] += int(z["weapon_native_valid"].sum())
                counts["primary_projectile_valid_samples"] += int(
                    z["projectiles_native_valid"].sum()
                )
                counts["visible_enemy_samples"] += int(
                    ((z["entities"][..., 3] == 1) & z["entity_mask"]).any(-1).sum()
                )
                counts["visible_projectile_samples"] += int(
                    ((z["entities"][..., 3] > 1) & z["entity_mask"]).any(-1).sum()
                )
                counts["native_minimap_samples"] += int(
                    z["minimap_valid"].any((1, 2)).sum()
                )
                counts["native_minimap_valid_cells"] += int(z["minimap_valid"].sum())
                counts["native_ray_ink_samples"] += int(
                    z["screen_channel_valid"][..., 2].any((1, 2)).sum()
                )
                counts["native_ray_ink_valid_rays"] += int(
                    z["screen_channel_valid"][..., 2].sum()
                )
                counts["own_ink_cells"] += int(
                    ((z["minimap"] == 1) & z["minimap_valid"]).sum()
                )
                counts["enemy_ink_cells"] += int(
                    ((z["minimap"] == 2) & z["minimap_valid"]).sum()
                )
                labels_masked &= not bool(z["action_labels_trainable"].any())
                finite &= all(
                    np.isfinite(z[k]).all() for k in ["screen", "entities", "hud"]
                )
        bindings = {k: sha(source / k) == v for k, v in r["source_sha256"].items()}
        assert (
            all(bindings.values())
            and counts["samples"] == r["samples"]
            and finite
            and labels_masked
        )
        data["bc"][name] = dict(
            path=path,
            counts=dict(counts),
            finite=finite,
            ideal_aim_labels_masked=labels_masked,
            source_bindings_current=bindings,
            ready_for_training=r["ready_for_training"],
            blocked_gates=r["blocked_gates"],
            report_sha256=sha(bc / "report.json"),
            shard_sha256={p.name: sha(p) for p in sorted(bc.glob("bc-*.npz"))},
        )
    mapping = ROOT / "work/rl-demo/truth-ink-mapping-r1"
    validation = json.loads((mapping / "controls-validation.json").read_text())
    data["ink_projection"] = {
        k: validation[k]
        for k in [
            "passed",
            "samples",
            "role1_pure_g_pixels",
            "projection_fitted_to_controls",
            "scope",
            "panels_sha256",
        ]
    }
    # This public report includes only scalar validation, not the UV table.
    for p, h in json.loads(
        (ROOT / "work/rl-demo/truth-host-panel-uv-r1/protected.json").read_text()
    ).items():
        actual = sha(ROOT / p)
        assert actual == h, p
        data["protection"][p] = actual
    expected = "89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd"
    for p in [
        ROOT / "work/save_ref/save.dat",
        ROOT.parent / "splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat",
    ]:
        actual = sha(p)
        assert actual == expected
        data["protection"][str(p)] = actual
    for path, expected in {
        "work/data/v720896/RomFS/Pack/Scene/Vss_Yunohana.pack.zs": "782655acf53279b3ff4801c934884c000f8d41491658dadd01b200a5bac5bcf9",
        "work/data/v720896/RomFS/Pack/Bootup.Nin_NX_NVN.pack.zs": "5862c49fc7ebbb1b99c7e79a62f1ab24df44e732f3fc173f08a84d1d22e80929",
    }.items():
        actual = sha(ROOT / path)
        assert actual == expected
        data["protection"][path] = actual
    data["qa"] = "work/rl-demo/truth-qa-qualified/"
    data["source_sha256"] = {
        str(p.relative_to(ROOT)): sha(p)
        for p in [
            *sorted((ROOT / "rl/demo").glob("*.py")),
            *sorted((ROOT / "rl/demo").glob("*.inc")),
        ]
    }
    write(out, data)
    print(
        json.dumps(
            {k: data[k] for k in ["ready_for_training", "training_started", "bc"]},
            indent=2,
        )
    )
    return data


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    report(p.parse_args().out)
