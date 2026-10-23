"""Reduce native tick/release events; never extrapolate pooled bullet pointers.

Only the measured primary-only 8000/50 pair is supported. Ownership comes from
the native parameter weapon ID mapped to the two unique verified loadouts,
not from which process happened to observe the remote projectile.
"""

import collections
import json
from pathlib import Path
import re
import struct
import numpy as np
from .state_sync import read_jsonl
from .capture import write

KINDS = {"5c79398": (3, 52.0), "5c75510": (1, 35.0), "5c76df0": (2, 70.0)}
LIFE = re.compile(
    r"DEMO_TRUTH_LIFE frame=(\d+) event=(\d+) object=(\w+) vtable=(\w+) valid=(\d+) position=([^ ]+) velocity=([^ ]+) linger=(-?\d+) params=(\w+)"
)
RAW = re.compile(
    r"DEMO_NATIVE_RAW frame=(\d+) kind=lifecycle_params object=(\w+) size=\d+ data=(\w+)"
)


def reduce(source):
    source = Path(source)
    result = json.loads((source / "result.json").read_text())
    if result.get("weapons") != [8000, 50]:
        raise ValueError("unique measured primary weapon pair required")
    rows = read_jsonl(source / "native-barriers.jsonl")
    base = rows[0]["infos"]["player_0"]["frame"]
    params = {}
    events = []
    covered = set()
    counts = collections.Counter()
    path = Path(result["session"]) / "player-0/host.log"
    for line in path.open():
        if "DEMO_TRUTH_ACTION" in line:
            covered.add(int(re.search(r"frame=(\d+)", line)[1]) - base)
        m = RAW.search(line)
        if m:
            data = bytes.fromhex(m[3])
            weapon = struct.unpack_from("<I", data, 0xC)[0]
            params[(int(m[1]), m[2])] = weapon
        m = LIFE.search(line)
        if m:
            f, event = int(m[1]), int(m[2])
            counts[(event, m[4])] += 1
            events.append(
                dict(
                    frame=f - base,
                    event=event,
                    object=m[3],
                    vtable=m[4],
                    valid=bool(int(m[5])),
                    position=list(map(float, m[6].split(","))),
                    velocity=list(map(float, m[7].split(","))),
                    linger=int(m[8]),
                    params=m[9],
                )
            )
    by_frame = collections.defaultdict(list)
    for event in events:
        by_frame[event["frame"]].append(event)
    sensor_attested = {0, 2, 3} <= {e["event"] for e in events}
    owner = {}
    generation = collections.Counter()
    born = {}
    snapshots = []
    lives = []
    open_lives = {}
    previous_position = {}
    for f in sorted(covered):
        active = {}
        unknown = []
        for e in by_frame[f]:
            obj = e["object"]
            if e["event"] == 0:
                previous_position.pop(obj, None)
                generation[obj] += 1
                born[obj] = f
                weapon = params.get((f + base, e["params"]))
                owner[obj] = 0 if weapon == 8000 else 1 if weapon == 50 else None
                open_lives[obj] = dict(
                    object=obj,
                    generation=generation[obj],
                    start_frame=f,
                    owner=owner[obj],
                    vtable=e["vtable"],
                    ticks=0,
                )
            elif e["event"] in (1, 3):
                previous_position.pop(obj, None)
                active.pop(obj, None)
                if obj in open_lives:
                    lives.append(open_lives.pop(obj) | dict(end_frame=f))
            elif e["event"] == 2:
                if obj in open_lives:
                    open_lives[obj]["ticks"] += 1
                if e["vtable"] not in KINDS or owner.get(obj) is None or not e["valid"]:
                    unknown.append(obj)
                    continue
                if not np.isfinite(e["position"] + e["velocity"]).all():
                    unknown.append(obj)
                    continue
                if e["linger"] < 0:
                    kind, damage = KINDS[e["vtable"]]
                    old = previous_position.get(obj)
                    velocity_valid = bool(old and old[0] == f - 1)
                    apparent_velocity = (
                        (np.array(e["position"]) - old[1]).tolist()
                        if velocity_valid
                        else [0.0, 0.0, 0.0]
                    )
                    previous_position[obj] = (f, np.array(e["position"]))
                    active[obj] = dict(
                        object=obj,
                        generation=generation[obj],
                        owner=owner[obj],
                        kind=kind,
                        damage=damage,
                        damage_native_valid=False,
                        damage_semantics="nominal parameter, not native falloff/current per-hit damage",
                        position=e["position"],
                        velocity=apparent_velocity,
                        velocity_estimated_from_native_positions=velocity_valid,
                        native_velocity_field=e["velocity"],
                        age_frames=f - born[obj],
                        sample_frame=f,
                        position_phase="before_native_bullet_calc",
                        velocity_unit="u/native_frame",
                    )
        overflow = any(
            sum(x["owner"] == n for x in active.values()) > 8 for n in (0, 1)
        )
        snapshots.append(
            dict(
                frame=f,
                observer=0,
                projectiles=list(active.values()),
                # This certifies only the measured primary classes in this fixture,
                # not arbitrary weapons/specials/particles or another observer.
                primary_projectile_set_qualified=sensor_attested
                and not unknown
                and not overflow,
                unknown_objects=unknown,
                capacity_overflow=overflow,
            )
        )
    (source / "native-projectiles.jsonl").write_text(
        "".join(json.dumps(x, separators=(",", ":")) + "\n" for x in snapshots)
    )
    report = dict(
        schema="inklab.rl.demo.projectile-truth.v1",
        observer=0,
        scope="native 8000/50 primary actor ticks, local world0",
        snapshots=len(snapshots),
        positive_frames=sum(bool(x["projectiles"]) for x in snapshots),
        qualified_frames=sum(x["primary_projectile_set_qualified"] for x in snapshots),
        events={f"event{k[0]}-vt{k[1]}": v for k, v in counts.items()},
        lifetimes=lives,
        unclosed_lifetimes=list(open_lives.values()),
        complete_general_projectile_sensor=False,
        sensor_attested=sensor_attested,
        notes=[
            "event0 reset; event2 common BulletMove calc entry; event3 native actor release. Event1 teardown is not the pool's active lifetime boundary.",
            "Only exact observed frames imported; no pointer persistence or kinematic extrapolation. Pool generations separated.",
            "Native params+0xc weapon ID with unique verified 8000/50 roles establishes ownership. Process ID is not owner.",
            "Positions are sampled before bullet calc, potentially one native tick behind the displayed post-calc pose. No fabricated post-calc integration.",
            "Entity velocity is a causal finite difference of native positions; first tick zero+unknown. Raw BulletMove velocity retained separately (native timestep scaling can differ). Damage is nominal+unqualified and is not exposed by entities.",
            "Primary scope only, zero newly supported specials/other weapons. Observer1 not certified.",
        ],
    )
    write(source / "projectile-truth.json", report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in ["snapshots", "positive_frames", "qualified_frames", "events"]
            },
            indent=2,
        )
    )
    return report


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("recording")
    reduce(p.parse_args().recording)
