"""Owned camera/sensitivity fixture; optional max setting writes no save data."""

import argparse, json, sys, re
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.zipcaster_d3.native import DuelLab, owned_options, neutral, NativeSession


def main(args):
    gates = {
        int(row.split("\t")[1])
        for row in (args.host.parent / "modules/main.obs.tsv").read_text().splitlines()
        if row and not row.startswith("#")
    }
    if not set(range(48, 52)) <= gates:
        raise RuntimeError(
            "camera probe build incomplete: diagnostic gates absent; do not start a host"
        )
    lab = DuelLab(
        "rl0-camera-" + args.name, host=args.host, modules=args.host.parent / "modules"
    )
    files = [lab.out / f"readonly-aim-{i}.txt" for i in (0, 1)]
    for p in files:
        p.write_text("D3Rv1 1 0 0 0\n")
    try:
        with owned_options():
            original = NativeSession.host_options

            def options(self, n):
                return original(self, n) | dict(
                    DM_TEST_AIM="1",
                    DM_TEST_AIM_FILE=str(files[n]),
                    DM_D3R_DUMP="1",
                    **({"DM_R0_CAMERA_PLUS5": "1"} if args.plus5 else {}),
                )

            with patch.object(NativeSession, "host_options", options):
                lab.start()
                for label, stick in [
                    ("idle", 0.0),
                    ("right", 1.0),
                    ("idle2", 0.0),
                    ("left", -1.0),
                    ("idle3", 0.0),
                ]:
                    a = neutral()
                    a["sticks"][2] = stick
                    for _ in range(20):
                        lab.act(0, a, "rl0-" + label, 6)
                lab.result["probe_completed"] = True
    except BaseException as ex:
        import traceback

        lab.result.update(
            errors=lab.result["errors"] + [repr(ex)], traceback=traceback.format_exc()
        )
    finally:
        lab.finish()
    print("CAMERA_PROBE " + str(lab.out), flush=True)
    if "session" not in lab.result:
        return 1
    log = Path(lab.result["session"]) / "player-0/host.log"
    text = log.read_text()
    (lab.out / "camera-readonly.json").write_text(
        json.dumps(
            dict(
                options=re.findall(r"R0_OPTIONS[^\n]+", text),
                camera=re.findall(r"R0_CAMERA[^\n]+", text),
                native_plus5_confirmed=bool(
                    args.plus5
                    and re.search(
                        r"R0_INPUT_LIVE[^\n]*gyro_normalized=1 stick_normalized=1", text
                    )
                ),
                warning="FOV projection axis/dynamic orbit not yet fully verified; readback and interpretation remain separate",
            ),
            indent=2,
        )
        + "\n"
    )
    return 0 if lab.result.get("probe_completed") else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", type=Path, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--plus5", action="store_true")
    a = p.parse_args()
    raise SystemExit(main(a))
