#!/usr/bin/env python3
"""在目标二进制里搜索用已知源码（zlib 等）编译出的函数。

方法：把候选函数的首 N 条指令（归一化：忽略分支/重定位立即数）做成指纹，
在目标 .text 里建立滚动索引，快速定位所有匹配位置。

用法:
    python3 find_known_funcs.py --text work/text/text.bin --objs '/tmp/zlib-test/objs/*.o'
"""
from __future__ import annotations

import argparse
import glob
import struct
import subprocess
from collections import defaultdict
from pathlib import Path

OBJDUMP = "/opt/homebrew/opt/llvm/bin/llvm-objdump"


def norm(w: int) -> int:
    """归一化指令：把分支/重定位的立即数抹掉，只留 opcode + 寄存器。"""
    if (w & 0xFC000000) == 0x14000000:  # B
        return w & 0xFC000000 | (w & 0x1F)  # 保留 Rd
    if (w & 0xFF000010) == 0x54000000:  # B.cond
        return w & 0xFF00001F | 0x10
    if (w & 0x9F000000) == 0x90000000:  # ADRP
        return w & 0x9F00001F  # 去掉立即数
    if (w & 0xFC000000) == 0x94000000:  # BL
        return 0x94000000
    return w


def read_text(path: Path) -> list[int]:
    d = path.read_bytes()
    return [struct.unpack_from("<I", d, i)[0] for i in range(0, len(d) - 3, 4)]


def obj_functions(path: Path) -> dict[str, list[int]]:
    out = subprocess.run([OBJDUMP, "-d", str(path)], capture_output=True, text=True).stdout
    funcs: dict[str, list[int]] = {}
    cur: str | None = None
    buf: list[int] = []
    for line in out.splitlines():
        s = line.strip()
        if s.endswith(">:") and "<" in s:
            if cur:
                funcs[cur] = buf
            cur = s.split("<")[-1].rstrip(">:").strip()
            buf = []
        elif "\t" in line and cur is not None:
            head = line.split("\t", 1)[0].strip()
            try:
                buf.append(int(head.split(":", 1)[1].strip(), 16))
            except (ValueError, IndexError):
                pass
    if cur:
        funcs[cur] = buf
    return funcs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", type=Path, required=True)
    ap.add_argument("--objs", required=True, help="glob")
    ap.add_argument("--window", type=int, default=20, help="指纹长度（指令数）")
    ap.add_argument("--min-match", type=int, default=18)
    args = ap.parse_args()

    gw = read_text(args.text)
    n = len(gw)
    W = args.window

    # 用前 W 条归一化指令作为指纹
    def fp(insns: list[int]) -> tuple[int, ...]:
        return tuple(norm(x) for x in insns[:W])

    # 目标里所有窗口的指纹索引（只索引每 4 条对齐位置以控制内存）
    idx: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for i in range(0, n - W, 1):
        idx[tuple(gw[i : i + W])].append(i)   # 精确匹配索引

    # 也做"宽松"匹配：对每个候选，先精确找，找不到再用 opcode 序列
    def opcode(w: int) -> str:
        return f"{w & 0x9F000000:08x}" if (w & 0x9F000000) in (0x90000000,) else f"{w & 0xFF000000:08x}"

    results = []
    for path in sorted(glob.glob(args.objs)):
        name = Path(path).stem
        for fname, insns in obj_functions(Path(path)).items():
            if len(insns) < W or len(insns) > 4000:
                continue
            key = fp(insns)
            hits = idx.get(key, [])
            exact = len(hits)
            if not hits:
                continue
            results.append((exact, name, fname, len(insns), hits[:3]))

    results.sort(reverse=True)
    print(f"{'命中':>4s}  {'文件':22s} {'函数':34s} {'长度':>5s}  位置")
    print("-" * 90)
    for exact, name, fname, ln, hits in results[:30]:
        hs = ", ".join(f"{h*4:#x}" for h in hits)
        print(f"{exact:4d}  {name:22s} {fname:34s} {ln:5d}  {hs}")
    if not results:
        print("（无精确指纹匹配）")


if __name__ == "__main__":
    main()
