"""Reduce private, read-only native sensor logs without inventing missing truth."""

import argparse, json, re
from pathlib import Path
from .capture import write


def reduce(recording):
    out = Path(recording)
    result = json.loads((out / "result.json").read_text())
    session = Path(result["session"])
    rows = [json.loads(x) for x in (out / "native-barriers.jsonl").open()]
    origin = rows[0]["infos"]
    counts = {}
    projectiles = []
    weapons = []
    cameras = []
    for n in range(2):
        text = (session / f"player-{n}/host.log").read_text()
        base = origin[f"player_{n}"]["frame"]
        for m in re.finditer(
            r"D3R_PROJECTILE frame=(\d+) kind=(\w+) object=(0x[0-9a-f]+) vtable=([0-9a-f]+) velocity=([^ ]+) p110=([^ ]+) readonly=1",
            text,
        ):
            projectiles.append(
                dict(
                    player=n,
                    frame=int(m[1]) - base,
                    kind=m[2],
                    object=m[3],
                    vtable=m[4],
                    velocity=list(map(float, m[5].split(","))),
                    position110=list(map(float, m[6].split(","))),
                    validity="readonly sample; object lifetime/owner/active state not yet fully qualified",
                )
            )
        for m in re.finditer(
            r"DEMO_WEAPON frame=(\d+) object=(0x[0-9a-f]+) phase40_candidate=(\d+)",
            text,
        ):
            weapons.append(
                dict(
                    player=n,
                    frame=int(m[1]) - base,
                    object=m[2],
                    phase40_candidate=int(m[3]),
                    qualified=False,
                )
            )
        for m in re.finditer(
            r"D3R_STATE frame=(\d+)[^\n]*? yaw=([^ ]+) pitch=([^ ]+) v17b8=([^ ]+) v17c4=([^ ]+)",
            text,
        ):
            cameras.append(
                dict(
                    player=n,
                    frame=int(m[1]) - base,
                    yaw=float(m[2]),
                    pitch=float(m[3]),
                    eye=list(map(float, m[4].split(","))),
                    at=list(map(float, m[5].split(","))),
                )
            )
        counts[str(n)] = dict(
            full_aim_writes=text.count("D3R_APPLY"),
            camera_elisions=text.count("A8_CAMERA skipped="),
            native_weapon_setup=re.findall(
                r"SPL3_WEAPON requested=(\d+) local_kit_reads=(\d+) save_writes=(\d+)",
                text,
            ),
        )
    for name, data in [
        ("projectiles", projectiles),
        ("weapons", weapons),
        ("cameras", cameras),
    ]:
        (out / f"{name}.jsonl").write_text(
            "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in data)
        )
    from arena.hud_events import HudEvents
    from arena.lib.atlas import MapAtlas

    hud = HudEvents(origin, MapAtlas.load(1))
    for row in rows:
        hud.update(row["infos"], row["frame"])
    hud_by_role = {
        f"player_{n}": hud.summary(f"player_{n}", f"player_{1 - n}") for n in range(2)
    }
    write(out / "hud-events.json", hud.events)
    summary = dict(
        hud_by_role=hud_by_role,
        projectile_samples=len(projectiles),
        weapon_phase_candidates=len(weapons),
        camera_samples=len(cameras),
        counts=counts,
        native_dense_paint=False,
        weapon_phase_complete=False,
        projectile_active_set_complete=False,
        unknown_is_not_zero=True,
        notes=[
            "No phase samples is unknown, not idle.",
            "Native final turf comes from Winners; dense paint is not captured.",
            "Raw vectors remain private and are not promised to be complete visible entities.",
        ],
    )
    write(out / "telemetry-summary.json", summary)
    lines = [
        "# 本局录制摘要",
        "",
        f"来源：{result['source']}；完整到Winners：{result['complete']}；present：{result['frames']}。",
        "",
        "HUD击倒/倒下包含未归因原因，不能称为个人武器K/D；涂地为原生结算。",
        "",
        "|角色|HUD敌方倒下|自身倒下|已识别敌方环境倒下|原生涂地|",
        "|---|---:|---:|---:|---:|",
    ]
    for p, h in hud_by_role.items():
        turf = result.get("turf_ratio_by_role", {}).get(p)
        value = f"{100 * turf[0]:.1f}%" if turf else "未知（未完成结算）"
        lines.append(
            f"|{p}|{h['enemy_hud_downs']}|{h['own_hud_downs']}|{h['enemy_environmental_downs']}|{value}|"
        )
    lines.extend(
        ["", "实时60fps与BC真实性另见latency.json/report.json，不由完整对局自动签收。"]
    )
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("recording")
    reduce(p.parse_args().recording)
