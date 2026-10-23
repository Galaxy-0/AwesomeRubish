"""Compare fixed native inputs and source-frame-aligned state, without correction."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def digest(actions):
    return hashlib.sha256(
        json.dumps(actions, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load(path):
    path = Path(path)
    barriers = [json.loads(line) for line in (path / "native-barriers.jsonl").open()]
    actions = [
        json.loads(line)["actions"]
        for line in (path / "inputs-per-present.jsonl").open()
    ]
    return barriers, actions


def stats(a):
    a = np.asarray(a, float)
    return (
        dict(
            n=len(a),
            mean=float(a.mean()),
            p95=float(np.percentile(a, 95)),
            max=float(a.max()),
        )
        if len(a)
        else None
    )


def compare(a, b, start=180):
    aa, ia = load(a)
    bb, ib = load(b)
    n = min(len(ia), len(ib))
    result = dict(
        reference=str(a),
        candidate=str(b),
        input_frames=n,
        inputs_identical=ia[:n] == ib[:n],
        input_sha256=digest(ia[:n]),
        start_frame=start,
        roles={},
        scope="Measured fixed-input short test only; no state correction, no inferred unseen combat equivalence",
    )
    for role in ["player_0", "player_1"]:

        def samples(rows):
            base = rows[0]["infos"][role]["frame"]
            out = {}
            for row in rows:
                i = row["infos"][role]
                f = i.get("position_sample_frame", base) - base
                if (
                    start <= f < n
                    and i.get("position_valid")
                    and i.get("hp_valid")
                    and i.get("ink_valid")
                ):
                    out[f] = i
            return out

        sa, sb = samples(aa), samples(bb)
        frames = sorted(sa.keys() & sb.keys())
        pa = np.array([sa[f]["position"] for f in frames])
        pb = np.array([sb[f]["position"] for f in frames])
        role_result = dict(
            source_samples_reference=len(sa),
            source_samples_candidate=len(sb),
            matched_source_frames=len(frames),
            position_l2_units=stats(np.linalg.norm(pa - pb, axis=1))
            if frames
            else None,
            hp_fraction_abs=stats([abs(sa[f]["hp"] - sb[f]["hp"]) for f in frames]),
            ink_fraction_abs=stats([abs(sa[f]["ink"] - sb[f]["ink"]) for f in frames]),
            alive_mismatches=sum(sa[f]["alive"] != sb[f]["alive"] for f in frames),
            phase_mismatches=sum(sa[f]["phase"] != sb[f]["phase"] for f in frames),
            hp_values_reference=sorted({sa[f]["hp"] for f in frames}),
            hp_values_candidate=sorted({sb[f]["hp"] for f in frames}),
        )
        aligned = [
            (x["infos"][role], y["infos"][role])
            for x, y in zip(aa[start:n], bb[start:n])
            if x["infos"][role].get("position_valid")
            and y["infos"][role].get("position_valid")
        ]
        role_result["same_ack_frame"] = dict(
            position_l2_units=stats(
                [
                    np.linalg.norm(np.array(x["position"]) - y["position"])
                    for x, y in aligned
                ]
            ),
            hp_fraction_abs=stats([abs(x["hp"] - y["hp"]) for x, y in aligned]),
            ink_fraction_abs=stats([abs(x["ink"] - y["ink"]) for x, y in aligned]),
            alive_mismatches=sum(x["alive"] != y["alive"] for x, y in aligned),
            phase_mismatches=sum(x["phase"] != y["phase"] for x, y in aligned),
            hp_values_reference=sorted({x["hp"] for x, _ in aligned}),
            hp_values_candidate=sorted({y["hp"] for _, y in aligned}),
            scope="Raw same-ACK comparison, retains up to three-frame sampling phase error",
        )
        ta, tb = sorted(sa), sorted(sb)
        if ta and tb:
            grid = np.arange(max(ta[0], tb[0]), min(ta[-1], tb[-1]) + 1)
            pa = np.array([sa[f]["position"] for f in ta])
            pb = np.array([sb[f]["position"] for f in tb])
            va = np.stack([np.interp(grid, ta, pa[:, k]) for k in range(3)], 1)
            vb = np.stack([np.interp(grid, tb, pb[:, k]) for k in range(3)], 1)
            role_result["sample_clock_interpolated_position_l2"] = stats(
                np.linalg.norm(va - vb, axis=1)
            )
            role_result["interpolation_scope"] = (
                "Diagnostic linear interpolation only between actual 4-frame samples, no native state correction or bitwise/per-frame equivalence claim"
            )
        result["roles"][role] = role_result
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("reference")
    p.add_argument("candidate")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--start", type=int, default=180)
    a = p.parse_args()
    r = compare(a.reference, a.candidate, a.start)
    a.out.write_text(json.dumps(r, indent=2) + "\n")
    print(json.dumps(r, indent=2))
