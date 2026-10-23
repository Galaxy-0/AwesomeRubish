"""Native packet-vs-support residuals, no new experiments or state correction."""

import argparse
import json
from pathlib import Path
import torch
from rl.gpu.geometry import Geometry
from .convert import stats
from .capture import write


def audit(source, old_data, new_data, out):
    rows = [json.loads(x) for x in (Path(source) / "native-barriers.jsonl").open()]
    positions = []
    seen = set()
    for row in rows:
        for role, i in row["infos"].items():
            key = role, i.get("position_sample_frame")
            if key in seen:
                continue
            seen.add(key)
            if (
                i.get("position_valid")
                and i.get("alive")
                and i.get("referee_motion", {}).get("ground_contact") in (0, 4)
                and i["position"][1] < 25
            ):
                positions.append(i["position"])
    p = torch.tensor(positions, dtype=torch.float32)
    result = dict(
        source=str(source),
        samples=len(p),
        scope="Actual native source packets, reported grounded at ACK. Contact state may be up to4f newer than position. Not triangle-membership/side-collision or full dynamics qualification.",
        models={},
    )
    for name, path in [("navigation", old_data), ("triangles", new_data)]:
        geo = Geometry(path, torch.device("cpu"))
        floor, cell = geo.support(p)
        error = p[:, 1] - floor
        valid = cell >= 0
        result["models"][name] = dict(
            valid=int(valid.sum()),
            missing=int((~valid).sum()),
            height_above_support_u=stats(error[valid].numpy()),
            above_0_3_fraction=float((error[valid] > 0.3).float().mean()),
        )
    write(Path(out), result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recording", required=True)
    p.add_argument("--old-data", default="work/rl-stage0/data-v5")
    p.add_argument("--new-data", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    torch.set_num_threads(1)
    audit(a.recording, a.old_data, a.new_data, a.out)
