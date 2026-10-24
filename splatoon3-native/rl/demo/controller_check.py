"""Guided physical-label calibration; pure reducers also work without SDL/hardware."""

import json
import math
import statistics
import time
from pathlib import Path


GAME_BUTTONS = ("ZR", "ZL", "R", "RS", "B", "Y")
DEFAULT_BINDINGS = {
    "ZR": ["axis", 5],
    "ZL": ["axis", 4],
    "A": ["button", 0],
    "B": ["button", 1],
    "X": ["button", 2],
    "Y": ["button", 3],
    "Minus": ["button", 4],
    "Home": ["button", 5],
    "Plus": ["button", 6],
    "LS": ["button", 7],
    "RS": ["button", 8],
    "L": ["button", 9],
    "R": ["button", 10],
    "Up": ["button", 11],
    "Down": ["button", 12],
    "Left": ["button", 13],
    "Right": ["button", 14],
    "Capture": ["button", 15],
}
BUTTON_LABELS = {
    "ZR": "ZR（右后扳机，开火）",
    "ZL": "ZL（左后扳机，潜墨）",
    "B": "印字 B（下面，跳跃）",
    "R": "R（右肩，副武器/出钩）",
    "A": "印字 A（右面）",
    "X": "印字 X（上面）",
    "Y": "印字 Y（左面）",
    "L": "L（左肩）",
    "RS": "右摇杆按下（RS，大招）",
    "LS": "左摇杆按下（LS）",
    "Minus": "−（Minus）",
    "Plus": "+（Plus）",
    "Up": "十字键 上",
    "Down": "十字键 下",
    "Left": "十字键 左",
    "Right": "十字键 右",
    "Capture": "截图键（小方键）",
    "Home": "HOME（小圆键）",
}


def radial_sticks(raw, centers=(0, 0, 0, 0), deadzone=0.15):
    """Recenter each axis, retain full throw, then radial deadzone per stick."""
    out = []
    for off in (0, 2):
        xy = [
            (raw[i] - centers[i])
            / max(0.01, 1 - math.copysign(1, raw[i] - centers[i]) * centers[i])
            for i in (off, off + 1)
        ]
        radius = math.hypot(*xy)
        scale = (
            min(1, (radius - deadzone) / (1 - deadzone)) / radius
            if radius > deadzone
            else 0
        )
        out.extend(v * scale for v in xy)
    return out


def active_channels(row, edges=False):
    """Triggers are axes, NOT SDL buttons. Joystick fallbacks stay separately named."""
    found = set()
    for i, value in enumerate(row.get("controller_axes", [])):
        if i >= 4 and value > 16383:
            found.add(("axis", i))
    for kind, field in (("button", "all_buttons"), ("joy_button", "joystick_buttons")):
        found.update((kind, i) for i, v in enumerate(row.get(field, [])) if v)
    if edges:
        for e in row.get("button_events", []):
            if e["type"] == "axis" and e["index"] >= 4 and e["value"] > 16383:
                found.add(("axis", e["index"]))
            elif e["type"] in ("button", "joy_button") and e.get("down"):
                found.add((e["type"], e["index"]))
    return found


def resolve_binding(channels):
    """Prefer one controller binding; raw joystick is a diagnosed fallback, not OR'd."""
    primary = sorted(v for v in channels if v[0] != "joy_button")
    candidates = primary or sorted(channels)
    return list(candidates[0]) if len(candidates) == 1 else None


def mapped_buttons(row, bindings):
    active = active_channels(row, edges=True)
    return {label: int(tuple(binding) in active) for label, binding in bindings.items()}


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * q))] if values else 0


