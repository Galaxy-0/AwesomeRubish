"""One owned script room for renderer attribution; never a human demonstration."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from rl.demo import capture


def run(args):
    predicate = getattr(args, "predicate", "strict")
    shots = getattr(args, "screenshots", False)
    manifest = json.loads(args.host.with_suffix(".build.json").read_text())
    if predicate != "strict" and not manifest.get("predicate_experiment"):
        raise ValueError("predicate variants require the isolated build_render host")
    overlay = capture.safe_out(args.overlay) if args.overlay else None
    warm = getattr(args, "warm_from", None)
    if warm:
        warm = capture.safe_out(warm)
    if overlay and not (overlay / "manifest.json").is_file():
        raise ValueError("private quality overlay manifest required")
    base = capture.DemoSession

    class ProfileSession(base):
        def host_options(self, n):
            options = super().host_options(n)
            options["DM_DEMO_PREDICATE"] = predicate
            if shots and n == 0:
                folder = capture.safe_out(args.out) / "screenshots"
                folder.mkdir(exist_ok=True)
                options["DM_DEMO_SHOT_DIR"] = str(folder)
                options["DM_NVN_SHOT_OUT"] = "1280x720"
            if args.gpu_profile:
                options.update(
                    DM_NVN_PASSGPU4=str(self.out / f"player-{n}/gpu-pass.tsv"),
                    DM_NVN_PASSGPU4_RANGES="600-611,1200-1211",
                )
            if overlay:
                options["DM_ROMFS_OVERLAY"] = str(overlay)
            return options

    capture.DemoSession = ProfileSession
    try:
        capture.run(
            SimpleNamespace(
                fixture=True,
                source="script",
                allow_unqualified=False,
                host=args.host,
                modules=args.host.parent / "modules",
                out=args.out,
                resolution=None,
                present_link=args.present_link,
                loadout="primary_only",
                opponent="52",
                policy=None,
                opponent_stride=None,
                timeout=1200,
                max_frames=args.frames,
                pace=True,
                fixture_inputs=getattr(args, "fixture_inputs", None),
                render_predicate=predicate,
                warm_from=warm,
                max_catchup_frames=getattr(args, "max_catchup_frames", 6),
            )
        )
    finally:
        capture.DemoSession = base
    out = capture.safe_out(args.out)
    if out.exists():
        capture.write(
            out / "experiment.json",
            dict(
                kind="passive attribution/private native visual quality experiment",
                counter_instrumented=args.gpu_profile,
                overlay=str(overlay) if overlay else None,
                visual_parameters=json.loads((overlay / "manifest.json").read_text())
                if overlay
                else None,
                native_present_interval_override=False,
                realtime60_claimed=False,
                no_training=True,
                predicate=predicate,
                screenshots=shots,
                warm_from=str(warm) if warm else None,
                max_catchup_frames=getattr(args, "max_catchup_frames", 6),
            ),
        )
    native = json.loads((out / "result.json").read_text())
    return int(
        bool(native["errors"])
        or not (native["complete"] or native["frames"] == args.frames)
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", type=Path, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--frames", type=int, default=1800)
    p.add_argument("--present-link", type=int, choices=[0, 1], default=1)
    p.add_argument("--gpu-profile", action="store_true")
    p.add_argument("--overlay")
    p.add_argument(
        "--predicate", choices=["strict", "async", "always"], default="strict"
    )
    p.add_argument("--fixture-inputs", type=Path)
    p.add_argument("--screenshots", action="store_true")
    p.add_argument("--warm-from", type=Path)
    p.add_argument("--max-catchup-frames", type=int, default=6)
    raise SystemExit(run(p.parse_args()))
