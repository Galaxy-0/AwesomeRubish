"""One owned script room for renderer attribution; never a human demonstration."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from rl.demo import capture


def run(args):
    overlay = capture.safe_out(args.overlay) if args.overlay else None
    if overlay and not (overlay / "manifest.json").is_file():
        raise ValueError("private quality overlay manifest required")
    base = capture.DemoSession

    class ProfileSession(base):
        def host_options(self, n):
            options = super().host_options(n)
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
            ),
        )
    native = json.loads((out / "result.json").read_text())
    return int(bool(native["errors"]) or native["frames"] != args.frames)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", type=Path, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--frames", type=int, default=1800)
    p.add_argument("--present-link", type=int, choices=[0, 1], default=1)
    p.add_argument("--gpu-profile", action="store_true")
    p.add_argument("--overlay")
    raise SystemExit(run(p.parse_args()))
