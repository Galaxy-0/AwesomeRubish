"""SDL2 HIDAPI Switch Pro USB handshake/IMU diagnostic, no game required.

Units follow installed SDL_sensor.h: rad/s. Physical axes/signs are calibrated.
The native nn::hid fixture consumes turns/s; record both, never reuse rad/s as turns/s.
"""

import argparse
import ctypes as C
import ctypes.util
import json
import math
import struct
from pathlib import Path
import time

from .controller_check import (
    DEFAULT_BINDINGS,
    GAME_BUTTONS,
    GuidedCheck,
    mapped_buttons,
    radial_sticks,
    validate_profile,
    load_base_profile,
)


class Controller:
    def __init__(
        self, library=None, deadzone=0.15, profile=None, allow_direction_check=False
    ):
        if not 0 <= deadzone < 0.5:
            raise ValueError("extra deadzone must be in [0,.5)")
        self.deadzone = deadzone
        self.calibration = (
            validate_profile(
                json.loads(Path(profile).read_text()),
                allow_direction_check=allow_direction_check,
            )
            if profile
            else {}
        )
        path = (
            library
            or ctypes.util.find_library("SDL2")
            or "/opt/homebrew/lib/libSDL2.dylib"
        )
        self.lib = C.CDLL(path)
        self.handle = None
        self.closed = False

        def bind(name, result, *args):
            fn = getattr(self.lib, "SDL_" + name)
            fn.restype, fn.argtypes = result, list(args)
            return fn

        self.error = bind("GetError", C.c_char_p)
        bind("SetHint", C.c_int, C.c_char_p, C.c_char_p)
        for k, v in {
            "SDL_JOYSTICK_HIDAPI": "1",
            "SDL_JOYSTICK_HIDAPI_SWITCH": "1",
            "SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS": "1",
            "SDL_GAMECONTROLLER_USE_BUTTON_LABELS": "1",
            "SDL_JOYSTICK_MFI": "0",
        }.items():
            self.lib.SDL_SetHint(k.encode(), v.encode())
        bind("Init", C.c_int, C.c_uint32)
        bind("Quit", None)
        bind("NumJoysticks", C.c_int)
        bind("IsGameController", C.c_int, C.c_int)
        bind("GameControllerOpen", C.c_void_p, C.c_int)
        bind("GameControllerClose", None, C.c_void_p)
        bind("GameControllerName", C.c_char_p, C.c_void_p)
        bind("GameControllerGetVendor", C.c_uint16, C.c_void_p)
        bind("GameControllerGetProduct", C.c_uint16, C.c_void_p)
        bind("GameControllerHasSensor", C.c_int, C.c_void_p, C.c_int)
        bind("GameControllerSetSensorEnabled", C.c_int, C.c_void_p, C.c_int, C.c_int)
        bind("GameControllerGetSensorDataRate", C.c_float, C.c_void_p, C.c_int)
        bind(
            "GameControllerGetSensorDataWithTimestamp",
            C.c_int,
            C.c_void_p,
            C.c_int,
            C.POINTER(C.c_uint64),
            C.POINTER(C.c_float),
            C.c_int,
        )
        bind("GameControllerGetAxis", C.c_int16, C.c_void_p, C.c_int)
        bind("GameControllerGetButton", C.c_uint8, C.c_void_p, C.c_int)
        bind("GameControllerGetStringForButton", C.c_char_p, C.c_int)
        bind("GameControllerGetJoystick", C.c_void_p, C.c_void_p)
        bind("GameControllerMapping", C.c_void_p, C.c_void_p)
        bind("free", None, C.c_void_p)
        bind("GetRevision", C.c_char_p)
        bind("JoystickNumAxes", C.c_int, C.c_void_p)
        bind("JoystickNumButtons", C.c_int, C.c_void_p)
        bind("JoystickNumHats", C.c_int, C.c_void_p)
        bind("JoystickGetAxis", C.c_int16, C.c_void_p, C.c_int)
        bind("JoystickGetButton", C.c_uint8, C.c_void_p, C.c_int)
        bind("JoystickGetHat", C.c_uint8, C.c_void_p, C.c_int)
        bind("GameControllerGetAttached", C.c_int, C.c_void_p)
        bind("PollEvent", C.c_int, C.c_void_p)
        bind("GameControllerUpdate", None)
        if self.lib.SDL_Init(0x2000 | 0x200 | 0x4000):
            raise RuntimeError("SDL init: " + self.error().decode())
        self.devices = []
        for i in range(self.lib.SDL_NumJoysticks()):
            if not self.lib.SDL_IsGameController(i):
                continue
            h = self.lib.SDL_GameControllerOpen(i)
            if not h:
                continue
            vendor = self.lib.SDL_GameControllerGetVendor(h)
            product = self.lib.SDL_GameControllerGetProduct(h)
            row = dict(
                index=i,
                name=self.lib.SDL_GameControllerName(h).decode(),
                vendor=vendor,
                product=product,
                gyro=bool(self.lib.SDL_GameControllerHasSensor(h, 2)),
            )
            self.devices.append(row)
            if (vendor, product) == (0x057E, 0x2009) and self.handle is None:
                self.handle = h
                self.device = row
            else:
                self.lib.SDL_GameControllerClose(h)
        if not self.handle:
            self.close()
            raise RuntimeError(
                "Nintendo Pro 057e:2009 not accessible. Devices="
                + json.dumps(self.devices)
                + "; check USB and System Settings > Privacy & Security > Input Monitoring for the launching terminal/app, then restart it."
            )
        if not self.device["gyro"] or self.lib.SDL_GameControllerSetSensorEnabled(
            self.handle, 2, 1
        ):
            self.close()
            raise RuntimeError("Switch Pro IMU unavailable: " + self.error().decode())
        self.device["advertised_gyro_hz"] = float(
            self.lib.SDL_GameControllerGetSensorDataRate(self.handle, 2)
        )
        self.device["transport"] = (
            "USB (user verified), handshake/IMU delegated to SDL HIDAPI"
        )
        self.device["units"] = "rad/s; native gyro = rad/s / (2*pi)"
        self.joystick = self.lib.SDL_GameControllerGetJoystick(self.handle)
        self.button_names = []
        for i in range(64):
            name = self.lib.SDL_GameControllerGetStringForButton(i)
            if not name:
                break
            self.button_names.append(name.decode())
        self.joy_counts = [
            self.lib.SDL_JoystickNumAxes(self.joystick),
            self.lib.SDL_JoystickNumButtons(self.joystick),
            self.lib.SDL_JoystickNumHats(self.joystick),
        ]
        mapping = self.lib.SDL_GameControllerMapping(self.handle)
        try:
            self.device["sdl_mapping"] = (
                C.string_at(mapping).decode() if mapping else ""
            )
        finally:
            if mapping:
                self.lib.SDL_free(mapping)
        self.device.update(
            sdl_revision=self.lib.SDL_GetRevision().decode(),
            button_labels="Nintendo printed labels; SDL_GAMECONTROLLER_USE_BUTTON_LABELS=1",
            controller_button_names=self.button_names,
            joystick_axis_button_hat_counts=self.joy_counts,
            calibration_file=str(profile) if profile else None,
            physical_mapping_verified=bool(self.calibration.get("complete")),
            profile_scope=self.calibration.get(
                "scope", "calibrated" if profile else "unverified"
            ),
        )
        if profile:
            saved = self.calibration["device"]
            if any(
                saved.get(k) != self.device.get(k)
                for k in (
                    "vendor",
                    "product",
                    "sdl_mapping",
                    "sdl_revision",
                    "controller_button_names",
                )
            ):
                self.close()
                raise ValueError(
                    "SDL/device mapping changed; rerun guided controller check"
                )
        self.event = C.create_string_buffer(128)

    def sample(self):
        events = []
        button_events = []
        while self.lib.SDL_PollEvent(self.event):
            typ = struct.unpack_from("<I", self.event.raw)[0]
            if typ in (0x603, 0x604):  # raw joystick buttons, including unmapped extras
                button_events.append(
                    dict(
                        type="joy_button",
                        index=self.event.raw[12],
                        down=typ == 0x603,
                        timestamp_ms=struct.unpack_from("<I", self.event.raw, 4)[0],
                    )
                )
            if typ in (0x650, 0x651, 0x652):
                stamp_ms = struct.unpack_from("<I", self.event.raw, 4)[0]
                index = self.event.raw[12]
                if typ == 0x650:
                    value = struct.unpack_from("<h", self.event.raw, 16)[0]
                    button_events.append(
                        dict(
                            type="axis", index=index, value=value, timestamp_ms=stamp_ms
                        )
                    )
                else:
                    button_events.append(
                        dict(
                            type="button",
                            index=index,
                            down=typ == 0x651,
                            timestamp_ms=stamp_ms,
                        )
                    )
            if typ == 0x659:
                typ, ts, which, sensor, x, y, z, us = struct.unpack_from(
                    "<IIIIfff4xQ", self.event.raw
                )
                if sensor == 2:
                    events.append(dict(timestamp_us=us, gyro_rad_s=[x, y, z]))
        self.lib.SDL_GameControllerUpdate()
        if not self.lib.SDL_GameControllerGetAttached(self.handle):
            raise RuntimeError(
                "Controller disconnected; aborting without holding stale input"
            )
        gyro = (C.c_float * 3)()
        stamp = C.c_uint64()
        if self.lib.SDL_GameControllerGetSensorDataWithTimestamp(
            self.handle, 2, C.byref(stamp), gyro, 3
        ):
            raise RuntimeError("IMU read: " + self.error().decode())
        controller_axes = [
            self.lib.SDL_GameControllerGetAxis(self.handle, i) for i in range(6)
        ]
        axes = [v / 32767 for v in controller_axes]
        # SDL sticks are down-positive; native sticks are forward/up-positive.
        raw_sticks = [axes[0], -axes[1], axes[2], -axes[3]]
        deadzone = self.calibration.get("deadzone", self.deadzone)
        sticks = radial_sticks(
            raw_sticks, self.calibration.get("centers", [0] * 4), deadzone
        )
        raw = list(gyro)
        row = dict(
            sample_monotonic_ns=time.monotonic_ns(),
            sensor_timestamp_us=stamp.value,
            raw_sticks=raw_sticks,
            stick_deadzone=deadzone,
            stick_centers=self.calibration.get("centers", [0] * 4),
            sensor_events=events,
            button_events=button_events,
            sticks=[max(-1, min(1, x)) for x in sticks],
            gyro_rad_s=raw,
            gyro=[
                max(-8, min(8, x / (2 * math.pi))) for x in [raw[0], -raw[2], raw[1]]
            ],
            gyro_axis_mapping="SDL(x,y,z) -> native(x,-z,y), provisional physical sign check pending",
            controller_axes=controller_axes,
            trigger_axes=dict(
                sdl_lefttrigger=controller_axes[4], sdl_righttrigger=controller_axes[5]
            ),
            all_buttons=[
                int(self.lib.SDL_GameControllerGetButton(self.handle, i))
                for i in range(len(self.button_names))
            ],
            joystick_axes=[
                self.lib.SDL_JoystickGetAxis(self.joystick, i)
                for i in range(self.joy_counts[0])
            ],
            joystick_buttons=[
                int(self.lib.SDL_JoystickGetButton(self.joystick, i))
                for i in range(self.joy_counts[1])
            ],
            joystick_hats=[
                self.lib.SDL_JoystickGetHat(self.joystick, i)
                for i in range(self.joy_counts[2])
            ],
        )
        row["physical_buttons"] = mapped_buttons(
            row, self.calibration.get("bindings", DEFAULT_BINDINGS)
        )
        row["buttons"] = [row["physical_buttons"].get(b, 0) for b in GAME_BUTTONS]
        if "gyro_mapping" in self.calibration:
            corrected = [
                x - b for x, b in zip(raw, self.calibration["gyro_bias_rad_s"])
            ]
            row["gyro"] = [
                max(-8, min(8, corrected[v["axis"]] * v["sign"] / (2 * math.pi)))
                for v in (
                    self.calibration["gyro_mapping"][k]
                    for k in ("pitch", "yaw", "roll")
                )
            ]
            row["gyro_axis_mapping"] = self.calibration["gyro_mapping"]
        return row

    def close(self):
        if self.closed:
            return
        if self.handle:
            self.lib.SDL_GameControllerClose(self.handle)
            self.handle = None
        self.lib.SDL_Quit()
        self.closed = True


