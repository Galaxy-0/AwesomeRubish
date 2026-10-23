"""SDL2 HIDAPI Switch Pro USB handshake/IMU diagnostic, no game required.

Units and axes follow the installed SDL_sensor.h: rad/s, X=pitch,Y=yaw,Z=roll.
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


class Controller:
    def __init__(self, library=None, deadzone=0.0):
        if not 0 <= deadzone < 0.5:
            raise ValueError("extra deadzone must be in [0,.5)")
        self.deadzone = deadzone
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
        self.event = C.create_string_buffer(128)

    def sample(self):
        events = []
        button_events = []
        trigger_edges = set()
        button_edges = set()
        while self.lib.SDL_PollEvent(self.event):
            typ = struct.unpack_from("<I", self.event.raw)[0]
            if typ in (0x650, 0x651, 0x652):
                stamp_ms = struct.unpack_from("<I", self.event.raw, 4)[0]
                index = self.event.raw[12]
                if typ == 0x650:
                    value = struct.unpack_from("<h", self.event.raw, 16)[0]
                    if index in (4, 5) and value > 16383:
                        trigger_edges.add(index)
                    button_events.append(
                        dict(
                            type="axis", index=index, value=value, timestamp_ms=stamp_ms
                        )
                    )
                else:
                    if typ == 0x651:
                        button_edges.add(index)
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
        axes = [
            self.lib.SDL_GameControllerGetAxis(self.handle, i) / 32767 for i in range(6)
        ]
        # SDL sticks are down-positive; native sticks are forward/up-positive.
        raw_sticks = [axes[0], -axes[1], axes[2], -axes[3]]
        sticks = [
            0.0
            if abs(x) < self.deadzone
            else math.copysign((abs(x) - self.deadzone) / (1 - self.deadzone), x)
            for x in raw_sticks
        ]
        # SDL Nintendo button-label hint keeps A/B/X/Y labels; triggers are axes.
        buttons = [
            int(axes[5] > 0.5 or 5 in trigger_edges),
            int(axes[4] > 0.5 or 4 in trigger_edges),
            int(
                self.lib.SDL_GameControllerGetButton(self.handle, 10)
                or 10 in button_edges
            ),
            int(
                self.lib.SDL_GameControllerGetButton(self.handle, 8)
                or 8 in button_edges
            ),
            int(
                self.lib.SDL_GameControllerGetButton(self.handle, 1)
                or 1 in button_edges
            ),
            int(
                self.lib.SDL_GameControllerGetButton(self.handle, 3)
                or 3 in button_edges
            ),
        ]
        raw = list(gyro)
        return dict(
            sample_monotonic_ns=time.monotonic_ns(),
            sensor_timestamp_us=stamp.value,
            raw_sticks=raw_sticks,
            stick_deadzone=self.deadzone,
            sensor_events=events,
            button_events=button_events,
            sticks=[max(-1, min(1, x)) for x in sticks],
            gyro_rad_s=raw,
            gyro=[
                max(-8, min(8, x / (2 * math.pi))) for x in [raw[0], -raw[2], raw[1]]
            ],
            gyro_axis_mapping="SDL(x,y,z) -> native(x,-z,y), provisional physical sign check pending",
            buttons=buttons,
            all_buttons=[
                int(self.lib.SDL_GameControllerGetButton(self.handle, i))
                for i in range(15)
            ],
        )

    def close(self):
        if self.closed:
            return
        if self.handle:
            self.lib.SDL_GameControllerClose(self.handle)
            self.handle = None
        self.lib.SDL_Quit()
        self.closed = True


def main(a):
    c = Controller(a.library, a.deadzone)
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
        "--deadzone",
        type=float,
        default=0,
        help="optional EXTRA software deadzone; default0 leaves game-native deadzone intact",
    )
    main(p.parse_args())
