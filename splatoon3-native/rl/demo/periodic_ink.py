"""Bind periodic images to THIS recording's native panel transforms.

Previously qualified panels only, exact numeric equality to the measured table,
matching build/map, immutable reference validation. Never carry snapshots forward.
"""

import argparse
import json
from pathlib import Path
import numpy as np
from .build_host import sha
from .capture import write
from .native_ink import extract, attach


def normalize(recording, reference="work/rl-demo/truth-ink-mapping-r1"):
    source, reference = Path(recording), Path(reference).resolve()
    result = json.loads((source / "result.json").read_text())
    if result.get("errors"):
        raise ValueError("failed native recording cannot qualify ink readbacks")
    log = (Path(result["session"]) / "player-0/host.log").read_text(errors="replace")
    if "命令缓冲执行出错" in log:
        raise ValueError("GPU submission error: retain images as diagnostic only")
    manifest = json.loads(Path(result["host"]).with_suffix(".build.json").read_text())
    if result["map"] != "Yunohana" or not manifest.get("periodic_ink_panels"):
        raise ValueError("per-recording native panel hooks required")
    measured = source / "ink-panel-map"
    extract(source, measured)
    with np.load(measured / "panels.npz") as a, np.load(reference / "panels.npz") as b:
        if set(a.files) != set(b.files) or any(
            not np.array_equal(a[k], b[k]) for k in a.files
        ):
            raise ValueError(
                "native panel table differs from the measured calibration; keep all paint masked"
            )
    validation = json.loads((reference / "controls-validation.json").read_text())
    if not validation.get("passed") or validation["panels_sha256"] != sha(
        reference / "panels.npz"
    ):
        raise ValueError("invalid immutable native control evidence")
    write(
        measured / "controls-validation.json",
        validation
        | dict(
            panels_sha256=sha(measured / "panels.npz"),
            reference_validation_sha256=sha(reference / "controls-validation.json"),
            reference_mapping=str(reference),
            per_session_native_arrays_exact_match=True,
            qualification_scope="same 133/147 panels as original controls, verified native table in this session; no new surfaces qualified",
        ),
    )
    # attach supports both standalone controlled fixtures and recorder sessions.
    attach(source, measured)
    index = json.loads((source / "native-ink.json").read_text())
    code = {
        p.name: sha(p)
        for p in [Path(__file__), Path(__file__).with_name("native_ink.py")]
    }
    index["normalizer_source_sha256"] = code
    write(source / "native-ink.json", index)
    frames = [r["frame"] for r in index["snapshots"]]
    report = dict(
        source_sha256=code,
        schema="inklab.periodic.ink.v1",
        source=str(source),
        requested_period_frames=result["ink_every_frames"],
        snapshots=len(frames),
        first_frame=min(frames) if frames else None,
        last_frame=max(frames) if frames else None,
        max_gap_frames=max(np.diff(frames)).item() if len(frames) > 1 else None,
        per_session_native_arrays_exact_match=True,
        qualified_panels=index["qualified_panels"],
        snapshot_hold=False,
        dense_paint_native_valid=False,
        scope="periodic exact-frame native ink in qualified ground panels, walls/ambiguous/missing ticks masked",
    )
    write(source / "periodic-ink.json", report)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("recording")
    p.add_argument("--reference", default="work/rl-demo/truth-ink-mapping-r1")
    a = p.parse_args()
    print(json.dumps(normalize(a.recording, a.reference), indent=2))
