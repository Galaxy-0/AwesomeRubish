#!/usr/bin/env python3
"""Send one bounded controller action to this run's DM_HID_FIFO (local only)."""
import argparse
from pathlib import Path
import stat
import os
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--fifo", type=Path, required=True)
parser.add_argument("--hold", type=float, default=0.15)
parser.add_argument("keys", nargs="*")
args = parser.parse_args()
if not stat.S_ISFIFO(args.fifo.stat().st_mode):
    parser.error("--fifo must be a named pipe")
if not 0 <= args.hold <= 30:
    parser.error("hold must be between 0 and 30 seconds")
names = "A B X Y LS RS L R ZL ZR Plus Minus Left Up Right Down".split()
buttons = 0
axes = [0] * 4
gyro = [0.0] * 3
stick = {"LLeft": (0, -32767), "LRight": (0, 32767), "LUp": (1, 32767), "LDown": (1, -32767),
         "RLeft": (2, -32767), "RRight": (2, 32767), "RUp": (3, 32767), "RDown": (3, -32767)}
motion = {"GUp": (0, 0.1), "GDown": (0, -0.1), "GLeft": (1, -0.1), "GRight": (1, 0.1),
          "GRollLeft": (2, -0.1), "GRollRight": (2, 0.1)}
for token in args.keys:
    for key in token.split("+"):
        if key in names:
            buttons |= 1 << names.index(key)
        elif key in stick:
            i, value = stick[key]
            axes[i] = value
        elif key in motion:
            i, value = motion[key]
            gyro[i] = value
        else:
            parser.error(f"unknown key {key}")
deadline = time.monotonic() + 2
while True:
    try:
        fd = os.open(args.fifo, os.O_WRONLY | os.O_NONBLOCK)
        break
    except OSError:
        if time.monotonic() >= deadline:
            parser.error("no running controller reader on this FIFO")
        time.sleep(0.02)
with os.fdopen(fd, "w") as stream:
    stream.write(" ".join([f"{buttons:x}", *map(str, axes), *map(str, gyro), str(args.hold)]) + "\n")
