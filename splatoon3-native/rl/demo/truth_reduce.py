"""Evidence reduction for controlled native truth; no unqualified UV/actors import."""

import argparse
import collections
import json
from pathlib import Path
import re
import numpy as np
from PIL import Image
from .capture import write
from .build_host import sha
from .state_sync import read_jsonl
from .telemetry import reduce as telemetry
from .native_survey import reduce as survey
from .weapon_truth import decode_saber


def reduce(source):
    source = Path(source)
    telemetry(source)
    survey(source)
    result = json.loads((source / "result.json").read_text())
    rows = read_jsonl(source / "native-barriers.jsonl")
    origins = rows[0]["infos"]
    stage = []
    event_edges = []
    previous = {}
    squid = collections.Counter()
    for row in rows:
        for p, i in row["infos"].items():
            old = previous.get(p, i)
            if i.get("hp_valid") and old.get("hp_valid") and i["hp"] < old["hp"] - 0.1:
                event_edges.append(
                    dict(
                        frame=row["frame"],
                        label=row.get("label"),
                        player=p,
                        damage=(old["hp"] - i["hp"]) * 100,
                        hp=i["hp"],
                        down=not bool(i.get("alive")),
                    )
                )
            if i.get("referee_motion", {}).get("form_squid") == 1:
                squid[p] += 1
            previous[p] = i
    raw_hash = {}
    for n in range(2):
        base = origins[f"player_{n}"]["frame"]
        path = Path(result["session"]) / f"player-{n}/host.log"
        raw_hash[str(path)] = sha(path)
        for line in path.open():
            m = re.search(
                r"DEMO_TRUTH_ACTION frame=(\d+) slot=\d+ type=(\d+) object=\w+ state=(\d+) cost=([^ ]+) elapsed=([^ ]+) duration=(\d+)",
                line,
            )
            if m and int(m[2]) == 3 and n == 0:
                d = decode_saber(int(m[3]), float(m[4]), float(m[5]), int(m[6]))
                if d:
                    stage.append(dict(player=n, frame=int(m[1]) - base, **d))
    # Preserve raw candidate sidecars and promote only the controlled, owned
    # Saber primary action. Never promote the coexisting unused action class.
    path = source / "native-state.jsonl"
    original = source / "native-state-unqualified.jsonl"
    if not original.exists():
        original.write_bytes(path.read_bytes())
    path.write_text("".join(json.dumps(x, separators=(",", ":")) + "\n" for x in stage))
    paint = []
    previous_images = {}
    for control in result.get("ink_controls", []):
        for file in sorted(
            (source / "ink-targets").glob(
                f"frame-{control['absolute_frame']}-target-*.png"
            )
        ):
            a = np.asarray(Image.open(file).convert("RGB"))
            key = file.stem.split("target-")[1]
            b = previous_images.get(key, np.zeros_like(a))
            change = np.any(a != b, axis=-1)
            pixels = np.argwhere(change)
            rgb_delta = np.count_nonzero(a != b, axis=(0, 1)).tolist()
            paint.append(
                dict(
                    label=control["label"],
                    file=str(file),
                    sha256=sha(file),
                    size=list(a.shape),
                    changed_pixels=int(change.sum()),
                    changed_by_RGB=rgb_delta,
                    changed_bbox_yx=[pixels.min(0).tolist(), pixels.max(0).tolist()]
                    if len(pixels)
                    else None,
                    actual_positions={
                        p: i.get("position") for p, i in control["infos"].items()
                    },
                    world_projection_qualified=False,
                )
            )
            previous_images[key] = a
    report = dict(
        schema="inklab.rl.demo.controlled-truth.v1",
        source=str(source),
        ideal_operation_fixture=True,
        action_labels_trainable=False,
        ready_for_training=False,
        controlled_clip_complete=result.get("controlled_clip_complete", False),
        damage_edges=event_edges,
        squid_frames=dict(squid),
        saber_samples=len(stage),
        saber_stages=dict(collections.Counter(x["weapon_stage"] for x in stage)),
        max_charge_native_frames=max(
            (x["charge_native_frames"] for x in stage), default=0
        ),
        native_dense_paint_qualified=False,
        native_projectile_active_set_qualified=False,
        paint_differences=paint,
        raw_sha256=raw_hash,
        limits=[
            "Controlled ideal aim is not a human action label; all frames trainable=false.",
            "R/G ownership measured only in this native team setup. Atlas world/layer projection remains masked.",
            "State1/E4>=0 is light swing, not idle. Charge native20 ticks maps to HUD fraction1 and GPU charge21.",
            "Animation E8 deadline is not an input-lock timer; queued/cancelled actions not inferred.",
            "Pooled pointers/1238 values alone never qualify native projectile activity.",
        ],
    )
    write(source / "truth-report.json", report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "source",
                    "damage_edges",
                    "squid_frames",
                    "saber_stages",
                    "max_charge_native_frames",
                ]
            },
            indent=2,
        )
    )
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("recording")
    reduce(p.parse_args().recording)
