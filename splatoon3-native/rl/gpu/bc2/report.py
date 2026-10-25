"""Local aggregate evidence only. No traces/grids/images/checkpoints in notes."""

import argparse
import json
import hashlib
import re
from pathlib import Path
import numpy as np
from .distribution import compare


def main(a):
    root = Path(a.root)

    def read(p):
        return json.loads(Path(p).read_text())

    result = dict(
        schema="inklab.bc2.summary.v1",
        recordings={},
        fits={},
        evaluations={},
        variants={},
        native={},
    )
    contract = read(root / "ink-contract-r2/contract.json")
    result["ink_contract"] = contract
    with np.load(root / "ink-contract-r2/contract.npz") as z:
        paintable_fraction = float(z["paintable_map"].mean())
    for p in sorted(root.glob("data-*/report.json")):
        r = read(p)
        r = {k: v for k, v in r.items() if k != "attack_events"}
        r["ink_available_among_paintable"] = (
            r["ink_map_available_fraction"] / paintable_fraction
        )
        r["prepared_sha256"] = hashlib.sha256(
            (p.parent / "prepared.npz").read_bytes()
        ).hexdigest()
        result["recordings"][p.parent.name] = r
    for p in root.glob("fit-*/result.json"):
        result["fits"][p.parent.name] = read(p)
    pattern = re.compile(
        r"eval-(feedback1|nofeedback1|chunk8|chunk16)-(\d+)-(random|script|history)-(greedy|sampled|expected)"
    )
    for p in sorted(root.glob("eval-*/result.json")):
        match = pattern.fullmatch(p.parent.name)
        if not match:
            continue
        scheme, seed, kind, mode = match.groups()
        r = read(p)
        row = {
            k: r[k]
            for k in [
                "games",
                "kind",
                "deterministic",
                "frames",
                "all_terminated",
                "kills",
                "deaths",
                "enemy_weapon_kills",
                "damage",
                "attacks",
                "attacks_per_minute",
                "hit_decisions",
                "turf_percent",
                "enemy_turf_percent",
                "seconds",
            ]
        }
        row.update(
            scheme=scheme,
            training_seed=int(seed),
            mode=mode,
            full_releases=r["combat"]["stamper"]["full_releases"],
        )
        result["evaluations"][p.parent.name] = row
    human = read(root / "training-bank.json")
    result["human_reference"] = human
    for scheme in ["feedback1", "nofeedback1", "chunk8", "chunk16"]:
        for mode in ["greedy", "expected", "sampled"]:
            rows = [
                r
                for r in result["evaluations"].values()
                if r["scheme"] == scheme and r["mode"] == mode
            ]
            if not rows:
                continue
            result["variants"][scheme + "-" + mode] = dict(
                groups=len(rows),
                games=sum(r["games"] for r in rows),
                kills=sum(r["kills"] for r in rows),
                damage=sum(r["damage"] for r in rows),
                turf_percent_mean=float(np.mean([r["turf_percent"] for r in rows])),
                attacks_per_minute_mean=float(
                    np.mean([r["attacks_per_minute"] for r in rows])
                ),
                human_attack_fraction=float(
                    np.mean([r["attacks_per_minute"] for r in rows])
                    / human["human_attacks_per_minute"]
                ),
            )
    gate_rows = {}
    for name, row in result["evaluations"].items():
        if row["kind"] != "script":
            continue
        gate = dict(
            attack_frequency=row["attacks_per_minute"]
            >= human["gate_attack_per_minute"],
            nonzero_weapon_ko=row["kills"] > 0,
            turf=row["turf_percent"] >= 8,
        )
        gate["passed"] = all(gate.values())
        gate_rows[name] = gate
    result["gates"] = dict(
        required=dict(
            attacks_per_minute=human["gate_attack_per_minute"],
            human_fraction=0.3,
            script_weapon_kills=">0",
            turf_percent=8,
        ),
        cases=gate_rows,
        any_pass=any(r["passed"] for r in gate_rows.values()),
        ppo_started=False,
    )
    from rl.demo.bc2_export import attack_events

    for p in sorted(root.glob("native-*/result.json")):
        r = read(p)
        events = attack_events(p.parent)
        row = {
            k: r.get(k)
            for k in [
                "passed",
                "complete",
                "frames",
                "errors",
                "turf_ratio_by_role",
                "bc_checkpoint_sha256",
                "controlled_presents_per_second",
                "session",
            ]
        }
        row.update(
            attack_birth_proxies=len(events),
            attacks_per_minute=len(events) / 3,
            full=sum(k == 3 for _, k in events),
            light=sum(k == 2 for _, k in events),
            hud=read(p.parent / "telemetry-summary.json")["hud_by_role"],
        )
        decisions = [
            json.loads(s)
            for s in (p.parent / "bc-decisions.jsonl").read_text().splitlines()
        ]
        row["ink_map_available_mean"] = float(
            np.mean([x["ink_map_available"] for x in decisions])
        )
        row["ink_age_mean"] = float(np.mean([x["ink_age"] for x in decisions]))
        row["camera_bins"] = {
            name: np.bincount(
                [x["actions"][h] for x in decisions], minlength=9
            ).tolist()
            for name, h in [("yaw", 1), ("pitch", 2)]
        }
        result["native"][p.parent.name] = row
    result["paired_same_input"] = read(root / "paired-report.json")
    probe = root / "probe-nofeedback1-80-script-r2"
    if probe.exists():
        with (
            np.load(root / "train-distributions.npz") as train,
            np.load(probe / "distributions.npz") as gpu,
        ):
            result["train_vs_gpu_distribution"] = compare(
                {k: train[k] for k in train.files}, {k: gpu[k] for k in gpu.files}
            )
            result["visible_enemy_probe"] = dict(
                train=float(len(train["entities"]) / len(train["hud"])),
                gpu=float(len(gpu["entities"]) / len(gpu["hud"])),
                scope="training samples vs one GPU observation probe each62f (all ink-age phases); not every-decision hit visibility",
            )
        original = read(root / "eval-nofeedback1-80-script-greedy/result.json")
        repeated = read(probe / "result.json")
        result["logger_replay_equal"] = {
            k: original[k] == repeated[k]
            for k in [
                "kills",
                "deaths",
                "damage",
                "attacks",
                "turf_percent",
                "per_game",
            ]
        }
    result["native_ink_reservation_audit"] = read(
        root / "native-ink-reservation-audit.json"
    )
    result["formal_gpu_games"] = sum(r["games"] for r in result["evaluations"].values())
    result["all_formal_gpu_terminated"] = all(
        r["all_terminated"] and r["frames"] == 10800
        for r in result["evaluations"].values()
    )
    result["protected_hosts_unchanged"] = read(root / "protected-check.json")
    sources = sorted(Path("rl/gpu/bc2").glob("*.py")) + [
        Path("rl/demo") / n
        for n in [
            "bc_ink.py",
            "bc2_export.py",
            "bc2_pair.py",
            "bc2_native.py",
            "bc_native.py",
            "capture.py",
            "test_bc2_sensor.py",
        ]
    ]
    result["source_sha256"] = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
    }
    result["checkpoint_sha256"] = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.glob("fit-*/*.pt")
    }
    Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    main(p.parse_args())