def baseline_report(rows):
    rows = [r for r in rows if r.get("sensor_timestamp_us")]
    if len(rows) < 20:
        raise ValueError("有效静置样本不足；检查 USB/IMU 后重跑")
    centers = [statistics.median(r["raw_sticks"][i] for r in rows) for i in range(4)]
    bias = [statistics.median(r["gyro_rad_s"][i] for r in rows) for i in range(3)]
    radius = [
        percentile([math.hypot(*r["raw_sticks"][j : j + 2]) for r in rows], 0.99)
        for j in (0, 2)
    ]
    noise = [
        percentile(
            [
                math.hypot(*(r["raw_sticks"][i] - centers[i] for i in (j, j + 1)))
                for r in rows
            ],
            0.99,
        )
        for j in (0, 2)
    ]
    gyro_noise = [
        percentile([abs(r["gyro_rad_s"][i] - bias[i]) for r in rows], 0.99)
        for i in range(3)
    ]
    recommended = max(0.15, max(radius) + 0.03)
    return dict(
        centers=centers,
        gyro_bias_rad_s=bias,
        raw_radius_p99=radius,
        centered_noise_radius_p99=noise,
        recommended_uncentered_deadzone=recommended,
        gyro_noise_p99_rad_s=gyro_noise,
        deadzone=min(0.45, max(0.15, max(noise) + 0.03)),
        stable=max(noise) < 0.06
        and max(gyro_noise) < 0.15
        and max(abs(v) for v in bias) < 0.15
        and max(abs(v) for v in centers) < 0.35,
    )


def gyro_gesture(rows, bias, threshold=0.35, expected_axis=None):
    """Lock the FIRST threshold crossing; never relabel a return/larger later motion.

    Require a dominant, same-sign 30ms onset. Mixed-axis onset is a failed
    attempt, not permission to scan ahead until the desired answer appears.
    """
    events = {}
    for r in rows:
        for e in r.get("sensor_events", []):
            if e["timestamp_us"]:
                events[e["timestamp_us"]] = e["gyro_rad_s"]
        if r.get("sensor_timestamp_us"):
            events.setdefault(r["sensor_timestamp_us"], r["gyro_rad_s"])
    samples = [(t, [x - b for x, b in zip(v, bias)]) for t, v in sorted(events.items())]
    first = next(((t, v) for t, v in samples if max(map(abs, v)) >= threshold), None)
    if first is None:
        return dict(
            valid=False, pending=True, reason="no_onset", sensor_updates=len(samples)
        )
    stamp, vector = first
    axis = max(range(3), key=lambda i: abs(vector[i]))
    sign = 1 if vector[axis] > 0 else -1
    result = dict(
        valid=False,
        pending=False,
        axis=axis,
        sign=sign,
        method="first_threshold_onset_v1",
        threshold_rad_s=threshold,
        onset_timestamp_us=stamp,
        onset_vector_rad_s=vector,
        onset_offset_seconds=(stamp - samples[0][0]) / 1e6,
        sensor_updates=len(samples),
    )
    if expected_axis is not None and axis != expected_axis:
        return dict(result, reason="unexpected_axis")
    if abs(vector[axis]) < 1.8 * max(abs(vector[i]) for i in range(3) if i != axis):
        return dict(result, reason="mixed_axis_onset")
    if samples[-1][0] < stamp + 30000:
        return dict(result, pending=True, reason="onset_debounce")
    window = [(t, v) for t, v in samples if stamp <= t <= stamp + 30000]
    if len(window) < 5:
        return dict(result, reason="insufficient_fresh_updates")
    if any(v[axis] * sign < threshold * 0.5 for _, v in window):
        return dict(result, reason="onset_reversed_or_too_short")
    if any(
        abs(v[axis]) < 1.5 * max(abs(v[i]) for i in range(3) if i != axis)
        for _, v in window
    ):
        return dict(result, reason="mixed_axis_onset")
    return dict(result, valid=True, reason="first_onset_confirmed")


