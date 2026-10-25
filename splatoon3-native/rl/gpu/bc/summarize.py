"""Allowlisted aggregate report only: never includes maps, traces or checkpoints."""

import argparse
import hashlib
import json
from pathlib import Path


def main(a):
    root = Path(a.root)
    source = json.loads((root / "dataset-report.json").read_text())
    result = dict(
        schema="inklab.rl.bc.first-summary.v1",
        recordings={},
        fits={},
        evaluations={},
        native={},
    )
    for name, d in source.items():
        report = d["source_report"]
        result["recordings"][name] = dict(
            samples=d["samples"],
            rejected_samples=d["rejected_samples"],
            source_frames=report["source_frames"],
            invalid_packet_frames_skipped=report["invalid_packet_frames_skipped"],
            decision_stride=report["decision_stride"],
            masked_fraction=d["masked_fraction"],
            action_counts=d["actions"],
            physical_action_counts=d["physical_actions"],
            quantization=report["quantization"],
            position_import_error_units=report["position_import_error_units"],
            source_sha256=report["source_sha256"],
            shard_sha256=d["shards_sha256"],
            free_replay={
                variant: {
                    role: {
                        k: v[k]
                        for k in (
                            "position",
                            "horizontal",
                            "vertical",
                            "hp",
                            "ink",
                            "alive_mismatches",
                            "horizons",
                        )
                    }
                    for role, v in values.items()
                }
                for variant, values in d["free_replay"]["variants"].items()
            },
        )
    result["persistence_baseline"] = json.loads((root / "persistence.json").read_text())
    for path in sorted(root.glob("fit-*/result.json")):
        result["fits"][path.parent.name] = json.loads(path.read_text())
    for path in sorted(root.glob("eval-*/result.json")):
        r = json.loads(path.read_text())
        result["evaluations"][path.parent.name] = {
            k: v for k, v in r.items() if k != "per_game"
        }
    for path in sorted(root.glob("native-*/result.json")):
        r = json.loads(path.read_text())
        result["native"][path.parent.name] = {
            k: r.get(k)
            for k in [
                "passed",
                "complete",
                "errors",
                "frames",
                "bc_checkpoint_sha256",
                "turf_ratio_by_role",
                "controlled_wall_seconds",
                "controlled_presents_per_second",
                "session",
                "kd_semantics",
            ]
        }
        telemetry = path.parent / "telemetry-summary.json"
        if telemetry.exists():
            result["native"][path.parent.name]["hud_by_role"] = json.loads(
                telemetry.read_text()
            )["hud_by_role"]
    result["checkpoint_sha256"] = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.glob("fit-*/*.pt")
    }
    remote = root / "remote-final.log"
    if remote.exists():
        result["remote_closeout"] = json.loads(remote.read_text().splitlines()[0])
    Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    main(p.parse_args())
