"""Controlled native firefight and ink/stage survey; never human BC labels.

One owned private room. Natural movement/healing; explicit ideal aim only.
All setup/aim discontinuities are labelled and excluded from training.
"""

import argparse
from contextlib import contextmanager
import json
import math
from pathlib import Path
import traceback
from unittest.mock import patch
from tools.zipcaster_d3.native import DuelLab, NativeSession
from tools.zipcaster_d3r.control import Aim, neutral
from tools.zipcaster_d3r.weapon_aim import blade_angles
from .capture import trace
from .build_host import ROOT, sha


class TruthLab(DuelLab):
    def __init__(self, host, name):
        super().__init__("truth-" + name, 1, host=host, modules=host.parent / "modules")
        self.rows = []
        self.inputs = []
        self.absolute_ink_frames = []
        self.ink_schedule = self.out / "ink-schedule.txt"
        self.ink_schedule.write_text("")
        self.result.update(
            source="controlled_truth_fixture",
            loadout_mode="primary_only",
            host=str(host),
            host_manifest_sha256=sha(host.with_suffix(".build.json")),
            weapons=[8000, 50],
            complete=False,
            frames=0,
            ideal_operation_fixture=True,
            action_labels_trainable=False,
            direct_aim=True,
            no_position_or_hp_writes=True,
        )

    def step(self, actions, label, frames=6):
        if not self.rows:
            self.rows.append(dict(frame=0, infos=self.origins))
            self.barrier_stream = (self.out / "native-barriers.jsonl").open("w")
            self.input_stream = (self.out / "inputs-per-present.jsonl").open("w")
            self.barrier_stream.write(json.dumps(self.rows[0]) + "\n")
        for _ in range(frames):
            infos = super().step(actions, label, 1)
            f = len(self.inputs)
            inp = dict(
                frame_interval=[f, f + 1], actions=actions, label=label, trainable=False
            )
            row = dict(frame=f + 1, infos=infos, label=label)
            self.rows.append(row)
            self.inputs.append(inp)
            self.input_stream.write(json.dumps(inp) + "\n")
            self.barrier_stream.write(json.dumps(row) + "\n")
        self.input_stream.flush()
        self.barrier_stream.flush()
        return infos

    def ink_snapshot(self, label):
        # mtl_set_frame counts absolute native presents, matching ACK frame IDs.
        f = self.info(0)["frame"] + 2
        self.absolute_ink_frames.append(f)
        self.ink_schedule.write_text(
            "\n".join(map(str, self.absolute_ink_frames)) + "\n"
        )
        self.step(self.actions(), "ink-sample-" + label, 5)
        self.result.setdefault("ink_controls", []).append(
            dict(
                label=label,
                absolute_frame=f,
                relative_frame=f - self.origins["player_0"]["frame"],
                infos=self.env.process_infos,
            )
        )
        self.capture(label)
        self.save()

    def close(self):
        self.result["frames"] = len(self.inputs)
        for stream in [
            getattr(self, "input_stream", None),
            getattr(self, "barrier_stream", None),
        ]:
            if stream:
                stream.close()
        if self.rows:
            trace(self.rows, self.inputs, self.out)
        super().close()


@contextmanager
def controlled(lab):
    aim = Aim(lab)
    old = NativeSession.host_options

    def options(session, n):
        ink = lab.out / "ink-targets"
        ink.mkdir(exist_ok=True)
        return (
            old(session, n)
            | dict(
                DM_TEST_DEMO="1",
                DM_TEST_DEMO_TRUTH="1",
                DM_TEST_AIM="1",
                DM_TEST_AIM_FILE=str(aim.paths[n]),
                DM_DEMO_NATIVE_CAPTURE="1",
                DM_D2B_SENSOR="1",
                DM_DEMO_PREDICATE="async",
                DM_R0_CAMERA_PLUS5="1",
                DM_PRESENT_LINK="0",
                DM_HEADLESS="1",
                DM_RL_STALL_SECONDS="120",
            )
            | (
                dict(
                    DM_DEMO_INK_DIR=str(ink), DM_DEMO_INK_SCHEDULE=str(lab.ink_schedule)
                )
                if n == 0
                else {}
            )
        )

    with patch.object(NativeSession, "host_options", options):
        try:
            yield aim
        finally:
            aim.off()