def gyro_mapping(results):
    """Native fixture: pitch up +X, yaw right +Y, roll right +Z (hle_hid.c)."""
    mapping = {}
    for name, positive, negative in (
        ("pitch", "up", "down"),
        ("yaw", "right", "left"),
        ("roll", "right", "left"),
    ):
        a, b = (results.get(f"gyro_{name}_{v}", {}) for v in (positive, negative))
        valid = (
            a.get("valid")
            and b.get("valid")
            and a["axis"] == b["axis"]
            and a["sign"] == -b["sign"]
        )
        mapping[name] = dict(valid=bool(valid), axis=a.get("axis"), sign=a.get("sign"))
    axes = [v["axis"] for v in mapping.values() if v["valid"]]
    if len(set(axes)) != len(axes):
        for v in mapping.values():
            v["valid"] = False
    return mapping


def validate_profile(profile, allow_direction_check=False):
    provisional = bool(
        allow_direction_check
        and profile.get("usable_for_direction_check")
        and profile.get("scope") == "direction_check_only"
    )
    if profile.get("schema") != "pro-controller-physical-v1" or not (
        profile.get("complete") or provisional
    ):
        raise ValueError("手柄校准未通过；先重跑引导式自检，不能使用不完整 profile")
    bindings = profile.get("bindings", {})
    if not set(GAME_BUTTONS).issubset(bindings) or not set(bindings).issubset(
        DEFAULT_BINDINGS
    ):
        raise ValueError("profile 缺少关键印字按键映射")
    values = []
    for kind, index in bindings.values():
        if (
            kind not in ("axis", "button", "joy_button")
            or type(index) is not int
            or index < 0
        ):
            raise ValueError("invalid controller binding")
        if kind == "axis" and index not in (4, 5):
            raise ValueError("trigger must map to SDL axis 4/5")
        values.append((kind, index))
    if len(set(values)) != len(values):
        raise ValueError("duplicate physical binding")
    centers = profile.get("centers", [])
    bias = profile.get("gyro_bias_rad_s", [])
    if (
        len(centers) != 4
        or any(not math.isfinite(x) or abs(x) >= 0.35 for x in centers)
        or len(bias) != 3
        or any(not math.isfinite(x) or abs(x) >= 0.15 for x in bias)
        or not 0.15 <= profile.get("deadzone", 0) <= 0.45
    ):
        raise ValueError("invalid baseline calibration")
    mapping = profile.get("gyro_mapping", {})
    if (
        set(mapping) != {"pitch", "yaw", "roll"}
        or not all(
            (
                v.get("valid")
                or (provisional and v.get("basis") == "SDL convention assumption")
            )
            and v.get("sign") in (-1, 1)
            for v in mapping.values()
        )
        or {v.get("axis") for v in mapping.values()} != {0, 1, 2}
    ):
        raise ValueError("gyro axes/signs are unconfirmed")
    return profile


def load_base_profile(path):
    path = Path(path).resolve()
    if "work" not in path.parts:
        raise ValueError("calibration profiles must stay in private work/")
    profile = json.loads(path.read_text())
    if profile.get("schema") != "pro-controller-physical-v1":
        raise ValueError("invalid base profile")
    summary = path.with_name("summary.json")
    if "stage_evidence" not in profile and summary.exists():
        saved = json.loads(summary.read_text())
        if saved.get("profile") != profile:
            raise ValueError("base profile and summary disagree")
        profile["stage_evidence"] = saved.get("stages", {})
    profile["profile_source"] = str(path)
    return profile


