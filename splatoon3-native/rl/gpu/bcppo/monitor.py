"""Short read-only status command. No torch/CUDA allocation or game import."""

import argparse
import csv
import json
import math
import os
import time
from pathlib import Path


def summary(root):
    root = Path(root)
    result = dict(root=str(root), checked_unix=time.time())
    for name in ["status", "critic-preheat", "latest-evaluation"]:
        p = root / (name + ".json")
        if p.exists():
            result[name] = json.loads(p.read_text())
    status = result.get("status", {})
    pid = status.get("pid")
    if pid:
        try:
            os.kill(pid, 0)
            alive = True
        except ProcessLookupError:
            alive = False
        except PermissionError:
            alive = None
        result["pid_exists"] = alive
    metrics = root / "metrics.csv"
    if metrics.exists():
        rows = list(csv.DictReader(metrics.open()))
        if rows:
            names = [
                "policy_loss",
                "value_loss",
                "bc_kl",
                "approx_kl",
                "grad_norm",
                "entropy_ZR",
                "entropy_yaw",
                "entropy_pitch",
                "zr_fraction",
                "attacks_per_minute",
                "full_per_minute",
                "visible_fraction",
                "pitch_clamped_fraction",
                "longest_zr_frames",
                "peak_cuda_mib",
            ]
            result["metric_rows"] = len(rows)
            result["last20_mean"] = {
                k: sum(float(x[k]) for x in rows[-20:]) / len(rows[-20:]) for k in names
            }
            result["all_metrics_finite"] = all(
                math.isfinite(float(x[k])) for x in rows for k in names
            )
            result["training_minutes"] = float(rows[-1]["wall_seconds"]) / 60
    matches = root / "matches.jsonl"
    if matches.exists():
        rows = [json.loads(x) for x in matches.read_text().splitlines()]
        result["training_matches"] = dict(
            batches=len(rows),
            weapon_kills=sum(x["weapon_kills"] for x in rows),
            damage=sum(x["damage"] for x in rows),
            note="includes curriculum placements; not acceptance",
        )
    result["collapse_warning"] = (root / "collapse-warning.json").exists()
    result["checkpoint_files"] = len(list((root / "checkpoints").glob("*.pt")))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    print(json.dumps(summary(p.parse_args().root), indent=2))
