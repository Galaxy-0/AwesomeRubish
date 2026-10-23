"""Aggregate numbers/hashes only. Never copies native images, grids or traces."""

import argparse, json, subprocess
from pathlib import Path
import numpy as np
from rl.demo.build_host import ROOT, sha
from rl.native_start import validate_runtime
from rl.demo.capture import write
from rl.demo.state_sync import read_jsonl


def report(out):
    root = ROOT / "work/rl-demo/data-ready"
    result = dict(
        schema="inklab.rl.demo.data-ready.v1",
        date="2026-10-24",
        training_started=False,
        ready_for_training=False,
        cases={},
        dynamics={},
        source_sha256={},
    )
    for n in [1, 2, 3]:
        source = root / f"native-survey-full-r{n}"
        bc = root / f"bc-native-sync-final-r{n}"
        r = json.loads((source / "result.json").read_text())
        b = json.loads((bc / "report.json").read_text())
        native = json.loads((source / "native-survey.json").read_text())
        session = Path(r["session"])
        resources = read_jsonl(session / "resources.jsonl")
        case = dict(
            source=str(source.relative_to(ROOT)),
            bc=str(bc.relative_to(ROOT)),
            session=str(session.relative_to(ROOT)),
            recording={
                k: r.get(k)
                for k in [
                    "complete",
                    "passed",
                    "frames",
                    "source",
                    "script_pattern",
                    "errors",
                    "host_sha256",
                    "weapons",
                    "loadout_mode",
                    "controlled_wall_seconds",
                    "score_by_role",
                    "hud_downs",
                ]
            },
            bc_report=b,
            native_survey=native,
            resources=dict(
                peak_footprint_mib=max(x["footprint_sum_mib"] for x in resources),
                new_swapout_bytes=max(x["new_swapout_bytes"] for x in resources),
                max_pressure=max(x["pressure"] for x in resources),
            ),
            sha256={},
        )
        for p in [
            source / "result.json",
            source / "inputs-per-present.jsonl",
            source / "native-barriers.jsonl",
            source / "native-state.jsonl",
            source / "native-weapon.jsonl",
            source / "native-survey.json",
            bc / "report.json",
            *sorted(bc.glob("bc-*.npz")),
        ]:
            case["sha256"][str(p.relative_to(ROOT))] = sha(p)
        bindings = {k: sha(source / k) == v for k, v in b["source_sha256"].items()}
        assert all(bindings.values()), bindings
        case["source_bindings_current"] = bindings
        audit = dict(
            samples=0,
            finite=True,
            actions_legal=True,
            unknown_paint_masked=True,
            unknown_projectiles_masked=True,
            source_age_max=0,
            visible_entity_frames=0,
            frame_order=True,
        )
        previous_frame = -1
        for p in sorted(bc.glob("bc-*.npz")):
            with np.load(p, allow_pickle=False) as z:
                count = len(z["frame"])
                audit["frame_order"] &= bool(
                    np.all(np.diff(z["frame"]) > 0)
                    and int(z["frame"][0]) > previous_frame
                    and int(z["frame"][-1]) < b["last_frame_exclusive"]
                )
                previous_frame = int(z["frame"][-1])
                audit["samples"] += count
                for name in ["screen", "entities", "hud"]:
                    audit["finite"] &= bool(np.isfinite(z[name]).all())
                ix = np.arange(count)[:, None]
                heads = np.arange(8)[None, :]
                audit["actions_legal"] &= bool(
                    z["action_mask"][ix, heads, z["actions"]].all()
                )
                audit["unknown_paint_masked"] &= bool(
                    not z["minimap_valid"].any()
                    and not z["screen_channel_valid"][..., 2].any()
                )
                audit["unknown_projectiles_masked"] &= bool(
                    not z["projectiles_native_valid"].any()
                )
                audit["source_age_max"] = max(
                    audit["source_age_max"], int(z["source_age_frames"].max())
                )
                audit["visible_entity_frames"] += int(z["entity_mask"].any(-1).sum())
        assert (
            audit["samples"] == b["samples"]
            and audit["finite"]
            and audit["frame_order"]
            and audit["actions_legal"]
            and audit["unknown_paint_masked"]
            and audit["unknown_projectiles_masked"]
        )
        case["shard_audit"] = audit
        qa = root / f"qa-native-sync-final-r{n}/report.json"
        case["visual_qa"] = json.loads(qa.read_text())
        result["cases"][str(n)] = case
    for name in ["dynamics-r1", "dynamics-common-r1", "dynamics-original-r11-final"]:
        p = root / name / "report.json"
        result["dynamics"][name] = json.loads(p.read_text())
    result["camera_heldout"] = json.loads((root / "camera-heldout-r3.json").read_text())
    result["total_bc_samples"] = sum(
        c["bc_report"]["samples"] for c in result["cases"].values()
    )
    protected = json.loads(
        (ROOT / "work/rl-demo/data-host-r3/protected.json").read_text()
    )
    result["protected"] = {
        p: dict(expected=h, actual=sha(ROOT / p), unchanged=sha(ROOT / p) == h)
        for p, h in protected.items()
    }
    assert all(x["unchanged"] for x in result["protected"].values())
    result["saves"] = {
        str(p): sha(p)
        for p in [
            ROOT / "work/save_ref/save.dat",
            ROOT.parent
            / "splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat",
        ]
    }
    assert len(set(result["saves"].values())) == 1
    old_saves = json.loads((ROOT / "notes/rl-demo-realtime-20261024.json").read_text())[
        "saves"
    ]
    assert all(sha(ROOT / p) == h for p, h in old_saves.items())
    result["saves_match_run67"] = True
    result["manifest_checks"] = []
    for name in ["host-r5", "render-host-r2", "data-host-r2", "data-host-r3"]:
        p = ROOT / f"work/rl-demo/{name}/dmhost-demo"
        validate_runtime(p, p.parent / "modules", allow_demo=True)
        result["manifest_checks"].append(name)
    original = json.loads(
        (ROOT / "work/rl-demo/visual-overlay-r2/manifest.json").read_text()
    )["files"]
    result["original_romfs"] = {}
    for p, info in original.items():
        src = ROOT / "work/data/v720896/RomFS" / p
        assert sha(src) == info["source_sha256"]
        result["original_romfs"][p] = dict(sha256=sha(src), unchanged=True)
    for p in [
        *sorted((ROOT / "rl/demo").glob("*.py")),
        *sorted((ROOT / "rl/demo").glob("*.inc")),
        ROOT / "rl/gpu/env.py",
    ]:
        result["source_sha256"][str(p.relative_to(ROOT))] = sha(p)
    owned = []
    for line in subprocess.check_output(
        ["ps", "-axo", "pid,ppid,command"], text=True
    ).splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        cmd = parts[2]
        exe = cmd.split()[0]
        if exe.endswith("/dmhost-demo") or (
            exe.endswith("/python") and " -m rl.demo.capture " in cmd
        ):
            owned.append(parts)
    assert not owned, owned
    result["closeout"] = dict(
        owned_native_capture_processes=owned,
        max_rooms=1,
        training_started=False,
        production_defaults_unchanged=True,
        notes="Full-state sensor semantics not promoted just because readable; all BC files remain masked approximate research artifacts.",
    )
    write(out, result)
    print(
        json.dumps(
            dict(
                total_samples=result["total_bc_samples"],
                ready_for_training=False,
                cases=3,
                protected=True,
                owned_processes=owned,
            ),
            indent=2,
        )
    )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    report(p.parse_args().out)
