#!/bin/bash
# boot.sh <log name> [seconds] [VAR=value ...] — run the patched Splatoon 3 under dmhost with a time limit
R="$(cd "$(dirname "$0")/.." && pwd)"; W="$R/work"; VER=v720896
name=${1:?log name}; secs=${2:-60}; shift 2 2>/dev/null
mkdir -p "$W/run/save" "$W/run/temp"
env DM_ROOT="$W" DM_ROMFS="$W/data/$VER/RomFS" DM_SAVE="$W/run/save" DM_TEMP="$W/run/temp" \
    DM_MSL_DIR="$W/build/cache/metal_shader_cache" DM_FONT_DIR="$W/build/font" "$@" \
    python3 -c '
import subprocess, sys
p = subprocess.Popen(sys.argv[2:])
try:
    rc = p.wait(timeout=float(sys.argv[1]))
except subprocess.TimeoutExpired:
    p.terminate()
    try:
        rc = p.wait(timeout=8)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        rc = 124
sys.exit(rc if rc >= 0 else 128 - rc)
' "$secs" "$R/upstream/dm/host/dmhost" "$W/build/patched_$VER" > "$W/run/$name.log" 2>&1
status=$?
echo "exit $status → $W/run/$name.log"; LC_ALL=C grep -a "【红】" "$W/run/$name.log" | sort | uniq -c | head -30; tail -40 "$W/run/$name.log"
exit "$status"