def main(a):
    if a.timeout <= 0 or a.baseline_seconds < 1 or a.seconds <= 0:
        raise ValueError(
            "timeout/seconds must be positive; baseline must be at least 1s"
        )
    # Validate the private destination BEFORE opening SDL or touching the device.
    if a.out:
        out = Path(a.out).resolve()
        if "work" not in out.parts or out.exists():
            raise ValueError(
                "use a NEW private work/ output directory; old records are never overwritten"
            )
    if not a.raw and not a.out:
        raise ValueError(
            "guided check requires --out work/rl-demo/controller-check-002"
        )
    if a.only != "all" and not a.base_profile:
        raise ValueError("--only requires --base-profile from the previous check")
    if not 0.05 <= a.gyro_threshold <= 3:
        raise ValueError("gyro onset threshold must be .05–3 rad/s")
    base = load_base_profile(a.base_profile) if a.base_profile else None
    c = Controller(a.library, a.deadzone, a.profile)
    if not a.raw:
        try:
            GuidedCheck(
                c,
                a.out,
                a.timeout,
                a.baseline_seconds,
                only=a.only,
                base_profile=base,
                gyro_threshold=a.gyro_threshold,
            ).run()
        finally:
            c.close()
        return
    rows = []
    start = time.monotonic()
    last = 0
    print(json.dumps(c.device, ensure_ascii=False), flush=True)
    try:
        while time.monotonic() - start < a.seconds:
            row = c.sample()
            rows.append(row)
            if time.monotonic() - last >= 0.1:
                print(json.dumps(row), flush=True)
                last = time.monotonic()
            time.sleep(0.001)
    finally:
        c.close()
    stamps = sorted(
        {r["sensor_timestamp_us"] for r in rows if r["sensor_timestamp_us"]}
    )
    hz = (len(stamps) - 1) * 1e6 / (stamps[-1] - stamps[0]) if len(stamps) > 1 else 0
    event_stamps = sorted(
        {
            v["timestamp_us"]
            for r in rows
            for v in r["sensor_events"]
            if v["timestamp_us"]
        }
    )
    event_hz = (
        (len(event_stamps) - 1) * 1e6 / (event_stamps[-1] - event_stamps[0])
        if len(event_stamps) > 1
        else 0
    )
    summary = dict(
        sensor_event_hz=event_hz,
        sensor_event_count=len(event_stamps),
        device=c.device,
        seconds=time.monotonic() - start,
        polls=len(rows),
        unique_sensor_updates=len(stamps),
        observed_sensor_hz=hz,
        gyro_peak_rad_s=[
            max((abs(r["gyro_rad_s"][i]) for r in rows), default=0) for i in range(3)
        ],
        stick_peak=[
            max((abs(r["sticks"][i]) for r in rows), default=0) for i in range(4)
        ],
        button_seen=[any(r["buttons"][i] for r in rows) for i in range(6)],
        gyro_readable=len(stamps) > 1,
        axis_sign_validation="manual movement and native camera comparison still required",
    )
    if a.out:
        out = Path(a.out).resolve()
        if "work" not in out.parts:
            raise ValueError("diagnostics must stay in private work/")
        out.mkdir(parents=True, exist_ok=False)
        (out / "samples.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seconds", type=float, default=15)
    p.add_argument("--out")
    p.add_argument("--library")
    p.add_argument(
        "--raw",
        action="store_true",
        help="legacy free-form monitor; default is guided check",
    )
    p.add_argument(
        "--profile", help="validated private profile.json from a guided check"
    )
    p.add_argument(
        "--timeout", type=float, default=12, help="per-step timeout in guided mode"
    )
    p.add_argument("--baseline-seconds", type=float, default=3)
    p.add_argument("--only", choices=["all", "gyro", "buttons"], default="all")
    p.add_argument(
        "--base-profile",
        help="previous profile.json (may be incomplete) to preserve other checks",
    )
    p.add_argument(
        "--gyro-threshold",
        type=float,
        default=0.35,
        help="first-motion onset threshold, rad/s",
    )
    p.add_argument(
        "--deadzone",
        type=float,
        default=0.15,
        help="radial software deadzone (default .15); guided profile also recenters the sticks",
    )
    main(p.parse_args())
