"""Offline decision/input/native alignment. Never imported by the opponent.

Mode labels alone are not proof of firing, moving or painting. This reducer uses
actual per-present inputs and native own samples, and retains denominator counts.
"""

import argparse
import bisect
import collections
import json
import math
from pathlib import Path
import numpy as np
from .capture import write
from .opponent_report import rows


def audit(recording):
    path = Path(recording)
    result = json.loads((path / "result.json").read_text())
    range_cap = result.get("opponent_parameters", {}).get("fire_range", 13.4)
    decisions = rows(path / "opponent-decisions.jsonl")
    frames = [d["frame"] for d in decisions]
    barriers = rows(path / "native-barriers.jsonl")
    inputs = rows(path / "inputs-per-present.jsonl")
    timing = rows(path / "timing.jsonl")
    modes = collections.defaultdict(list)
    positions = collections.defaultdict(list)
    ink = collections.Counter()
    previous = None
    blocked = collections.Counter()
    for f, action in enumerate(inputs):
        d = decisions[max(0, bisect.bisect_right(frames, f) - 1)]
        i = barriers[f]["infos"]["player_1"]
        a = action["actions"]["player_1"]
        modes[d["mode"]].append((a["buttons"][0], math.hypot(*a["sticks"][:2])))
        if not (i.get("alive") and i.get("position_valid") and i["position"][1] < 20):
            previous = None
            continue
        positions[d["mode"]].append(i["position"])
        if previous:
            old = previous
            if i.get("ink_valid") and old.get("ink_valid"):
                ink[d["mode"]] += max(0, old["ink"] - i["ink"])
        previous = i
        if f >= 120:
            old = barriers[f - 120]["infos"]["player_1"]
            if old.get("alive") and old.get("position_valid"):
                dist = math.hypot(
                    i["position"][0] - old["position"][0],
                    i["position"][2] - old["position"][2],
                )
                if dist < 0.6 and math.hypot(*a["sticks"][:2]) > 0.1:
                    blocked[d["mode"]] += 1
    summaries = {}
    for mode, v in modes.items():
        a = np.array(v)
        p = np.asarray(positions[mode])
        summaries[mode] = dict(
            presents=len(v),
            seconds=len(v) / 60,
            actual_ZR_fraction=float(a[:, 0].mean()),
            zero_movement_input_fraction=float((a[:, 1] < 0.1).mean()),
            travel_stall_presents=int(blocked[mode]),
            native_ink_spent_estimate=ink[mode],
            visited_2u_cells=len({tuple(np.floor(x / 2).astype(int)) for x in p}),
            bounds=[p.min(0).tolist(), p.max(0).tolist()] if len(p) else None,
        )
    combat = [d for d in decisions if d["mode"] in ("engage", "cover")]
    value = dict(
        recording=str(path),
        mode_effects=summaries,
        combat_decisions=len(combat),
        combat_range_gate_u=range_cap,
        combat_range_ready=sum(
            d.get("distance", math.inf) <= range_cap for d in combat
        ),
        combat_reaction_ready=sum(
            d["frame"] >= d.get("reaction_at", math.inf) for d in combat
        ),
        combat_fire_decisions=sum(bool(d.get("fire")) for d in combat),
        combat_distances_u={
            str(q): float(
                np.percentile([d["distance"] for d in combat if "distance" in d], q)
            )
            for q in (0, 10, 50, 90, 100)
        }
        if combat
        else None,
        python_input_work_ms={
            str(q): float(
                np.percentile(
                    [(r["send_ns"] - r["sample_ns"]) / 1e6 for r in timing], q
                )
            )
            for q in (50, 99, 100)
        },
        turf=result.get("turf_ratio_by_role"),
        limits="2s displacement stall proxy; ink spent is positive own ink decrements, not exact paint. No live truth is fed back into the controller.",
    )
    write(path / "opponent-audit.json", value)
    return value


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("recording")
    print(json.dumps(audit(p.parse_args().recording), indent=2))
