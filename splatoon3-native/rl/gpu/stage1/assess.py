"""Version-bound full-match gates, historical Elo and replay exports."""

import argparse, json, time
from pathlib import Path
import torch
from .common import load_policy, digest, elo, CSV
from .evaluate import play


def main(a):
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("high")
    root = Path(a.out)
    root.mkdir(parents=True, exist_ok=False)
    current, meta = load_policy(a.checkpoint, a.device)
    result = dict(
        schema="inklab.rl.stage1.assessment.v1",
        checkpoint_sha256=digest(a.checkpoint),
        training_frames=meta["frames"],
        training_update=meta["update"],
        results={},
    )
    start = time.perf_counter()
    for i, kind in enumerate(["random", "d4-spawn", "d4-encounter"]):
        folder = root / kind
        folder.mkdir()
        r = play(
            current,
            a.data,
            a.calibration,
            games=a.games if kind != "random" else a.games * 2,
            kind=kind,
            seed=a.seed + i * 101,
            device=a.device,
            trace=folder / "trace.json",
            deterministic=not a.stochastic,
        )
        (folder / "result.json").write_text(json.dumps(r, indent=2) + "\n")
        result["results"][kind] = r
        print(
            json.dumps(dict(event="assessment", kind=kind, roles=r["roles"])),
            flush=True,
        )
    ratings = (
        json.loads(Path(a.ratings).read_text())
        if a.ratings
        else dict(ratings={}, latest={})
    )
    csv = CSV(root / "elo.csv")
    version = str(meta["update"])
    entries = [("checkpoint", path) for path in a.history]
    if a.pool_history:
        entries += [("snapshot", item) for item in meta.get("league", [])]
    seen = set()
    for kind, source in entries:
        if kind == "checkpoint":
            old, oldmeta = load_policy(source, a.device)
        else:
            from .policy import Policy

            version_number, state = source
            oldmeta = {"update": version_number}
            old = Policy(
                meta["hidden_size"],
                action_feedback=meta.get("config", {}).get("action_feedback", False),
                control_prior=meta.get("config", {}).get("control_prior", False),
                button_semantics=meta.get("config", {}).get(
                    "button_semantics", "level"
                ),
            ).to(a.device)
            old.load_state_dict(state)
            old.memory.flatten_parameters()
            old.eval()
        oldversion = str(oldmeta["update"])
        if oldversion in seen:
            del old
            continue
        seen.add(oldversion)
        r = play(
            current,
            a.data,
            a.calibration,
            games=a.history_games,
            kind="history",
            seed=a.seed + 1000 + oldmeta["update"],
            device=a.device,
            opponent=old,
            deterministic=not a.stochastic,
        )
        (root / f"history-{oldversion}.json").write_text(json.dumps(r, indent=2) + "\n")
        for role, row in r["roles"].items():
            key = version + ":" + role
            other = oldversion + ":" + role
            before = ratings["ratings"].get(key, ratings["latest"].get(role, 1000.0))
            obefore = ratings["ratings"].get(other, 1000.0)
            score = (row["wins"] + 0.5 * row["draws"]) / row["games"]
            after = elo(before, obefore, score)
            ratings["ratings"][key] = after
            ratings["ratings"][other] = obefore - (after - before)
            ratings["latest"][role] = after
            csv.write(
                dict(
                    update=meta["update"],
                    frames=meta["frames"],
                    role=role,
                    opponent_update=oldmeta["update"],
                    games=row["games"],
                    wins=row["wins"],
                    draws=row["draws"],
                    score=score,
                    rating_before=before,
                    opponent_rating_before=obefore,
                    rating_after=after,
                    opponent_rating_after=ratings["ratings"][other],
                    scope="Descriptive role-specific league Elo,K24 per evaluated batch; historical anchors1000, no cross-weapon/global player ranking",
                )
            )
        del old
    csv.close()
    (root / "elo-state.json").write_text(json.dumps(ratings, indent=2) + "\n")
    random = result["results"]["random"]["roles"]
    encounter = result["results"]["d4-encounter"]["roles"]["stamper"]
    spawn = result["results"]["d4-spawn"]["roles"]["stamper"]
    allrows = [v for r in result["results"].values() for v in r["roles"].values()]
    result["gates"] = dict(
        primary_only_actions=all(
            not r["invalid_special_inputs"] for r in result["results"].values()
        ),
        stamper_beats_random=random["stamper"]["win_rate"] >= 0.95
        and random["stamper"]["wilson95"][0] >= 0.90,
        gun_beats_random=random["52"]["win_rate"] >= 0.95
        and random["52"]["wilson95"][0] >= 0.90,
        stamper_beats_d4_spawn=spawn["wilson95"][0] > 0.5,
        stamper_beats_d4_encounter=encounter["wilson95"][0] > 0.5,
        submerged_recovery_observed=any(
            x["submerged_recovery_agent_frames"] > 0 for x in allrows
        ),
        wounded_cover_movement_observed=any(
            x["wounded_covered_movement_samples"] > 0 for x in allrows
        ),
        replay_human_review_required=True,
        training_curve_review_required=True,
    )
    result["automatic_gates_passed"] = all(
        v for k, v in result["gates"].items() if not k.endswith("_required")
    )
    result["stage1_passed"] = False
    result["acceptance_scope"] = (
        "Automatic metrics cannot certify reasonable intent or stable learning; inspect curves/replays. Full fixed180s; random roles balanced, D4 encounter separate from spawn turf."
    )
    result["wall_seconds"] = time.perf_counter() - start
    (root / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                event="assessment-complete",
                gates=result["gates"],
                automatic_gates_passed=result["automatic_gates_passed"],
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--calibration", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--history", nargs="*", default=[])
    p.add_argument("--ratings")
    p.add_argument("--pool-history", action="store_true")
    p.add_argument("--stochastic", action="store_true")
    p.add_argument("--games", type=int, default=128)
    p.add_argument("--history-games", type=int, default=64)
    p.add_argument("--seed", type=int, default=19001)
    p.add_argument("--device", default="cuda")
    main(p.parse_args())
