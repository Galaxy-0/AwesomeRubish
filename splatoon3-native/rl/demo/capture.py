"""Explicit native demonstration fixture: one owned room, full rendering, no training.

Writes the existing S1 inputs/barriers and showcase trace plus raw USB measurements.
Every ACK is recorded; source sample frames/validity are preserved (not interpolated).
"""

import argparse
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import signal
import time
import threading
import traceback
from tools.m5_resources import Monitor, system_sample, memory_row
import numpy as np
from .protocol import DemoEnv
from rl.native_start import NativeSession, validate_runtime
from rl.session import ROOT
from rl.loadout import uniform_loadout
from arena.referee_api import RefereeAPI
from arena.config import PolicySpec
from arena.control_process import ControlProcess, own_special
from arena.lib.atlas import MapAtlas
from arena.lib.skills import Skills, neutral, aim_at


def write(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def safe_out(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT / "work"):
        raise ValueError("recordings must stay under private work/")
    return path


class DemoMonitor(Monitor):
    """Same memory stop rules, without repeatedly regex-scanning growing logs."""

    def sample(self, hosts):
        row = system_sample()
        row["hosts"] = [
            dict(player=n, pid=p.pid, memory=memory_row(d / "memory.tsv"))
            for n, p, d in hosts
        ]
        row["rss_sum_mib"] = sum(h["memory"].get("rss", 0) for h in row["hosts"])
        row["footprint_sum_mib"] = sum(
            h["memory"].get("phys_footprint", 0) for h in row["hosts"]
        )
        row["new_swapout_bytes"] = (
            max(0, row["swapouts"] - self.baseline["swapouts"]) * row["page_size"]
        )
        self.rows.append(row)
        with (self.out / "resources.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        if row["new_swapout_bytes"] > 2 * 2**30:
            raise RuntimeError("resource stop: additional swapout exceeds 2 GiB")
        if row["pressure"] >= 4:
            raise RuntimeError("resource stop: critical memory pressure")
        return row


class AsyncDemoMonitor(DemoMonitor):
    """Keep identical resource limits; never run system CLI polling on input ACKs."""

    def __init__(self, out):
        super().__init__(out)
        self.worker = None
        self.error = None
        self.worker_started = None
        self.latest = None

    def check_error(self):
        if self.error is not None:
            raise RuntimeError(
                "demo resource monitor failed: " + str(self.error)
            ) from self.error
        if (
            self.worker
            and self.worker.is_alive()
            and time.monotonic() - self.worker_started > 5
        ):
            raise RuntimeError("demo resource monitor stale for5s; stop owned room")

    def sample(self, hosts):
        self.check_error()
        if self.worker and self.worker.is_alive():
            return self.latest
        snapshot = list(hosts)

        def collect():
            try:
                self.latest = super(AsyncDemoMonitor, self).sample(snapshot)
            except BaseException as error:
                self.error = error

        self.worker_started = time.monotonic()
        self.worker = threading.Thread(target=collect, name="demo-resource-guard")
        self.worker.start()
        return self.latest

    def finish(self):
        if self.worker:
            self.worker.join(timeout=50)
            if self.worker.is_alive():
                raise RuntimeError("owned resource monitor did not finish")
        self.check_error()


class DemoSession(NativeSession):
    def __init__(
        self,
        *,
        demo_resolution=None,
        demo_present_link=1,
        demo_cancel=None,
        demo_predicate="strict",
        demo_warm_session=None,
        demo_native_survey=False,
        demo_ink_every=0,
        demo_warm_chain=(),
        **kwargs,
    ):
        self.demo_cancel = demo_cancel
        self.demo_resolution = demo_resolution
        self.demo_present_link = demo_present_link
        self.demo_predicate = demo_predicate
        self.demo_warm_session = demo_warm_session
        self.demo_native_survey = demo_native_survey
        self.demo_ink_every = demo_ink_every
        self.demo_warm_chain = demo_warm_chain
        super().__init__(**kwargs)
        self.monitor = AsyncDemoMonitor(self.out)

    def tick(self, sleep=True):
        if self.demo_cancel and self.demo_cancel():
            raise InterruptedError("demo cancelled during startup")
        super().tick(sleep=sleep)
        self.monitor.check_error()
        if not hasattr(self, "demo_progress"):
            self.demo_progress = {}
        now = time.monotonic()
        for n, p, d in self.hosts:
            f = self.frame(n)
            old, stamp = self.demo_progress.get(n, (f, now))
            if f != old:
                self.demo_progress[n] = (f, now)
            else:
                self.demo_progress.setdefault(n, (f, now))
                if now - stamp > 60:
                    raise TimeoutError(
                        f"demo native startup/progress stalled player{n} at resource frame{f} for60s; preserve artifacts, only close owned room"
                    )

    def close(self):
        try:
            if isinstance(self.monitor, AsyncDemoMonitor):
                self.monitor.finish()
        finally:
            super().close()

    def host_options(self, n):
        warm = {}
        if self.demo_native_survey:
            warm["DM_DEMO_NATIVE_CAPTURE"] = "1"
            if n == 0:
                for folder, key in [
                    ("ink-targets", "DM_DEMO_INK_DIR"),
                    ("screenshots", "DM_DEMO_SHOT_DIR"),
                ]:
                    path = self.out / f"player-{n}" / folder
                    path.mkdir(parents=True, exist_ok=True)
                    warm[key] = str(path)
                warm["DM_NVN_SHOT_OUT"] = "1280x720"
        if self.demo_ink_every and n == 0:
            path = self.out / "player-0/ink-targets"
            path.mkdir(parents=True, exist_ok=True)
            warm.update(
                DM_DEMO_INK_DIR=str(path), DM_DEMO_INK_EVERY=str(self.demo_ink_every)
            )
        if self.demo_warm_session:
            seed = ROOT / "upstream/dm/games/0100C2500FC20000/pso_manifest.tsv"
            lines = seed.read_text().splitlines()
            for session in self.demo_warm_chain or (self.demo_warm_session,):
                for name in (f"warm-{n}.tsv", f"player-{n}/pso_user.tsv"):
                    file = session / name
                    if file.is_file():
                        lines.extend(file.read_text().splitlines())
            path = self.out / f"warm-{n}.tsv"
            path.write_text("\n".join(dict.fromkeys(lines)) + "\n")
            warm["DM_PSO_MANIFEST"] = str(path)
        return (
            super().host_options(n)
            | warm
            | ({"DM_GAME_RES": self.demo_resolution} if self.demo_resolution else {})
            | dict(
                DM_TEST_DEMO="1",
                DM_DEMO_PREDICATE=self.demo_predicate,
                DM_R0_CAMERA_PLUS5="1",
                DM_D2B_SENSOR="1",
                DM_HEADLESS="0" if n == 0 else "1",
                DM_WINDOW="1",
                DM_RL_PIXELS="0",
                DM_HID_TRACE="0",
                DM_PRESENT_LINK=str(self.demo_present_link),
                DM_NVN_TSV=str(self.out / f"player-{n}/nvn.tsv"),
                DM_NVN_PROF="1",
                DM_NVN_TSV_CALLS="0",
            )
        )


def scripted(frame, pattern="legacy"):
    a = neutral()
    if pattern == "calibration" and 180 <= frame < 1080:
        block, offset = divmod(frame - 360, 60)
        if 0 <= block < 10 and offset < 50:
            axis = block // 2
            value = 1 if block % 2 == 0 else -1
            if axis < 2:
                a["sticks"][2 + axis] = value * 0.4
            else:
                a["gyro"][axis - 2] = value * 0.04
        return a
    # Synthetic measurement schedule, never label it a human demonstration.
    if frame < 180:
        a["buttons"][0] = int(frame % 60 == 0)  # native respawn-launch input
    elif frame < 300:
        a["sticks"][2] = 0.5
    elif frame < 420:
        a["gyro"][2] = 0.06
    elif frame < 540:
        a["gyro"][0] = 0.06
    elif frame < 660:
        a["gyro"][1] = 0.06
    elif frame < 720:
        pass
    else:
        a["sticks"][1] = 0.65 if frame % 720 < 300 else 0
        a["sticks"][2] = 0.12 if frame % 720 < 300 else 0
        a["buttons"][0] = int(frame % 60 < 23)
        a["buttons"][1] = int(frame % 720 >= 480)
        a["buttons"][4] = int(frame % 180 == 0)
    return a


def as_native(a):
    return {
        k: np.asarray(v, dtype=np.int8 if k == "buttons" else np.float32)
        for k, v in a.items()
    }


def summary(infos, origins):
    return dict(
        remaining_time={
            p: i.get("remaining_time") if i.get("time_valid") else None
            for p, i in infos.items()
        },
        score_by_role={
            p: i.get("score") if i.get("score_valid") else None
            for p, i in infos.items()
        },
        turf_ratio_by_role={
            p: i.get("turf_ratio") if i.get("turf_valid") else None
            for p, i in infos.items()
        },
        hud_downs={p: i.get("hud_downs") for p, i in infos.items()},
        kd_semantics="HUD downs include environmental splats; personal weapon kills require event attribution",
        frames_by_role={p: i["frame"] - origins[p]["frame"] for p, i in infos.items()},
    )


def trace(barriers, actions, out):
    origins = barriers[0]["infos"]
    players = []
    for n, name in enumerate(["alpha", "bravo"]):
        p = f"player_{n}"
        states = []
        views = []
        events = []
        oldhp = None
        oldalive = None
        previous = [0] * 6
        for row in barriers:
            i = row["infos"][p]
            frame = row["frame"]
            samp = i.get("position_sample_frame", i["frame"]) - origins[p]["frame"]
            if i.get("position_valid"):
                motion = i.get("referee_motion", {})
                form = (
                    "submerged"
                    if motion.get("form_squid") == 1
                    and motion.get("ground_contact") == 0
                    else "squid"
                    if motion.get("form_squid") == 1
                    else "human"
                )
                states.append(
                    [
                        frame,
                        samp,
                        *i["position"],
                        i.get("heading", 0),
                        form,
                        i.get("hp") if i.get("hp_valid") else None,
                        bool(i.get("alive")),
                        i.get("ink") if i.get("ink_valid") else None,
                    ]
                )
            if i.get("own_view", {}).get("valid"):
                views.append([frame, i["own_view"]["yaw"], i["own_view"]["pitch"]])
            if oldhp is not None and i.get("hp_valid") and i["hp"] < oldhp:
                events.append(
                    dict(
                        frame=frame,
                        type="damage",
                        amount=(oldhp - i["hp"]) * 100,
                        evidence="native_sample_bound",
                    )
                )
            if oldalive and i.get("alive_valid") and not i["alive"]:
                events.append(
                    dict(
                        frame=frame,
                        type="down",
                        evidence="native_hud",
                        cause="unattributed",
                    )
                )
            if i.get("hp_valid"):
                oldhp = i["hp"]
            if i.get("alive_valid"):
                oldalive = i["alive"]
        for row in actions:
            b = row["actions"][p]["buttons"]
            for j, key in enumerate(["ZR", "ZL", "R", "RS", "B", "Y"]):
                if b[j] != previous[j]:
                    events.append(
                        dict(
                            frame=row["frame_interval"][0],
                            type=key + ("_down" if b[j] else "_release"),
                            evidence="recorded_input",
                        )
                    )
            previous = b
        players.append(dict(id=name, role=p, states=states, views=views, events=events))
    data = dict(
        schema="inklab.trace.v1",
        id="rl-demo-" + out.name,
        label="RL示范录制夹具（非训练）",
        source_kind="native_recording",
        map="Yunohana",
        fps=60,
        start_frame=0,
        end_frame=barriers[-1]["frame"],
        stride=1,
        columns=[
            "frame",
            "sample_frame",
            "x",
            "y",
            "z",
            "heading",
            "form",
            "hp",
            "alive",
            "ink",
        ],
        players=players,
        position_semantics="Native per-present ACK; original sample_frame/validity retained, not necessarily fresh state each present.",
    )
    write(out / "trace.json", data)


def run(a):
    if not a.fixture:
        raise ValueError(
            "explicit --fixture required; formal arena/T1 cannot use this host"
        )
    if any(
        os.environ.get(k)
        for k in ["DM_TEST_AIM", "DM_TEST_AIM_FILE", "DM_TEST_SPECIAL"]
    ):
        raise ValueError("demo forbids aim/meter cheats")
    host, modules = validate_runtime(a.host, a.modules, allow_demo=True)
    manifest = json.loads(host.with_suffix(".build.json").read_text())
    predicate = getattr(a, "render_predicate", "strict")
    if predicate not in ("strict", "async", "always"):
        raise ValueError("unknown demo render predicate mode")
    if predicate != "strict" and not manifest.get("predicate_experiment"):
        raise ValueError("render predicate variants require isolated build_render host")
    native_survey = getattr(a, "native_survey", False)
    if native_survey and not manifest.get("native_capture_survey"):
        raise ValueError("native survey requires isolated build_capture host")
    ink_every = getattr(a, "ink_every", 0)
    if ink_every and (
        not 15 <= ink_every <= 3600 or not manifest.get("periodic_ink_async")
    ):
        raise ValueError(
            "periodic ink requires isolated async host and 15..3600 frames"
        )
    catchup_frames = getattr(a, "max_catchup_frames", 6)
    if catchup_frames < 0:
        raise ValueError("max catchup frames must be nonnegative")
    warm_from = getattr(a, "warm_from", None)
    warm_session = None
    warm_chain = []
    if warm_from:
        warm_from = safe_out(warm_from)
        warm_session = Path(
            json.loads((warm_from / "result.json").read_text())["session"]
        )
        ancestor = warm_from
        seen = set()
        while ancestor:
            if ancestor in seen:
                raise ValueError("cyclic warm inheritance")
            seen.add(ancestor)
            prior = json.loads((ancestor / "result.json").read_text())
            warm_chain.append(Path(prior["session"]))
            ancestor = safe_out(prior["warm_from"]) if prior.get("warm_from") else None
            if len(seen) > 100:
                raise ValueError("invalid cyclic/oversized warm inheritance")
    if (
        manifest.get("test_feature") != "demonstration_capture"
        or manifest.get("render_mode") != "none"
        or manifest.get("direct_aim") is not False
    ):
        raise ValueError("full-render recording build required")
    if a.source == "controller" and not a.allow_unqualified:
        raise ValueError(
            "Human recording is not qualified yet: realtime60/physical gyro axes/dense paint remain unverified. Use --allow-unqualified only for explicit diagnostic capture; see notes/rl-demo-20261023.md."
        )
    direction_check = bool(getattr(a, "direction_check", False))
    if direction_check:
        if a.source != "controller" or not getattr(a, "controller_profile", None):
            raise ValueError("--direction-check requires controller source and explicit --controller-profile")
        if a.max_frames is None:
            a.max_frames = 3600
    out = safe_out(a.out)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    fixture_path = getattr(a, "fixture_inputs", None)
    fixture_inputs = None
    if fixture_path:
        if a.source != "script":
            raise ValueError(
                "fixed-input replay is a script fixture, not human capture"
            )
        fixture_path = safe_out(fixture_path)
        fixture_inputs = [
            json.loads(line)["actions"]
            for line in fixture_path.read_text().splitlines()
        ]
    stop = False

    def stopping(*_):
        nonlocal stop
        stop = True

    old = signal.signal(signal.SIGINT, stopping)
    old_term = signal.signal(signal.SIGTERM, stopping)
    controller = None
    direction_monitor = None
    child = None
    env = None
    barriers = []
    inputs = []
    times = []
    sample_ages = []
    start = time.monotonic()
    controlled = None
    result = dict(
        schema="inklab.rl.demo.v1",
        passed=False,
        complete=False,
        ready_for_human_demonstration=False,
        ready_for_bc=False,
        passed_scope="native capture/settlement loop only; not realtime60 or BC quality",
        source="scripted_smoke" if a.source == "script" else "human_USB",
        script_pattern=getattr(a, "script_pattern", "legacy")
        if a.source == "script"
        else None,
        stage=1,
        map="Yunohana",
        mode="turf",
        loadout_mode=a.loadout,
        opponent=a.opponent,
        decision_frames=1,
        frames=0,
        host_sha256=hashlib.sha256(host.read_bytes()).hexdigest(),
        host=str(host),
        render_resolution="1280x720 native output; alternative scale is unverified",
        requested_render_resolution=a.resolution,
        present_link=a.present_link,
        max_catchup_frames=catchup_frames,
        render_predicate=predicate,
        native_survey=native_survey,
        ink_every_frames=ink_every,
        warm_from=str(warm_from) if warm_from else None,
        errors=[],
        artifacts=str(out),
        measurement_limits=[
            "Periodic exact-frame ink is qualified only in verified ground panels; walls/ambiguous/missing ticks remain masked."
            if ink_every
            else "No native world paint readback; final turf is native, dense paint is reconstructed and flagged unknown.",
            "ACK/sample frames do not imply fresh per-present physics state.",
            "Weapon/projectile sensor candidates retain raw evidence; unqualified fields are not silently promoted.",
        ],
    )
    result["source_sha256"] = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in Path(__file__).parent.glob("*.py")
    }
    write(out / "result.json", result)
    if fixture_inputs is not None:
        result["fixed_input_fixture"] = str(fixture_path)
        result["fixed_input_sha256"] = hashlib.sha256(
            fixture_path.read_bytes()
        ).hexdigest()
    streams = {
        name: (out / name).open("w")
        for name in [
            "inputs-per-present.jsonl",
            "native-barriers.jsonl",
            "usb-inputs.jsonl",
            "timing.jsonl",
        ]
    }

    def append(name, row):
        streams[name].write(json.dumps(row, separators=(",", ":")) + "\n")

    try:
        if a.source == "controller":
            from .controller import Controller

            controller = Controller(profile=getattr(a, "controller_profile", None),
                                    allow_direction_check=direction_check)
            result["controller"] = controller.device
            if direction_check:
                from .controller_recheck import DirectionMonitor

                direction_monitor = DirectionMonitor()
                result["direction_check_only"] = True
                print("方向短测：窗口内先按ZR从出生点发射，再水平左右转/抬头低头。"
                      "终端每0.25秒提示输入方向及原生镜头变化；请看画面核对。"
                      "Minus/Plus未确认时用Ctrl-C或输出目录STOP文件结束；默认最多3600帧。", flush=True)
        spec = PolicySpec.load(a.policy) if a.opponent == "policy" else None
        opponent_stride = a.opponent_stride or (spec.step_frames if spec else 6)
        if opponent_stride < 1:
            raise ValueError("opponent stride must be positive")
        result["opponent_stride"] = opponent_stride
        if spec:
            child = ControlProcess(
                spec.root, out / "opponent.stderr.log", timeout=spec.step_timeout
            )
            result["opponent_source_sha256"] = spec.source_sha256
        weapons = [8000, 8000 if spec else 50]
        result["weapons"] = weapons
        env = DemoEnv(
            players=2,
            stage_id=1,
            mode=0,
            weapons=weapons,
            frame_skip=1,
            pixels=False,
            reward_fn=None,
            timeout=a.timeout,
            state_dump=False,
            clock_mode="fixed60",
            loadouts=[uniform_loadout(), spec.loadout if spec else uniform_loadout()],
            patched=modules,
            session_factory=partial(
                DemoSession,
                host=host,
                demo_resolution=a.resolution,
                demo_present_link=a.present_link,
                demo_predicate=predicate,
                demo_warm_session=warm_session,
                demo_warm_chain=warm_chain,
                demo_native_survey=native_survey,
                demo_ink_every=ink_every,
                demo_cancel=lambda: stop or (out / "STOP").exists(),
            ),
        )
        _, origins = env.reset()
        result["session"] = str(env.session.out)
        result["owned_pids"] = [p.pid for _, p, _ in env.session.hosts]
        write(out / "result.json", result)
        result["origins"] = origins
        api = RefereeAPI(
            out.name,
            origins,
            dict(zip(env.possible_agents, weapons)),
            dict(zip(env.possible_agents, [0, 1])),
            ROOT / "work/arena/maps/Yunohana/sight.npz",
            stage_id=1,
        )
        skills = Skills(MapAtlas.load(1))
        opponent = neutral()
        last_policy = -1000
        row = dict(frame=0, infos=origins)
        barriers.append(row)
        append("native-barriers.jsonl", row)
        controlled = time.monotonic()
        deadline = controlled
        for frame in range(20000):
            if stop or (out / "STOP").exists():
                result["cancelled"] = True
                break
            before = time.monotonic_ns()
            if controller:
                raw = controller.sample()
                control = {k: raw[k] for k in ["sticks", "gyro", "buttons"]}
                sample_ages.append((before - raw["sample_monotonic_ns"]) / 1e6)
                append("usb-inputs.jsonl", dict(frame=frame, **raw))
                if raw["physical_buttons"].get("Minus") and raw["physical_buttons"].get("Plus"):
                    result["cancelled"] = True
                    break  # Minus+Plus
            else:
                control = scripted(frame, getattr(a, "script_pattern", "legacy"))
            if a.loadout == "primary_only":
                control["buttons"][2:4] = [0, 0]
            battle = all(i["phase"] == 1 for i in env.process_infos.values())
            if not battle:
                control = neutral()
                opponent = neutral()
            if (
                battle
                and fixture_inputs is None
                and frame - last_policy >= opponent_stride
            ):
                api.update(env.process_infos)
                obs = api.policy_observation("player_1")
                if child:
                    opponent = child.act(
                        obs,
                        own_special(
                            env.process_infos["player_1"],
                            "player_1",
                            origins["player_1"]["frame"],
                        ),
                    )
                else:
                    from arena.policy import encode_policy

                    view = json.loads(encode_policy(obs))
                    own = view["own"]
                    enemies = view.get("enemies", [])
                    opponent = neutral()
                    visible = [e for e in enemies if e.get("position") is not None]
                    if visible:
                        enemy = visible[0]
                        target = list(enemy["position"])
                        target[1] += 1
                        opponent = aim_at(view, target).action
                        distance = (
                            np.linalg.norm(
                                np.asarray(target) - np.asarray(own["position"])
                            )
                            if own.get("position") is not None
                            else 100
                        )
                        opponent["buttons"][0] = int(distance <= 14)
                    else:
                        r = skills.move_to(view, skills.atlas.objective())
                        opponent = r.action
                last_policy = frame
            own_info = env.process_infos["player_1"]
            if battle and (
                frame < 180
                or (own_info.get("position_valid") and own_info["position"][1] > 20)
            ):
                skills = Skills(
                    skills.atlas
                )  # do not retain failed navigation from the ignored launch window
                opponent = neutral()
                opponent["buttons"][0] = int(frame % 30 == 0)
            if a.loadout == "primary_only":
                opponent["buttons"][2:4] = [0, 0]
            acts = {"player_0": control, "player_1": opponent}
            if fixture_inputs is not None:
                if frame >= len(fixture_inputs):
                    if battle:
                        raise ValueError(
                            "fixed-input corpus shorter than requested battle"
                        )
                    acts = {p: neutral() for p in env.possible_agents}
                    result["post_fixture_neutral_frames"] = (
                        result.get("post_fixture_neutral_frames", 0) + 1
                    )
                else:
                    acts = fixture_inputs[frame]
            send = time.monotonic_ns()
            if env.agents:
                _, _, _, trunc, info = env.step(
                    {p: as_native(acts[p]) for p in env.agents}
                )
                if any(trunc.values()):
                    raise TimeoutError("native session timed out")
            else:
                _, info = env.advance_settlement()
            info = env.process_infos  # PettingZoo returns active agents only; retain both native peers through settlement
            ack = time.monotonic_ns()
            if direction_monitor:
                direction_monitor.update(raw, info["player_0"])
            times.append((ack - send) / 1e6)
            interval = dict(
                frame_interval=[frame, frame + 1],
                actions=acts,
                request_monotonic_ns=send,
            )
            inputs.append(interval)
            append("inputs-per-present.jsonl", interval)
            row = dict(frame=frame + 1, infos=info)
            barriers.append(row)
            append("native-barriers.jsonl", row)
            append(
                "timing.jsonl",
                dict(frame=frame + 1, send_ns=send, ack_ns=ack, sample_ns=before),
            )
            result["frames"] = frame + 1
            if frame % 120 == 0:
                write(
                    out / "progress.json",
                    dict(
                        frame=frame + 1,
                        controlled_wall_seconds=time.monotonic() - controlled,
                        phase={p: i["phase"] for p, i in info.items()},
                    ),
                )
                for s in streams.values():
                    s.flush()
            if all(i["phase"] == 3 for i in info.values()):
                result["complete"] = True
                break
            if a.max_frames and frame + 1 >= a.max_frames:
                result["truncated_smoke"] = True
                break
            deadline += 1 / 60
            if a.pace and (wait := deadline - time.monotonic()) > 0:
                time.sleep(wait)
            # Do not burst old inputs to recover a long stall.
            if time.monotonic() - deadline > catchup_frames / 60:
                deadline = time.monotonic()
        result.update(summary(env.process_infos, origins))
        result["passed"] = result["complete"] and not result.get("cancelled")
    except BaseException as ex:
        result["errors"].append(repr(ex))
        result["traceback"] = traceback.format_exc()
    finally:
        if controlled:
            result["controlled_wall_seconds"] = time.monotonic() - controlled
            result["controlled_presents_per_second"] = (
                result["frames"] / result["controlled_wall_seconds"]
            )
        if env:
            if env.artifacts:
                result["native_artifacts"] = [str(p) for p in env.artifacts]
            try:
                env.close()
            except BaseException as ex:
                result["errors"].append("close: " + repr(ex))
                result["passed"] = False
        if barriers:
            try:
                trace(barriers, inputs, out)
            except BaseException as ex:
                result["errors"].append("trace: " + repr(ex))
                result["passed"] = False
        if child:
            child.close()
        if controller:
            controller.close()
        for s in streams.values():
            s.flush()
            os.fsync(s.fileno())
            s.close()
        signal.signal(signal.SIGINT, old)
        signal.signal(signal.SIGTERM, old_term)
        result["wall_seconds"] = time.monotonic() - start
        result["ack_latency_ms"] = (
            {
                k: float(v)
                for k, v in zip(
                    ["p50", "p95", "max"], np.percentile(times, [50, 95, 100])
                )
            }
            if times
            else None
        )
        result["latency_scope"] = (
            "command-send to per-present native ACK; display callback independently in host.log, not photon latency"
        )
        write(out / "result.json", result)
    if result.get("complete") and Path(result.get("session", "missing")).is_dir():
        try:
            from .telemetry import reduce

            reduce(out)
            if getattr(a, "native_survey", False):
                from .native_survey import reduce as survey

                survey(out)
        except BaseException as ex:
            result["postprocess_error"] = repr(ex)
            write(out / "result.json", result)
    if ink_every and manifest.get("periodic_ink_panels") and barriers:
        try:
            from .periodic_ink import normalize

            normalize(out)
        except Exception as ex:
            result["ink_postprocess_error"] = repr(ex)
            write(out / "result.json", result)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ["origins", "source_sha256"]},
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return (
        0
        if result["passed"] or (result.get("truncated_smoke") and not result["errors"])
        else 1
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture", action="store_true")
    p.add_argument(
        "--allow-unqualified",
        action="store_true",
        help="explicit diagnostic only; does not certify realtime60 or BC observations",
    )
    p.add_argument(
        "--host", type=Path, default=ROOT / "work/rl-demo/host-r5/dmhost-demo"
    )
    p.add_argument(
        "--modules", type=Path, default=ROOT / "work/rl-demo/host-r5/modules"
    )
    p.add_argument("--out", required=True)
    p.add_argument("--source", choices=["controller", "script"], default="controller")
    p.add_argument("--controller-profile", type=Path, help="private profile.json from guided USB controller check")
    p.add_argument("--direction-check", action="store_true", help="human in-game gyro visual check; permits explicitly scoped SDL-assumption profile, prints directions; defaults to3600 frames")
    p.add_argument("--opponent", choices=["52", "policy"], default="52")
    p.add_argument("--policy", default="arena/policies/alpha")
    p.add_argument(
        "--opponent-stride",
        type=int,
        help="default: policy config cadence, or6 for .52 script",
    )
    p.add_argument(
        "--loadout", choices=["primary_only", "full"], default="primary_only"
    )
    p.add_argument(
        "--resolution",
        help="diagnostic DM_GAME_RES request only; not confirmed effective for Splatoon",
    )
    p.add_argument("--present-link", type=int, choices=[0, 1, 2], default=1)
    p.add_argument(
        "--render-predicate", choices=["strict", "async", "always"], default="strict"
    )
    p.add_argument(
        "--warm-from",
        type=Path,
        help="private prior recording whose per-role PSO lists are copied into a new warm manifest",
    )
    p.add_argument(
        "--fixture-inputs",
        type=Path,
        help="private fixed per-present script inputs, never human demonstration",
    )
    p.add_argument(
        "--ink-every",
        type=int,
        default=0,
        help="async 1600-square native ink period, isolated periodic host only; 0 disables",
    )
    p.add_argument("--timeout", type=float, default=1800)
    p.add_argument("--max-frames", type=int)
    p.add_argument(
        "--native-survey",
        action="store_true",
        help="private passive field/paint survey; extra readback may stall rendering",
    )
    p.add_argument(
        "--script-pattern", choices=["legacy", "calibration"], default="legacy"
    )
    p.add_argument("--pace", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument(
        "--max-catchup-frames",
        type=int,
        default=6,
        help="wall-clock backlog cap; never changes fixed60 game ticks",
    )
    raise SystemExit(run(p.parse_args()))
