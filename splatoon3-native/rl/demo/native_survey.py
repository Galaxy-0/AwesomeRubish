"""Normalize passive demo sensors; unknown native candidates stay unqualified."""

import argparse, collections, json, re, struct
from pathlib import Path
import numpy as np
from PIL import Image
from .capture import write
from .convert import stats


def reduce(source):
    source = Path(source)
    result = json.load(open(source / "result.json"))
    session = Path(result["session"])
    barriers = [json.loads(x) for x in (source / "native-barriers.jsonl").open()]
    native = []
    weapons = []
    summary = {}
    for n in range(2):
        p = f"player_{n}"
        base = barriers[0]["infos"][p]["frame"]
        path = session / f"player-{n}/host.log"
        owner = None
        for line in path.open():
            m = re.search(r"RL_SELF_SLOT slot=\d+ player=(0x\w+)", line)
            if m:
                owner = int(m[1], 16)
                break
        poses = {
            r["infos"][p]["position_sample_frame"] - base: r["infos"][p]["position"]
            for r in barriers
            if r["infos"][p].get("position_valid")
        }
        pose_errors = []
        live = 0
        raw = 0
        states = collections.Counter()
        projectile_phases = collections.Counter()
        for line in path.open():
            m = re.search(
                r"DEMO_NATIVE_RAW frame=(\d+) kind=(\w+) object=(0x\w+) size=(\d+) data=(\w+)",
                line,
            )
            if m and m[2] in [
                "weapon_saber",
                "weapon_shooter",
                "action_saber",
                "action_shooter",
            ]:
                data = bytes.fromhex(m[5])
                kind = m[2]
                off = (
                    0x368
                    if kind.startswith("weapon_")
                    else 0x198
                    if kind == "action_saber"
                    else 0x408
                )
                if (
                    len(data) < off + 8
                    or struct.unpack_from("<Q", data, off)[0] != owner
                ):
                    continue
                f = int(m[1]) - base
                state = struct.unpack_from("<I", data, 0x38)[0]
                elapsed = struct.unpack_from("<f", data, 0xE4)[0]
                cost = struct.unpack_from("<f", data, 0xE0)[0]
                duration = struct.unpack_from("<I", data, 0xE8)[0]
                weapons.append(
                    dict(
                        player=n,
                        frame=f,
                        kind=kind,
                        object=m[3],
                        owner_qualified=True,
                        native_state38=state,
                        native_countere4=struct.unpack_from("<I", data, 0xE4)[0],
                        native_duratione8=struct.unpack_from("<I", data, 0xE8)[0],
                        elapsed_e4_float_candidate=elapsed
                        if np.isfinite(elapsed)
                        else None,
                        charge_cost_e0_candidate=cost if np.isfinite(cost) else None,
                        stage_candidate=(
                            "charging"
                            if state == 5
                            else "swinging"
                            if state == 8
                            else "cooldown"
                            if state == 6 and elapsed >= 0
                            else "idle"
                            if state == 6
                            else "wait"
                            if state == 1
                            else "unknown"
                        )
                        if kind == "action_saber"
                        else "unknown",
                        cooldown_remaining_candidate=max(0.0, duration - elapsed)
                        if kind == "action_saber"
                        and np.isfinite(elapsed)
                        and 0 <= elapsed <= 100
                        and duration <= 100
                        else None,
                        charge_frames_qualified=False,
                        cooldown_frames_qualified=False,
                    )
                )
                raw += 1
                if kind == "action_saber" and n == 0:
                    states[state] += 1
            m = re.search(
                r"DEMO_NATIVE_LIVE frame=(\d+) slot=(\d+) type=(\d+) object=(0x\w+) pose_valid=(\d+) p170=([^ ]+) p1ac=([^ ]+) hp_native=(\d+) state38=(\d+) countere4=(\d+) duratione8=(\d+) tick_valid=(\d+) tick=(\d+)",
                line,
            )
            if m:
                f = int(m[1]) - base
                pose = list(map(float, m[6].split(",")))
                b = list(map(float, m[7].split(",")))
                row = dict(
                    player=n,
                    frame=f,
                    type=int(m[3]),
                    object=m[4],
                    position170_candidate=pose,
                    position1ac_candidate=b,
                    hp_live=int(m[8]) / 1000,
                    native_state38=int(m[9]),
                    native_countere4=int(m[10]),
                    native_duratione8=int(m[11]),
                    native_tick_candidate=int(m[13]) if int(m[12]) else None,
                    native_tick_semantics_qualified=False,
                    pose_read_valid=bool(int(m[5])),
                    position_live_qualified=False,
                    weapon_phase_qualified=False,
                )
                native.append(row)
                live += 1
                if f in poses:
                    pose_errors.append(float(np.linalg.norm(np.array(pose) - poses[f])))
            m = re.search(r"DEMO_NATIVE_PROJECTILE .*phase1238_candidate=(\d+)", line)
            if m:
                projectile_phases[int(m[1])] += 1
        summary[str(n)] = dict(
            owned_weapon_snapshots=raw,
            live_candidate_samples=live,
            pose170_same_source_frame_error=stats(pose_errors),
            saber_state38_counts=dict(states),
            projectile_phase1238_counts=dict(projectile_phases),
            weapon_stage_complete=False,
            projectile_active_set_complete=False,
        )
    for name, data in [("native-state", native), ("native-weapon", weapons)]:
        (source / f"{name}.jsonl").write_text(
            "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in data)
        )
    ink = []
    arrays = {}
    for i, file in enumerate(sorted((session / "player-0/ink-targets").glob("*.png"))):
        a = np.array(Image.open(file).convert("RGBA"))
        r = a[..., 0]
        colors, counts = np.unique(r, return_counts=True)
        nonzero = np.argwhere(r > 0)
        # Native UV render target, not world-aligned paint IDs. Do not wire it
        # into minimap/ray ink without a tested UV->world/team correspondence.
        arrays[f"sample_{i}"] = np.array(
            Image.fromarray(r).resize((256, 256), Image.Resampling.NEAREST)
        )
        ink.append(
            dict(
                file=str(file),
                native_size=list(a.shape[:2]),
                sample_size=[256, 256],
                channel="R raw native UV, owner/neutral semantics unqualified",
                r_nonzero_pixels=int((r > 0).sum()),
                r_values=colors.tolist(),
                nonzero_bounds=(
                    [nonzero.min(0).tolist(), nonzero.max(0).tolist()]
                    if len(nonzero)
                    else None
                ),
                world_mapping_qualified=False,
                per_frame_coverage=False,
            )
        )
    if arrays:
        np.savez_compressed(source / "native-ink-uv-survey.npz", **arrays)
    report = dict(
        schema="inklab.rl.demo.native-survey.v1",
        roles=summary,
        ink_samples=ink,
        native_paint_readback_available=bool(ink),
        native_world_ink_qualified=False,
        observations_may_use_candidates=False,
        notes=[
            "0x25c engine pose failed first survey, never imported.",
            "Player+170/+1ac raw candidates and native state38 are passive; static consumer/time semantics still required before BC imports.",
            "Weapon object owner link+368 and action owner links recovered; numeric state is not automatically charge/swing/cooldown.",
            "Projectile velocity callbacks are real live calls, not a complete active-set enumerator.",
            "1600x1600 UV colors readable, but no verified world/team projection or continuous cadence.",
        ],
    )
    write(source / "native-survey.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "ink_samples"}, indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("recording")
    reduce(p.parse_args().recording)
