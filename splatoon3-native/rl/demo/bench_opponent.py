"""Serial native fixture matches for .52 tiers, no controller and no training."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from .capture import ROOT, safe_out, write
from .opponent52 import LEVELS
from .opponent_report import analyze


def run(a):
    out = safe_out(a.out)
    out.mkdir(parents=True, exist_ok=False)
    src = Path(__file__).with_name("opponent52.py")
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    components = {
        name: hashlib.sha256(src.with_name(name).read_bytes()).hexdigest()
        for name in (
            "opponent52.py",
            "opponent_nav.py",
            "opponent_vision.py",
            "capture.py",
        )
    }
    write(
        out / "plan.json",
        dict(
            levels=a.levels,
            seed=a.seed,
            max_concurrent_rooms=1,
            fixture_player=str(a.player_policy),
            native_duration_seconds=180,
            opponent_sha256=digest,
            source_components=components,
            parameters={k: vars(v) for k, v in LEVELS.items()},
            host=str(a.host),
            warm_from=str(a.warm_from),
        ),
    )
    results = []
    for level in a.levels:
        path = out / level
        command = [
            sys.executable,
            "-m",
            "rl.demo.capture",
            "--fixture",
            "--fixture-headless",
            "--source",
            "script",
            "--fixture-player-policy",
            str(a.player_policy),
            "--opponent",
            "52",
            "--opponent-level",
            level,
            "--opponent-seed",
            str(a.seed),
            "--host",
            str(a.host),
            "--modules",
            str(a.host.parent / "modules"),
            "--render-predicate",
            "async",
            "--present-link",
            "0",
            "--max-catchup-frames",
            "1",
            "--ink-every",
            "30",
            "--warm-from",
            str(a.warm_from),
            "--out",
            str(path),
        ]
        print("START " + level, flush=True)
        with (out / f"{level}.log").open("w") as log:
            p = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        if p.returncode:
            raise RuntimeError(
                f"{level} fixture failed; original artifacts preserved: {path}"
            )
        if any(
            hashlib.sha256(src.with_name(name).read_bytes()).hexdigest() != sha
            for name, sha in components.items()
        ):
            raise RuntimeError("opponent source changed during native comparison")
        value = analyze(path)
        results.append(value)
        write(
            out / "results.json",
            dict(
                results=results,
                complete=len(results) == len(a.levels),
                scope="One native180s match/tier/seed, identical scripted controller; not a population difficulty proof",
            ),
        )
        print(
            "DONE "
            + level
            + " "
            + json.dumps(
                {
                    k: value[k]
                    for k in [
                        "opponent_turf_percent",
                        "hit_fraction_proxy",
                        "hud_downs",
                        "damage_to_player",
                        "first_fire_after_acquisition_ms",
                        "engagement_survival_seconds",
                    ]
                }
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    p.add_argument(
        "--levels", nargs="+", choices=[*LEVELS, "turret"], default=list(LEVELS)
    )
    p.add_argument("--seed", type=int, default=0)
    p.add_argument(
        "--player-policy", type=Path, default=ROOT / "arena/policies/alpha/versions/v6"
    )
    p.add_argument(
        "--host",
        type=Path,
        default=ROOT / "work/rl-demo/ink-recording-host-r1/dmhost-demo",
    )
    p.add_argument(
        "--warm-from", type=Path, default=ROOT / "work/rl-demo/run74/replay-final-r5"
    )
    raise SystemExit(run(p.parse_args()))
