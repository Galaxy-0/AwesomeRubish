#!/usr/bin/env bash
# Splatoon 3 提取链路 —— 从游戏文件到可分析的 NSO
#
# 前置:
#   - 游戏本体 XCI、11.3.0 更新 NSP
#   - prod.keys（自备，放在 TOOLS/keys/）
#   - tools/bin/{hactool,nstool} 已编译
#
# 用法:
#   ./extract.sh <base.xci> <update.nsp>
#
# 注意: 11.3.0 的主 NCA 是分段 BKTR patch 格式，需要 base NCA 才能重建。
#       hactool 处理不了，必须用 nstool。
set -euo pipefail

BASE_XCI="${1:?用法: ./extract.sh <base.xci> <update.nsp>}"
UPDATE_NSP="${2:?用法: ./extract.sh <base.xci> <update.nsp>}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HACTOOL="$ROOT/tools/bin/hactool"
NSTOOL="$ROOT/tools/bin/nstool"
KEYS="$ROOT/tools/keys/prod.keys.clean"
WORK="$ROOT/work"

for f in "$HACTOOL" "$NSTOOL" "$KEYS"; do
  [[ -e "$f" ]] || { echo "缺少: $f" >&2; exit 1; }
done

mkdir -p "$WORK"/{nca,base,exefs,romfs}
mkdir -p "$ROOT/binaries/11.3.0" "$ROOT/binaries/base-v0"

echo "==> [1/5] 从更新 NSP 抽出 NCA"
"$HACTOOL" -t pfs0 -k "$KEYS" --outdir="$WORK/nca" "$UPDATE_NSP" 2>&1 | grep -v WARN | tail -3

echo "==> [2/5] 从本体 XCI 抽出 base 分区（BKTR 重建需要）"
"$HACTOOL" -t xci -k "$KEYS" --securedir="$WORK/base" "$BASE_XCI" 2>&1 | grep -v WARN | tail -3

# 主 program NCA 是最大的那个；base NCA 同理
PATCH_NCA="$(find "$WORK/nca" -name '*.nca' -size +1G | head -1)"
BASE_NCA="$(find "$WORK/base" -name '*.nca' -size +1G | head -1)"
echo "    patch NCA: $(basename "$PATCH_NCA")"
echo "    base  NCA: $(basename "$BASE_NCA")"

echo "==> [3/5] nstool 做 BKTR 重建并提取程序（这一步慢，约 3 分钟 / 7GB）"
"$NSTOOL" -k "$KEYS" --basenca "$BASE_NCA" -x / "$WORK/romfs" "$PATCH_NCA" \
  2>&1 | grep -viE "warning|^\[NCA|^ +[A-Z][a-z]+ " | tail -3

echo "==> [4/5] 拷贝程序文件"
cp "$WORK/romfs/0/main" "$WORK/romfs/0/main.npdm" "$WORK/romfs/0/rtld" "$WORK/romfs/0/sdk" \
   "$ROOT/binaries/11.3.0/"

echo "==> [5/5] 解压 NSO（LZ4）"
"$HACTOOL" -t nso0 -k "$KEYS" \
  --uncompressed="$ROOT/binaries/11.3.0/main.uncompressed" \
  "$ROOT/binaries/11.3.0/main" 2>&1 | grep -v WARN | tail -6

echo
echo "==> 验证 Build ID（应为 28c4287aee36f749）"
python3 - "$ROOT/binaries/11.3.0/main" <<'PY'
import struct, sys
d = open(sys.argv[1], "rb").read(0x60)
assert d[:4] == b"NSO0", "不是 NSO0"
bid = d[0x40:0x48].hex()
print(f"    build_id = {bid}")
print("    ✅ 匹配运行时" if bid == "28c4287aee36f749" else "    ⚠️ 与运行时不一致！")
PY
