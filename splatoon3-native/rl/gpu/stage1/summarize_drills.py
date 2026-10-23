"""Aggregate private skill trials without exporting maps, poses or checkpoints."""

import argparse, csv, hashlib, json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(a):
    root = Path(a.root)
    rows = []
    for p in sorted(root.glob("stage1-*/summary.json")):
        d = json.loads(p.read_text())
        if "training_seconds" not in d or "kind" not in d:
            continue
        cfg = json.loads((p.parent / "config.json").read_text())
        name = p.parent.name
        distance = cfg.get("fixed_distance", 6)
        semantics = cfg["button_semantics"]
        seed = d["seed"]
        verified = (
            root
            / f"stage1-firstlife-r1-{distance:g}-{semantics}-{seed}-000128/summary.json"
        )
        initial_v = (
            root
            / f"stage1-firstlife-r1-{distance:g}-{semantics}-{seed}-000000/summary.json"
        )
        # Only the fixed paired experiments use this naming/versioned review.
        use_v = d["kind"] == "fixed" and verified.exists() and initial_v.exists()
        after = json.loads(verified.read_text()) if use_v else d
        before = json.loads(initial_v.read_text())["sampled"] if use_v else d["initial"]
        metrics = list(csv.DictReader((p.parent / "metrics.csv").open()))
        row = dict(
            run=name,
            seed=seed,
            kind=d["kind"],
            fixed_distance=distance,
            button_semantics=semantics,
            aim_window=cfg.get("aim_window", "full"),
            frames=d["frames"],
            cumulative_frames=d.get("cumulative_frames", d["frames"]),
            training_seconds=d["training_seconds"],
            peak_allocated_mib=d["peak_allocated_mib"],
            initial=dict(
                ko_fraction=before["ko_fraction"], combat=before["combat"]["stamper"]
            ),
            **{
                k: dict(
                    ko_fraction=after[k]["ko_fraction"],
                    combat=after[k]["combat"]["stamper"],
                )
                for k in ["sampled", "greedy"]
            },
            fixed_seed_first_life_review=use_v
            or after["sampled"].get("first_life_only", False),
            curve=dict(
                all_finite=all(x["finite"] == "True" for x in metrics),
                min_advantage_divisor=min(
                    float(x["advantage_divisor"]) for x in metrics
                ),
                nonzero_reward_rate_first=float(metrics[0]["nonzero_reward_rate"]),
                nonzero_reward_rate_last=float(metrics[-1]["nonzero_reward_rate"]),
                entropy_zr_first=float(metrics[0]["entropy_ZR"]),
                entropy_zr_last=float(metrics[-1]["entropy_ZR"]),
                max_kl_zr=max(float(x["kl_ZR"]) for x in metrics),
                kl_stopped_updates=sum(x["early_stop_kl"] == "True" for x in metrics),
            ),
            evidence_sha256={
                str(q.relative_to(root)): digest(q)
                for q in [p, p.parent / "config.json", p.parent / "metrics.csv"]
            },
        )
        if use_v:
            row["evidence_sha256"].update(
                {str(q.relative_to(root)): digest(q) for q in [verified, initial_v]}
            )
        rows.append(row)
    output = dict(
        schema="inklab.rl.stage1.drills.aggregate.v1",
        stage1_passed=False,
        scope="synthetic input/capability trials, not normal-spawn180s match acceptance",
        notes=[
            "ZL remains masked in fixed/random_pose; zero ZL does not prove learned restraint",
            "full_release means accepted attack with FULL flag; hit counts positive-damage decisions, not collision spheres",
            "per-minute uses nominal attempt duration; primary script opponent is frozen",
            "source trials and corrected seeded first-life reviews remain distinct",
        ],
        runs=rows,
        executed_phase_frames=sum(x["frames"] for x in rows),
    )
    Path(a.out).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                runs=len(rows), phase_frames=output["executed_phase_frames"], out=a.out
            )
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    main(p.parse_args())
