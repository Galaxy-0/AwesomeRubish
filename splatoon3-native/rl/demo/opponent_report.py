"""Offline native .52 sparring metrics; no optimizer or generated data in git.

Hit fraction is an explicitly labelled proxy: native own ink decrements confirm
.52 shots (0.015/shot); substantial target HP drops shortly afterwards count
likely bullet hits. Sparse state updates/ink damage mean no exact hit oracle.
"""

import argparse
import bisect
import collections
import json
from pathlib import Path
import numpy as np
from .capture import write


def rows(path):
    with Path(path).open() as stream:
        return [json.loads(x) for x in stream]


def analyze(recording):
    recording = Path(recording)
    result = json.loads((recording / "result.json").read_text())
    barriers = rows(recording / "native-barriers.jsonl")
    decisions = rows(recording / "opponent-decisions.jsonl")
    frames = [d["frame"] for d in decisions]
    origin = {p: i["frame"] for p, i in barriers[0]["infos"].items()}

    def decision(frame):
        index = bisect.bisect_right(frames, frame) - 1
        return decisions[index] if index >= 0 else {}

    samples = {p: {} for p in origin}
    for row in barriers:
        for p, i in row["infos"].items():
            f = i.get("position_sample_frame", 0) - origin[p]
            if (
                f >= 180
                and i.get("position_valid")
                and i.get("hp_valid")
                and i.get("ink_valid")
            ):
                samples[p].setdefault(f, i)
    shots = []
    damage = []
    own_damage = []
    for p, data in samples.items():
        previous = None
        for f, i in sorted(data.items()):
            if previous:
                oldf, old = previous
                if old.get("alive") and f - oldf <= 12:
                    if (
                        p == "player_1"
                        and i.get("alive")
                        and old["ink"] - i["ink"] > 0.009
                    ):
                        n = int(round((old["ink"] - i["ink"]) / 0.015))
                        d = decision(f)
                        shots.extend(
                            [f] * n
                            if d.get("mode") in ("engage", "cover") and d.get("fire")
                            else []
                        )
                    amount = (old["hp"] - i["hp"]) * 100
                    if amount >= 20:
                        (damage if p == "player_0" else own_damage).append(
                            dict(frame=f, amount=amount)
                        )
            previous = (f, i)
    likely = []
    unused = list(shots)
    for d in damage:
        choices = [j for j, s in enumerate(unused) if 0 <= d["frame"] - s <= 18]
        if choices:
            j = choices[-1]
            likely.append(dict(d, shot_frame=unused.pop(j)))
    speeds = []
    previous = None
    for f, i in sorted(samples["player_1"].items()):
        if previous:
            oldf, old = previous
            if (
                f - oldf <= 12
                and decision(f).get("mode") in ("engage", "cover")
                and i.get("alive")
                and old.get("alive")
            ):
                dx = i["position"][0] - old["position"][0]
                dz = i["position"][2] - old["position"][2]
                speed = float(np.hypot(dx, dz) * 60 / (f - oldf))
                if speed < 30:
                    speeds.append(speed)
        previous = (f, i)
    # Count starts at a visible engagement. Down ends an uncensored exposure;
    # surviving to the end/losing contact is right-censored, reported separately.
    fights = []
    start = None
    last_visible = None
    for d in decisions:
        f = d["frame"]
        if d.get("visible") and d.get("mode") in ("engage", "cover"):
            if start is None:
                start = f
            last_visible = f
        i = barriers[min(f, len(barriers) - 1)]["infos"]["player_1"]
        down = bool(i.get("alive_valid") and not i.get("alive"))
        lost = last_visible is not None and f - last_visible > 180
        if start is not None and (down or lost):
            fights.append(
                dict(
                    start=start,
                    end=f,
                    seconds=(f - start) / 60,
                    down=down,
                    censored=not down,
                )
            )
            start = None
            last_visible = None
    if start is not None:
        fights.append(
            dict(
                start=start,
                end=len(barriers) - 1,
                seconds=(len(barriers) - 1 - start) / 60,
                down=False,
                censored=True,
            )
        )
    fire_windows = []
    fire_start = None
    fire_last = None
    for d in decisions:
        f = d["frame"]
        if d.get("fire") and d.get("mode") in ("engage", "cover"):
            if fire_start is None:
                fire_start = f
            fire_last = f
        info = barriers[min(f, len(barriers) - 1)]["infos"]
        target_down = bool(
            info["player_0"].get("alive_valid") and not info["player_0"].get("alive")
        )
        own_down = bool(
            info["player_1"].get("alive_valid") and not info["player_1"].get("alive")
        )
        lost = fire_last is not None and f - fire_last > 180
        if fire_start is not None and (target_down or own_down or lost):
            fire_windows.append(
                dict(
                    start=fire_start,
                    end=f,
                    seconds=(f - fire_start) / 60,
                    target_down=target_down,
                    censored=not target_down,
                )
            )
            fire_start = None
            fire_last = None
    if fire_start is not None:
        fire_windows.append(
            dict(
                start=fire_start,
                end=len(barriers) - 1,
                seconds=(len(barriers) - 1 - fire_start) / 60,
                target_down=False,
                censored=True,
            )
        )
    reaction = []
    seen = set()
    for d in decisions:
        if (
            d.get("fire")
            and d.get("mode") in ("engage", "cover")
            and d.get("acquired_at") not in seen
        ):
            seen.add(d.get("acquired_at"))
            reaction.append((d["frame"] - d["acquired_at"]) * 1000 / 60)
    modes = collections.Counter(d["mode"] for d in decisions)
    final = barriers[-1]["infos"]["player_1"]
    hud = {}
    for text, player in final.get("hud_slot_agents", {}).items():
        slot = int(text)
        if final.get("hud_counter_valid", [0] * 8)[slot]:
            hud[player] = final["hud_downs"][slot]
    inputs = rows(recording / "inputs-per-present.jsonl")
    active = [a["actions"]["player_1"] for a in inputs[180:]]

    def summary(v):
        return (
            dict(
                n=len(v),
                median=float(np.median(v)),
                min=float(min(v)),
                max=float(max(v)),
            )
            if v
            else None
        )

    value = dict(
        recording=str(recording),
        level=result.get("opponent_level"),
        seed=result.get("opponent_seed"),
        frames=result["frames"],
        complete=result["complete"],
        errors=result["errors"],
        turf_ratio_by_role=result.get("turf_ratio_by_role"),
        opponent_turf_percent=(100 * result["turf_ratio_by_role"]["player_1"][0])
        if result.get("turf_ratio_by_role", {}).get("player_1")
        else None,
        hud_downs=result.get("hud_downs"),
        hud_downs_by_player_from_opponent_view=hud,
        modes=dict(modes),
        combat_shots_from_native_ink=len(shots),
        likely_bullet_damage_edges=len(likely),
        hit_fraction_proxy=len(likely) / len(shots) if shots else None,
        hit_fraction_scope=">=20HP target damage edges within18f after a .015 native ink combat shot; NOT exact native collision attribution",
        damage_to_player=sum(d["amount"] for d in damage),
        damage_to_opponent=sum(d["amount"] for d in own_damage),
        first_fire_after_acquisition_ms=summary(reaction),
        engagements=fights,
        engagement_survival_seconds=summary([f["seconds"] for f in fights]),
        engagement_uncensored_down_seconds=summary(
            [f["seconds"] for f in fights if f["down"]]
        ),
        first_fire_to_target_down_seconds=summary(
            [e["seconds"] for e in fire_windows if e["target_down"]]
        ),
        fire_windows=fire_windows,
        combat_horizontal_speed_units_s=summary(speeds),
        moving_fraction=sum(np.linalg.norm(a["sticks"][:2]) > 0.1 for a in active)
        / max(1, len(active)),
        squid_input_fraction=sum(a["buttons"][1] > 0 for a in active)
        / max(1, len(active)),
    )
    write(recording / "opponent-metrics.json", value)
    return value


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("recording")
    a = p.parse_args()
    print(json.dumps(analyze(a.recording), indent=2))
