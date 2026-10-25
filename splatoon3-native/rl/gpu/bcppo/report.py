"""Sanitized numeric startup evidence from a private snapshot; no PT/map/trace."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def build(root):
    root = Path(root)

    def read(name):
        return json.loads((root / name).read_text())

    config = read("config.json")
    status = read("status.json")
    with (root / "metrics.csv").open() as f:
        rows = [
            r
            for r in csv.DictReader(f)
            if None not in r and all(v is not None for v in r.values())
        ]
    ignored = {"phase"}
    fields = (
        [k for k in rows[0] if k not in ignored and rows[0][k] not in ("True", "False")]
        if rows
        else []
    )
    summaries = {}
    for field in fields:
        values = [float(r[field]) for r in rows]
        summaries[field] = dict(
            first=values[0],
            last=values[-1],
            minimum=min(values),
            maximum=max(values),
            mean=sum(values) / len(values),
            last20_mean=sum(values[-20:]) / len(values[-20:]),
        )
    matches = (
        [json.loads(x) for x in (root / "matches.jsonl").read_text().splitlines()]
        if (root / "matches.jsonl").exists()
        else []
    )
    evaluations = []
    for line in (root / "evaluations.jsonl").read_text().splitlines():
        r = json.loads(line)
        evaluations.append({k: v for k, v in r.items() if k != "per_game"})
    source_match = {}
    for name, sha in config["source_sha256"].items():
        path = Path("rl/gpu") / name
        if path.is_file():
            source_match[name] = hashlib.sha256(path.read_bytes()).hexdigest() == sha
    return dict(
        schema="inklab.bcppo.startup-report.v1",
        scope="running startup snapshot, not completed training or native acceptance",
        config=config,
        status=status,
        critic_preheat=read("critic-preheat.json"),
        update_count=len(rows),
        metrics=summaries,
        all_metrics_finite=all(
            math.isfinite(float(r[k])) for r in rows for k in fields
        ),
        ppo_update_span_minutes=(
            float(rows[-1]["wall_seconds"]) - float(rows[0]["wall_seconds"])
        )
        / 60
        if rows
        else 0,
        training_batches=dict(
            count=len(matches),
            weapon_kills=sum(r["weapon_kills"] for r in matches),
            damage=sum(r["damage"] for r in matches),
            mean_weapon_kills_per_game=sum(r["weapon_kills"] for r in matches)
            / max(1, len(matches) * config["n_envs"]),
            mean_damage_per_game=sum(r["damage"] for r in matches)
            / max(1, len(matches) * config["n_envs"]),
            includes_curriculum=True,
        ),
        normal_spawn_evaluations=evaluations,
        gpu_gate_passed=any(
            r["passed"] for r in evaluations if r["opponent"] == "script"
        ),
        native_precheck_started=False,
        source_at_launch_matches_local=source_match,
        checkpoint_note="private actor/resume files; best can remain baseline until formal KO/damage improves",
        t1_s1_resumed=False,
        vpt_touched=False,
        new_human_recordings=False,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    Path(a.out).write_text(json.dumps(build(a.root), indent=2) + "\n")