def run(a):
    lab = TruthLab(a.host.resolve(), a.name)
    rec = json.loads(a.host.with_suffix(".build.json").read_text())
    if not rec.get("native_truth_survey"):
        raise ValueError("explicit truth-survey fixture host required")
    lab.result["driver_sha256"] = sha(__file__)
    lab.result["paint_native_pitch"] = a.paint_pitch
    print(lab.out, flush=True)
    try:
        with controlled(lab) as aim:
            lab.start()
            if a.setup_only:
                lab.result.update(passed=True, controlled_setup_complete=True)
                return 0
            if a.extended_ink:
                # Sample the high spawn support before dropping to mid. The
                # navigation atlas is directed; do not invent a route back up.
                lab.ink_snapshot("high-spawn-before")
                aim.set_native(0, 0, a.paint_pitch)
                lab.step(lab.actions(), "high-spawn-aim", 4)
                act = neutral()
                act["buttons"][0] = 1
                lab.act(0, act, "high-spawn-light", 1)
                lab.step(lab.actions(), "high-spawn-travel", 55)
                lab.ink_snapshot("high-spawn-after")
                aim.off()
            lab.navigate({0: [0, 3, 8], 1: [-6, 3, 8]}, "middle-setup")
            lab.result["middle_ready"] = lab.env.process_infos
            # Reproducible stage timing with a visible, stationary opponent.
            params = json.loads(
                (ROOT / "work/d3r/attack-parameters-v1.json").read_text()
            )
            lab.ink_snapshot("before-paint")
            for n in (0, 1):
                aim.set_native(n, 0 if n == 0 else math.pi, a.paint_pitch)
                lab.step(lab.actions(), f"paint-{n}-aim", 4)
                for j in range(2):
                    act = neutral()
                    act["buttons"][0] = 1
                    lab.act(n, act, f"paint-{n}-press-{j}", 1 if n == 0 else 10)
                    lab.step(lab.actions(), f"paint-{n}-release-{j}", 60)
                lab.ink_snapshot(f"after-paint-{n}")
                aim.off()
            lab.refill(0, 150)
            lab.refill(1, 150)
            if a.ink_only:
                for j, goal in enumerate([[5, 3, 8], [-5, 3, 3], [-7, 3, 3]]):
                    aim.off()
                    lab.navigate({0: goal}, f"floor-anchor-{j}")
                    lab.ink_snapshot(f"floor-anchor-{j}-before")
                    aim.set_native(0, 0, a.paint_pitch)
                    lab.step(lab.actions(), f"floor-anchor-{j}-aim", 4)
                    act = neutral()
                    act["buttons"][0] = 1
                    lab.act(0, act, f"floor-anchor-{j}-light", 1)
                    lab.step(lab.actions(), f"floor-anchor-{j}-travel", 55)
                    lab.ink_snapshot(f"floor-anchor-{j}-after")
                lab.result.update(passed=True, controlled_ink_complete=True)
                return 0
            for style, hold in [("light", 1), ("full", 21), ("cancel", 12)]:
                p, q = lab.info(0)["position"], lab.info(1)["position"]
                yaw, pitch = blade_angles(
                    p, q, params, style="full" if style == "full" else "light"
                )
                aim.set_native(0, yaw, pitch)
                lab.step(lab.actions(), style + "-aim", 4)
                lab.ink_snapshot(style + "-before")
                act = neutral()
                act["buttons"][0] = 1
                lab.act(0, act, style + "-hold", hold)
                if style == "cancel":
                    act["buttons"][1] = 1
                    lab.act(0, act, "cancel-ZL", 4)
                lab.step(lab.actions(), style + "-release-cooldown", 60)
                lab.ink_snapshot(style + "-after")
                aim.off()
                if not lab.info(1)["alive"]:
                    lab.navigate({1: [-6, 3, 8]}, "target-respawn")
                # Natural recovery, keep both controls as recorded gameplay.
                lab.paint_floor(1)
                lab.refill(1, 180)
            if a.extended_ink:
                # Distinct ground/high-platform anchors; observations always
                # retain actual native poses rather than assuming navigation exact.
                for j, goal in enumerate([[5, 3, 8]]):
                    aim.off()
                    lab.navigate({0: goal}, f"ink-anchor-{j}")
                    lab.ink_snapshot(f"anchor-{j}-before")
                    aim.set_native(0, 0, a.paint_pitch)
                    lab.step(lab.actions(), f"anchor-{j}-aim", 4)
                    act = neutral()
                    act["buttons"][0] = 1
                    lab.act(0, act, f"anchor-{j}-light", 1)
                    lab.step(lab.actions(), f"anchor-{j}-travel", 55)
                    lab.ink_snapshot(f"anchor-{j}-after")
                aim.off()
                lab.navigate({0: [0, 3, 8]}, "gun-return-middle")
            # Proven in-range .52 control: native yaw, calibrated elevation.
            aim.off()
            lab.paint_floor(0)
            lab.refill(0, 200)
            p, q = lab.info(1)["position"], lab.info(0)["position"]
            aim.set_native(1, math.atan2(q[0] - p[0], q[2] - p[2]), -0.04)
            act = neutral()
            act["sticks"][1] = 0.85
            lab.act(1, act, "gun-align-body", 8)
            lab.step(lab.actions(), "gun-ready", 80)
            p, q = lab.info(1)["position"], lab.info(0)["position"]
            aim.set_native(1, math.atan2(q[0] - p[0], q[2] - p[2]), -0.04)
            lab.step(lab.actions(), "gun-final-aim", 4)
            lab.capture("gun-before")
            for _ in range(90):
                act = neutral()
                act["buttons"][0] = 1
                lab.act(1, act, "gun-fire", 1)
                if not lab.info(0)["alive"]:
                    break
            lab.capture("gun-after")
            lab.step(lab.actions(), "post-fire-lifecycle", 90)
            lab.result.update(passed=True, controlled_clip_complete=True)
    except BaseException as e:
        lab.result["errors"].append(repr(e))
        lab.result["traceback"] = traceback.format_exc()
    finally:
        lab.finish()
    print("TRUTH_CAPTURE_CLOSED " + str(lab.out), flush=True)
    return 0 if lab.result["passed"] else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", type=Path, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--extended-ink", action="store_true")
    p.add_argument("--ink-only", action="store_true")
    p.add_argument("--setup-only", action="store_true")
    p.add_argument("--paint-pitch", type=float, default=-0.65)
    raise SystemExit(run(p.parse_args()))
