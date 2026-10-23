"""Private screenshot/ray/entity contact sheet. Never publish/commit images."""

import argparse, json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from .capture import safe_out


def run(a):
    recording = Path(a.recording)
    bc = Path(a.bc)
    out = safe_out(a.out)
    out.mkdir(parents=True, exist_ok=False)
    result = json.load(open(recording / "result.json"))
    session = Path(result["session"])
    files = sorted(bc.glob("bc-*.npz"))
    samples = {}
    for path in files:
        with np.load(path) as z:
            for j, f in enumerate(z["frame"]):
                for target in [602, 1202]:
                    if target not in samples or abs(int(f) - target) < abs(
                        samples[target]["frame"] - target
                    ):
                        samples[target] = {
                            k: z[k][j].copy()
                            for k in [
                                "frame",
                                "screen",
                                "entities",
                                "entity_mask",
                                "hud",
                                "hud_valid",
                                "minimap_valid",
                            ]
                        }
    reports = []
    palette = np.array(
        [[26, 31, 39], [179, 187, 183], [83, 140, 178], [232, 105, 65]], np.uint8
    )
    for target, s in samples.items():
        shot = target - 2
        path = session / f"player-0/screenshots/frame-{shot}.png"
        if not path.is_file():
            continue
        canvas = Image.new("RGB", (1280, 820), (21, 26, 34))
        d = ImageDraw.Draw(canvas)
        native = Image.open(path).convert("RGB").resize((640, 360))
        entities = s["entities"][s["entity_mask"]]
        for e in entities:
            x = int((e[0] + 1) * 320)
            y = int((1 - e[1]) * 180)
            ImageDraw.Draw(native).ellipse(
                (x - 8, y - 8, x + 8, y + 8), outline=(248, 107, 64), width=3
            )
        canvas.paste(native, (0, 32))
        types = palette[s["screen"][..., 1].astype(int).clip(0, 3)]
        canvas.paste(
            Image.fromarray(types).resize((640, 360), Image.Resampling.NEAREST),
            (640, 32),
        )
        distance = s["screen"][..., 0]
        fraction = np.clip(distance / 64, 0, 1)
        rgb = np.stack(
            [240 * (1 - fraction), 180 * (1 - fraction) + 30, 60 + 140 * fraction], -1
        ).astype("uint8")
        canvas.paste(
            Image.fromarray(rgb).resize((640, 360), Image.Resampling.NEAREST), (0, 428)
        )
        d.text(
            (12, 10),
            f"Native screenshot + visible entity projections ({len(entities)} entities)",
            fill="white",
        )
        d.text(
            (652, 10),
            "32x18 ray kind: dark=none gray=floor blue=wall red=person",
            fill="white",
        )
        d.text((12, 405), "Ray distance: warm=near, blue=far (64u)", fill="white")
        d.text(
            (660, 450),
            f"BC frame {int(s['frame'])} / native shot label {shot}",
            fill="white",
        )
        d.text(
            (660, 480),
            "Missing truth is MASKED, not labeled neutral / idle / empty.",
            fill=(247, 187, 92),
        )
        d.text(
            (660, 510),
            "Native world paint: UNKNOWN (UV mapping unresolved)",
            fill="white",
        )
        d.text((660, 540), "Complete native projectile set: UNKNOWN", fill="white")
        d.text((660, 570), "Weapon charge / cooldown: UNKNOWN", fill="white")
        d.text((660, 600), "Geometry/FOV: stage0 coarse approximation", fill="white")
        d.text(
            (660, 630),
            "Self body/weapon is intentionally absent from ray contract.",
            fill="white",
        )
        d.text(
            (660, 680),
            "HUD values " + np.array2string(s["hud"], precision=2),
            fill="white",
        )
        d.text(
            (660, 710),
            "HUD validity " + np.array2string(s["hud_valid"].astype(int)),
            fill="white",
        )
        dest = out / f"frame-{shot}.png"
        canvas.save(dest)
        reports.append(
            dict(
                frame=int(s["frame"]),
                screenshot=str(path),
                output=str(dest),
                visible_entities=len(entities),
                ray_kind_counts={
                    str(k): int(np.sum(s["screen"][..., 1] == k)) for k in range(4)
                },
                distance_range=[float(distance.min()), float(distance.max())],
                missing_truth_masked=True,
            )
        )
    (out / "report.json").write_text(json.dumps(reports, indent=2) + "\n")
    print(json.dumps(reports, indent=2))
    return reports


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--recording", required=True)
    p.add_argument("--bc", required=True)
    p.add_argument("--out", required=True)
    run(p.parse_args())
