"""Align recorder stalls with both native peers; operates only on private logs."""

import argparse
import csv
import json
from pathlib import Path
import re
import numpy as np
from .analyze import rates


def load_rows(path):
    return [json.loads(line) for line in Path(path).open()]


def summarize(timing):
    intervals = np.diff([r["ack_ns"] for r in timing]) / 1e6
    ack = [(r["ack_ns"] - r["send_ns"]) / 1e6 for r in timing]

    def distribution(values):
        return (
            dict(
                zip(
                    ("p50", "p99", "max"),
                    map(float, np.percentile(values, [50, 99, 100])),
                )
            )
            if len(values)
            else None
        )

    return dict(
        intervals=rates(intervals),
        interval_ms=distribution(intervals),
        ack_ms=distribution(ack),
        over_ms={str(ms): int((intervals > ms).sum()) for ms in (100, 200, 500, 1000)},
        input_processing_ms=distribution(
            [(r["send_ns"] - r["sample_ns"]) / 1e6 for r in timing]
        ),
        between_ack_and_next_sample_ms=distribution(
            [(a["sample_ns"] - b["ack_ns"]) / 1e6 for b, a in zip(timing, timing[1:])]
        ),
    )


def report(out):
    out = Path(out)
    result = json.loads((out / "result.json").read_text())
    barriers = {
        r["frame"]: r["infos"] for r in load_rows(out / "native-barriers.jsonl")
    }
    timing = load_rows(out / "timing.jsonl")
    session = Path(result["session"])
    peers = []
    for role in range(2):
        directory = session / f"player-{role}"
        rows = {}
        for row in csv.reader((directory / "nvn.tsv").open(), delimiter="\t"):
            if len(row) == 3 and row[0].isdigit() and row[1].startswith("@"):
                rows.setdefault(int(row[0]), {})[row[1]] = float(row[2])
        log = (directory / "host.log").read_text(errors="replace")
        creates = {
            int(f): float(c)
            for f, c in re.findall(r"\[长帧\] 帧 (\d+)（[^\n]*?个共 ([\d.]+) ms", log)
        }
        peers.append((rows, creates, log))
    events = []
    for row in timing:
        ack = (row["ack_ns"] - row["send_ns"]) / 1e6
        if ack <= 100:
            continue
        evidence = []
        for role, (rows, creates, _) in enumerate(peers):
            # Native gfx frame labels precede the completed ACK by one present.
            # Retain the adjacent frame too: submit/callback attribution crosses
            # present boundaries. Do not silently equate compiler sums to wall time.
            native = barriers[row["frame"]][f"player_{role}"]["frame"]
            for f in range(native - 2, native + 1):
                v = rows.get(f, {})
                evidence.append(
                    dict(
                        role=role,
                        native_frame=f,
                        submit_ms=v.get("@sub_wall_ms", 0),
                        compile_ms=creates.get(f, 0),
                        libraries=v.get("@lib_new", 0),
                        pipelines=v.get("@pso_new", 0),
                        gpu_ms=v.get("@gpu_ms", 0),
                    )
                )
        events.append(
            dict(
                frame=row["frame"],
                ack_ms=ack,
                native=evidence,
                compilation_nearby=any(e["compile_ms"] > 50 for e in evidence),
            )
        )
    battle = [
        r for r in timing if all(i["phase"] == 1 for i in barriers[r["frame"]].values())
    ]
    value = dict(
        source=str(out),
        all_frames=summarize(timing),
        battle=summarize(battle),
        ack_over100=len(events),
        compilation_nearby=sum(e["compilation_nearby"] for e in events),
        events=events,
        scope="Adjacent native frame evidence; overlapping compile time across threads/peers must not be added as exclusive wall time.",
    )
    (out / "stalls.json").write_text(json.dumps(value, indent=2) + "\n")
    return value


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    r = report(p.parse_args().out)
    print(json.dumps({k: v for k, v in r.items() if k != "events"}, indent=2))
