"""Private positive combat QA: native image, projected entities, rays and HUD."""

import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from .capture import safe_out, write
from .state_sync import read_jsonl


def run(source, bc, out):
    source = Path(source)
    bc = Path(bc)
    out = safe_out(out)
    out.mkdir(parents=True, exist_ok=False)
    result = json.loads((source / "result.json").read_text())
    origins = read_jsonl(source / "native-barriers.jsonl")[0]["infos"]
    base = origins["player_0"]["frame"]
    controls = [
        c
        for c in result.get("ink_controls", [])
        if c["label"]
        in (
            "light-before",
            "light-after",
            "full-before",
            "full-after",
            "cancel-before",
            "cancel-after",
        )
    ]
    samples = {}
    for path in sorted(bc.glob("bc-*.npz")):
        with np.load(path) as z:
            for c in controls:
                target = c["absolute_frame"] - base + 1
                ix = int(np.argmin(abs(z["frame"] - target)))
                if c["label"] not in samples or abs(int(z["frame"][ix]) - target) < abs(
                    samples[c["label"]]["frame"] - target
                ):
                    samples[c["label"]] = {k: z[k][ix].copy() for k in z.files}
    reports = []
    palette = np.array(
        [[25, 31, 40], [180, 187, 182], [85, 139, 175], [239, 112, 64]], np.uint8
    )
    for c in controls:
        native = source / f"ink-targets/screen-{c['absolute_frame']}.png"
        if not native.exists():
            continue
        s = samples[c["label"]]
        canvas = Image.new("RGB", (1280, 1040), (21, 26, 34))
        d = ImageDraw.Draw(canvas)
        image = Image.open(native).convert("RGB")
        width = origins["player_0"]["source_width"]
        height = origins["player_0"]["source_height"]
        cropped = False
        if (
            image.width >= width
            and image.height >= height
            and image.size != (width, height)
        ):
            a = np.asarray(image)
            if not a[height:].any() and not a[:height, width:].any():
                image = image.crop((0, 0, width, height))
                cropped = True
        shot = image.resize((640, 360))
        entities = s["entities"][s["entity_mask"]]
        for entity in entities:
            x = (float(entity[0]) + 1) * 320
            y = (1 - float(entity[1])) * 180
            color = (251, 104, 59) if int(entity[3]) == 1 else (253, 222, 93)
            ImageDraw.Draw(shot).ellipse(
                (x - 8, y - 8, x + 8, y + 8), outline=color, width=3
            )
        canvas.paste(shot, (0, 30))
        types = palette[s["screen"][..., 1].astype(int).clip(0, 3)]
        canvas.paste(
            Image.fromarray(types).resize((640, 360), Image.Resampling.NEAREST),
            (640, 30),
        )
        frac = np.clip(s["screen"][..., 0] / 64, 0, 1)
        distance = np.stack(
            [240 * (1 - frac), 180 * (1 - frac) + 30, 60 + 140 * frac], -1
        ).astype(np.uint8)
        canvas.paste(
            Image.fromarray(distance).resize((640, 360), Image.Resampling.NEAREST),
            (0, 430),
        )
        d.text(
            (10, 8),
            f"Native {c['label']} + projected enemy/orange, bullet/yellow",
            fill="white",
        )
        d.text(
            (650, 8), "Ray kind: gray floor / blue wall / orange enemy", fill="white"
        )
        d.text((12, 405), "Ray distance (coarse stage0 geometry)", fill="white")
        detail = [
            f"BC frame {int(s['frame'])}; shot native frame {c['absolute_frame']}",
            f"Visible entities: {len(entities)}; types {entities[:, 3].astype(int).tolist()}",
            f"Native charge HUD: {float(s['hud'][4]):.4f}; valid {bool(s['hud_valid'][4])}",
            f"Weapon stage: {int(s['weapon_stage_id'])}; animation remaining {float(s['weapon_animation_remaining_frames']):.1f}",
            f"Native primary bullets valid: {bool(s['projectiles_native_valid'])}",
            f"Native minimap valid cells: {int(s['minimap_valid'].sum())}/{s['minimap_valid'].size}",
            f"Human/BC action label trainable: {bool(s['action_labels_trainable'])}",
            "Walls / ambiguous panels / missing readback ticks stay masked.",
        ]
        for j, line in enumerate(detail):
            d.text((650, 440 + j * 28), line, fill=(220, 226, 235))
        mm_palette = np.array(
            [[122, 130, 141], [240, 129, 43], [138, 78, 230]], np.uint8
        )
        mm = mm_palette[s["minimap"].astype(int).clip(0, 2)]
        mm[~s["minimap_valid"]] = [36, 43, 53]
        canvas.paste(
            Image.fromarray(mm.transpose(1, 0, 2)).resize(
                (400, 280), Image.Resampling.NEAREST
            ),
            (650, 730),
        )
        d.text(
            (650, 708),
            "Native minimap: orange/purple; gray neutral; dark unknown",
            fill="white",
        )
        d.text(
            (12, 820),
            f"Native ray ink valid: {int(s['screen_channel_valid'][..., 2].sum())}/576",
            fill="white",
        )
        path = out / f"{c['label']}.png"
        canvas.save(path)
        reports.append(
            dict(
                label=c["label"],
                file=str(path),
                native=str(native),
                frame=int(s["frame"]),
                visible_entities=len(entities),
                types=entities[:, 3].astype(int).tolist(),
                charge=float(s["hud"][4]),
                weapon_valid=bool(s["hud_valid"][4]),
                primary_bullets_valid=bool(s["projectiles_native_valid"]),
                minimap_valid=bool(s["minimap_valid"].any()),
                action_labels_trainable=bool(s["action_labels_trainable"]),
            )
        )
        reports[-1]["zero_padding_cropped_using_native_source_dimensions"] = cropped
    write(
        out / "report.json",
        dict(
            cases=reports,
            visual_review_required=True,
            limitation="No automated pixel-perfect pass; FOV and geometry retain accepted stage0 approximations.",
        ),
    )
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recording", required=True)
    p.add_argument("--bc", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    run(a.recording, a.bc, a.out)
