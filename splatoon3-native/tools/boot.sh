#!/bin/bash
# boot.sh <log name> [seconds] [VAR=value ...] — run the patched Splatoon 3 under dmhost with a time limit
R="$(cd "$(dirname "$0")/.." && pwd)"; W="$R/work"; VER=v720896
name=${1:?log name}; secs=${2:-60}; shift 2 2>/dev/null
mkdir -p "$W/run/save" "$W/run/temp"
env DM_ROOT="$W" DM_ROMFS="$W/data/$VER/RomFS" DM_SAVE="$W/run/save" DM_TEMP="$W/run/temp" \
    DM_MSL_DIR="$W/build/cache/metal_shader_cache" DM_FONT_DIR="$W/build/font" "$@" \
    perl -e 'alarm shift; exec @ARGV' "$secs" "$R/upstream/dm/host/dmhost" "$W/build/patched_$VER" > "$W/run/$name.log" 2>&1
echo "exit $? → $W/run/$name.log"; LC_ALL=C grep -a "【红】" "$W/run/$name.log" | sort | uniq -c | head -30; tail -40 "$W/run/$name.log"