class GuidedCheck:
    def __init__(
        self,
        controller,
        out,
        timeout=12,
        baseline_seconds=3,
        emit=print,
        only="all",
        base_profile=None,
        gyro_threshold=0.35,
    ):
        self.c, self.out = controller, Path(out)
        self.timeout, self.baseline_seconds, self.emit = timeout, baseline_seconds, emit
        self.only, self.prior = only, base_profile or {}
        self.gyro_threshold = gyro_threshold
        if only != "all" and not base_profile:
            raise ValueError(
                "--only requires --base-profile to preserve the other checks"
            )
        if base_profile:
            if base_profile.get("schema") != "pro-controller-physical-v1":
                raise ValueError("invalid base profile schema")
            if any(
                base_profile["device"].get(k) != controller.device.get(k)
                for k in ("vendor", "product", "sdl_mapping", "sdl_revision")
            ):
                raise ValueError("base profile SDL/device mapping changed")
        self.results = {
            k: v
            for k, v in self.prior.get("stage_evidence", {}).items()
            if not k.startswith("gyro_" if only == "gyro" else "button_")
        }
        self.bindings = dict(self.prior.get("bindings", {})) if only == "gyro" else {}

    def read(self, stage):
        row = dict(self.c.sample(), check_stage=stage)
        self.stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def settle(self, stage, gyro=False):
        self.emit("  请松开所有按键、摇杆回中，手柄保持静止…", flush=True)
        start, quiet = time.monotonic(), None
        while time.monotonic() - start < self.timeout:
            r = self.read(stage + ":settle")
            neutral = not active_channels(r)
            neutral &= (
                max(abs(x - c) for x, c in zip(r["raw_sticks"], self.base["centers"]))
                < 0.15
            )
            if gyro:
                neutral &= (
                    max(
                        abs(x - b)
                        for x, b in zip(r["gyro_rad_s"], self.base["gyro_bias_rad_s"])
                    )
                    < 0.16
                )
            quiet = (quiet or time.monotonic()) if neutral else None
            if quiet and time.monotonic() - quiet >= 0.7:
                return True
            time.sleep(0.004)
        self.emit("  等待松开/静止超时，此项记为未确认。", flush=True)
        return False

    def measure(self, stage, prompt, detect, gyro=False):
        if not self.settle(stage, gyro=gyro):
            return dict(valid=False, reason="neutral_timeout")
        self.emit(
            f"\n▶ {prompt}（{self.timeout:g}秒内；检测后自动进入下一项）", flush=True
        )
        start, rows = time.monotonic(), []
        while time.monotonic() - start < self.timeout:
            rows.append(self.read(stage))
            result = detect(rows)
            if result:
                self.emit(
                    (
                        "  ✓ 已识别；现在可以回正。 "
                        if result.get("valid")
                        else "  ✗ 本次动作未确认。 "
                    )
                    + json.dumps(result, ensure_ascii=False),
                    flush=True,
                )
                return result
            time.sleep(0.004)
        self.emit("  ✗ 超时/方向不明确，记为未确认。", flush=True)
        return dict(valid=False, reason="input_timeout")

    def run(self):
        if "work" not in self.out.resolve().parts:
            raise ValueError("controller diagnostics must stay in private work/")
        self.out.mkdir(parents=True, exist_ok=False)
        self.emit(
            "引导式 USB Pro 自检：不启动游戏。按手柄印字操作。转到位后保持不动，等出现 ✓ 再回正。\n"
            "先把手柄平放，不碰摇杆/按键，采集中心与 IMU 零偏。Ctrl-C 可中止并保留原件。",
            flush=True,
        )
        with (self.out / "samples.jsonl").open("w") as self.stream:
            self.collect()
        profile = dict(
            schema="pro-controller-physical-v1",
            device=self.c.device,
            bindings=self.bindings,
            **self.base,
            gyro_mapping=(
                self.prior.get("gyro_mapping", {})
                if self.only == "buttons"
                else gyro_mapping(self.results)
            ),
            only=self.only,
            stage_evidence=self.results,
            inherited_from=self.prior.get("profile_source"),
            native_camera_validation="pending visual check; physical axes only",
        )
        buttons_ok = set(GAME_BUTTONS).issubset(self.bindings)
        stick_checks = [v for k, v in self.results.items() if k.startswith("stick_")]
        sticks_ok = len(stick_checks) == 8 and all(v["valid"] for v in stick_checks)
        profile["unconfirmed_buttons"] = sorted(
            set(DEFAULT_BINDINGS) - self.bindings.keys()
        )
        profile["all_buttons_confirmed"] = not profile["unconfirmed_buttons"]
        profile["stick_directions_verified"] = sticks_ok
        unique = len({tuple(v) for v in self.bindings.values()}) == len(self.bindings)
        profile["complete"] = bool(
            buttons_ok
            and unique
            and self.base["stable"]
            and sticks_ok
            and all(v["valid"] for v in profile["gyro_mapping"].values())
        )
        profile["stop_combo_enabled"] = {"Minus", "Plus"}.issubset(self.bindings)
        if profile["complete"]:
            validate_profile(profile)
        summary = dict(
            profile=profile,
            stages=self.results,
            button_bindings_unique=unique,
            **sensor_summary(self.out / "samples.jsonl"),
        )
        (self.out / "profile.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2) + "\n"
        )
        (self.out / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
        )
        table = report_markdown(summary)
        (self.out / "report.md").write_text(table)
        self.emit("\n" + table, flush=True)
        return summary

    def collect(self):
        start, rows = time.monotonic(), []
        # Warm-up first; SDL initial zero state must not calibrate the center.
        while time.monotonic() - start < 0.5:
            self.read("warmup")
            time.sleep(0.004)
        start = time.monotonic()
        while time.monotonic() - start < self.baseline_seconds:
            rows.append(self.read("baseline"))
            time.sleep(0.004)
        self.base = baseline_report(rows)
        self.c.calibration = dict(self.base, bindings=DEFAULT_BINDINGS)
        self.emit(
            "静置中心="
            + str(self.base["centers"])
            + "; 径向死区="
            + str(self.base["deadzone"]),
            flush=True,
        )
        if self.only in ("all", "buttons"):
            self.check_buttons()
        if self.only == "all":
            self.check_sticks()
        if self.only in ("all", "gyro"):
            self.check_gyro()

    def check_buttons(self):
        for label, prompt in BUTTON_LABELS.items():

            def detect(rows):
                channels = set().union(*(active_channels(r, edges=True) for r in rows))
                binding = resolve_binding(channels)
                if binding and len(rows) >= 12:
                    return dict(valid=True, binding=binding, observed=sorted(channels))

            result = self.measure(
                "button_" + label, "请按住 " + prompt + " 约半秒", detect
            )
            self.results["button_" + label] = result
            if result["valid"]:
                self.bindings[label] = result["binding"]

    def check_sticks(self):
        for name, axis, sign in (
            ("左摇杆左", 0, -1),
            ("左摇杆右", 0, 1),
            ("左摇杆上", 1, 1),
            ("左摇杆下", 1, -1),
            ("右摇杆左", 2, -1),
            ("右摇杆右", 2, 1),
            ("右摇杆上", 3, 1),
            ("右摇杆下", 3, -1),
        ):

            def detect(rows, axis=axis, sign=sign):
                values = [
                    x - c for x, c in zip(rows[-1]["raw_sticks"], self.base["centers"])
                ]
                if (
                    values[axis] * sign > 0.6
                    and max(range(4), key=lambda i: abs(values[i])) == axis
                ):
                    return dict(
                        valid=True, axis=axis, sign=sign, raw=rows[-1]["raw_sticks"]
                    )

            self.results["stick_" + name] = self.measure(
                "stick_" + name, "请将 " + name + " 推到底", detect
            )

    def check_gyro(self):
        for name, direction, text in (
            ("yaw", "left", "向左水平转动手柄（平放方向转弯，不侧倾）"),
            ("yaw", "right", "向右水平转动手柄（平放方向转弯，不侧倾）"),
            ("pitch", "up", "抬高手柄前沿（抬头，不侧倾）"),
            ("pitch", "down", "压低手柄前沿（低头，不侧倾）"),
            ("roll", "left", "向左侧倾手柄（左握把降低，右握把升高）"),
            ("roll", "right", "向右侧倾手柄（右握把降低，左握把升高）"),
        ):

            def detect(rows, name=name):
                result = gyro_gesture(
                    rows,
                    self.base["gyro_bias_rad_s"],
                    threshold=self.gyro_threshold,
                    expected_axis=dict(pitch=0, yaw=1, roll=2)[name],
                )
                return None if result.get("pending") else result

            stage = f"gyro_{name}_{direction}"
            self.results[stage] = self.measure(
                stage,
                "请从正常握姿 " + text + " 约30–60°；到位保持，等 ✓ 再回正",
                detect,
                gyro=True,
            )


