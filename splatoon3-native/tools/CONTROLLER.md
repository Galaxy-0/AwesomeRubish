# Scripted controller

`DM_KEYS` is the final reproducible route input. Its existing syntax is
`f<frame>:<keys>[~<hold seconds>][*<repeats>/<frame interval>]`; without `f`,
times and intervals use seconds. Steps execute in written order.

- Buttons: `A B X Y LS RS L R ZL ZR Plus Minus Left Up Right Down`.
- Left stick: `LLeft LUp LRight LDown`; right stick: `RLeft RUp RRight RDown`.
- Optional virtual controller rotation: `GUp GDown GLeft GRight GRollLeft GRollRight`.
  These set X / Y / Z angular rates to ±0.1 turns/s while held. Orientation
  persists after release. A script containing these names enables the virtual
  six-axis device; otherwise the previous no-motion behavior is retained.
- Combine inputs with `+`, for example `f5000:GLeft+GUp~0.15`.

The 0x60-byte sensor layout and connected flag follow
[libnx's HID definitions](https://github.com/switchbrew/libnx/blob/master/nx/include/switch/services/hid.h).
This controller feeds the game's HID APIs; it does not modify tutorial flags,
player position or camera memory. Physical calibration against a real IMU is
not claimed.

The virtual sensor keeps 16 newest-first samples at 200 Hz. Reading another
handle does not advance its sampling number. This matters for Splatoon 3:
`main+0x459b920` requests 16 samples and ignores the returned count;
`main+0x4d4f704` examines all 16, and zero acceleration in an unused entry can
invalidate the whole batch. A single current state is insufficient here.

Set `DM_HID_TRACE=1` for read-side diagnostics. `HID_READ npad` reports the axes
returned to the game; `HID_READ six` reports the caller, count, sampling number,
connected flag, rate and accumulated angles. The trace is limited to one entry
per 60 presented frames per kind. Use screenshots / actual game UI transitions
as separate evidence that the game acted on those returned values.

For finding a route interactively, create a FIFO inside `work/` and start the
host with `DM_HID_FIFO=/absolute/path/to/that/fifo`. This also enables motion.
Then send one action:

```sh
python3 tools/pad.py --fifo work/m2/hid-route4.fifo --hold 0.15 GLeft GUp
python3 tools/pad.py --fifo work/m2/hid-route4.fifo --hold 2 LUp ZR
```

Every action automatically releases its buttons/sticks/angular rate after the
hold. The host logs the actual presented frame where the action starts. Use
that evidence to replace exploration with a fixed `DM_KEYS` route before a
milestone acceptance run. The optional FIFO accepts nine fields per line:
hex button mask, four signed stick axes, three angular rates, hold seconds.
The host rejects axes outside ±32767, rates outside ±1 turn/s, non-finite
values and holds outside 0–30 seconds. There is no network listener.