def sensor_summary(path):
    stamps, latest, count = set(), set(), 0
    with Path(path).open() as source:
        for line in source:
            r = json.loads(line)
            count += 1
            if r.get("sensor_timestamp_us"):
                latest.add(r["sensor_timestamp_us"])
            stamps.update(
                e["timestamp_us"]
                for e in r.get("sensor_events", [])
                if e["timestamp_us"]
            )

    def rate(values):
        return (
            (len(values) - 1) * 1e6 / (max(values) - min(values))
            if len(values) > 1
            else 0
        )

    return dict(
        polls=count,
        sensor_event_count=len(stamps),
        sensor_event_hz=rate(stamps),
        observed_latest_hz=rate(latest),
        gyro_unit="rad/s; native uses turns/s = rad/s / (2π)",
    )


def report_markdown(summary):
    p = summary["profile"]
    lines = [
        "# 手柄印字映射 / 方向 / 漂移结论",
        "",
        "|按键（印字）|识别|实际 SDL 通道|",
        "|---|---|---|",
    ]
    for label in BUTTON_LABELS:
        binding = p["bindings"].get(label)
        duplicate = binding and list(p["bindings"].values()).count(binding) > 1
        state = "冲突" if duplicate else "通过" if binding else "未确认"
        lines.append(f"|{label}|{state}|{binding or '超时/歧义'}|")
    lines += ["", "|摇杆方向|识别|", "|---|---|"]
    for stage, result in summary["stages"].items():
        if stage.startswith("stick_"):
            lines.append(f"|{stage[6:]}|{'通过' if result['valid'] else '未确认'}|")
    lines += ["", "|物理转动|SDL 轴（正向动作）|反向一致|", "|---|---|---|"]
    for name, v in p["gyro_mapping"].items():
        desc = (
            ("xyz"[v["axis"]] + (" +" if v["sign"] > 0 else " −"))
            if v["valid"]
            else "未确认"
        )
        positive = dict(yaw="右转", pitch="抬头", roll="右倾")[name]
        lines.append(
            f"|{name}（{positive}为正）|{desc}|{'通过' if v['valid'] else '未确认'}|"
        )
    lines += [
        "",
        f"- 静置中心 LX/LY/RX/RY：{[round(x, 4) for x in p['centers']]}",
        f"- 未校中心建议径向死区 ≥ {p['recommended_uncentered_deadzone']:.3f}；校中心后采用 {p['deadzone']:.3f}。原始值和处理值均保留。",
        f"- 静置稳定：{p['stable']}；按键绑定唯一：{summary['button_bindings_unique']}。",
        f"- IMU 事件 {summary['sensor_event_hz']:.1f} Hz；最新状态 {summary['observed_latest_hz']:.1f} Hz（不是轮询率），单位 rad/s。",
        f"- 关键操作校准可用：{p['complete']}；未确认按键：{p.get('unconfirmed_buttons', [])}。",
        f"- Minus+Plus提前结束：{p.get('stop_combo_enabled', False)}；未确认时用STOP文件或Ctrl-C。",
        "- 原生画面方向仍需开录前短测确认。本工具不启动游戏。",
        "",
    ]
    return "\n".join(lines)
