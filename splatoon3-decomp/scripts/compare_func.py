#!/usr/bin/env python3
"""把 .o 和目标函数的指令对齐比对，正确处理重定位和编译器调度差异。

关键认识（来自实测）：
  1. `.o` 里被重定位的指令（adrp/add/call 取地址）的立即数是占位符，
     必须忽略——否则会误判为"不匹配"。
  2. 编译器会把「寄存器保存块」和「零初始化块」调度到不同位置，
     这些是顺序差异，可用后处理（prologue 修复）修正。
  3. 函数末尾的 padding（nop vs 0）不是真差异。

输出：区分三类
  - real   : 真差异（指令不同、非调度）
  - order  : 顺序差异（同一批指令换了位置）
  - reloc  : 重定位占位差异（非差异）
"""
from __future__ import annotations

import argparse
import struct
import subprocess
from pathlib import Path

OBJDUMP = "/opt/homebrew/opt/llvm/bin/llvm-objdump"
READELF = "/opt/homebrew/opt/llvm@17/bin/llvm-readelf"

# 重定位类型 → 该指令的立即数是占位符
RELOC_TYPES = {
    "R_AARCH64_ADR_PREL_PG_HI21",   # adrp
    "R_AARCH64_ADD_ABS_LO12_NC",     # add
    "R_AARCH64_LDST64_ABS_LO12_NC",  # ldr/str
    "R_AARCH64_LDST32_ABS_LO12_NC",
    "R_AARCH64_LDST16_ABS_LO12_NC",
    "R_AARCH64_LDST8_ABS_LO12_NC",
    "R_AARCH64_CALL26",              # bl
    "R_AARCH64_JUMP26",              # b
    "R_AARCH64_ABS64",               # 数据
    "R_AARCH64_PREL32",
}


def func_insns(obj: Path, fn: str) -> list[tuple[int, int, str]]:
    """返回 [(offset, encoding, text)]，offset 是 .text 段内字节偏移。"""
    out = subprocess.run([OBJDUMP, "-d", str(obj)], capture_output=True, text=True).stdout
    cur = None
    rows: list[tuple[int, int, str]] = []
    for line in out.splitlines():
        s = line.strip()
        if s.endswith(">:") and "<" in s:
            cur = s.split("<")[-1].rstrip(">:").strip()
            continue
        if "\t" in line and cur == fn:
            head, txt = line.split("\t", 1)
            h = head.strip()
            try:
                off = int(h.split(":", 1)[0].strip(), 16)
                enc = int(h.split(":", 1)[1].strip(), 16)
            except (ValueError, IndexError):
                continue
            rows.append((off, enc, txt.strip()))
    return rows


def reloc_offsets(obj: Path, section: str = ".text") -> set[int]:
    """返回 .text 里被重定位的指令偏移集合。

    注意：多个函数共用一个 .o 时，重定位偏移是相对 .text 段起点的。
    本函数返回的偏移与 func_insns 的 offset 同源（都来自 objdump 的段内偏移）。
    """
    out = subprocess.run([READELF, "-r", str(obj)], capture_output=True, text=True).stdout
    offs: set[int] = set()
    in_sec = False
    for line in out.splitlines():
        if line.startswith("Relocation section"):
            in_sec = f"'{section}'" in line
            continue
        if not in_sec:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            off = int(parts[0], 16)
        except ValueError:
            continue
        if parts[2] in RELOC_TYPES:
            offs.add(off)
    return offs


def find_adrp_add_pairs(game: list[int], cand: list[int]) -> set[int]:
    """找出「adrp + 取地址指令」对——两边形状相同则视为等价。

    .o 里 adrp 及其后续访存指令的立即数是占位符（未链接），
    目标里是已解析的真实地址。只要寄存器形制一致，链接后即等价。

    覆盖：adrp + add / ldr / str / ldrb / strb / ldrh / strh ...
    """
    pairs: set[int] = set()
    n = min(len(game), len(cand))
    # 取地址类后继指令的掩码（这些指令的 imm12 是页内偏移）
    LOAD_STORE = (
        (0xFFC00000, 0xF9400000),  # ldr x
        (0xFFC00000, 0xB9400000),  # ldr w
        (0xFFC00000, 0x39400000),  # ldrb
        (0xFFC00000, 0x79400000),  # ldrh
        (0xFFC00000, 0xF9000000),  # str x
        (0xFFC00000, 0xB9000000),  # str w
        (0xFFC00000, 0x39000000),  # strb
        (0xFFC00000, 0x79000000),  # strh
        (0xFF800000, 0x91000000),  # add imm
        (0x3D800000, 0x3D800000),  # ldr/str q (SIMD) — 见下方单独处理
    )

    def is_addr_use(w: int) -> bool:
        if (w & 0xFF800000) == 0x91000000:      # add imm
            return True
        for mask, val in LOAD_STORE[:-1]:
            if (w & mask) == val:
                return True
        # SIMD load/store: 0x3Dxxxxxx / 0xFDxxxxxx
        if (w & 0x3F000000) in (0x3D000000,):
            return True
        return False

    for i in range(n - 1):
        g0, g1 = game[i], game[i + 1]
        c0, c1 = cand[i], cand[i + 1]
        if (
            (g0 & 0x9F000000) == 0x90000000 and (c0 & 0x9F000000) == 0x90000000
            and (g0 & 0x1F) == (c0 & 0x1F)                    # 同一个 Rd
            and is_addr_use(g1) and is_addr_use(c1)
        ):
            # 后继指令的 opcode 形制必须一致，且基址寄存器是 adrp 的 Rd
            if (g1 & 0xFF000000) == (c1 & 0xFF000000) and ((g1 >> 5) & 0x1F) == (g0 & 0x1F) and ((c1 >> 5) & 0x1F) == (c0 & 0x1F):
                pairs.add(i)
                pairs.add(i + 1)
    return pairs


def find_swap_pairs(game: list[int], cand: list[int], relocs: set[int]) -> set[int]:
    """找出「同一对指令只是顺序颠倒」的位置。

    编译器（尤其 Nintendo 分叉）有时把两条独立的 store 交换顺序，
    这在语义上等价。返回可以视为等价的索引集合。
    """
    swap_ok: set[int] = set()
    n = min(len(game), len(cand))
    i = 0
    while i < n - 1:
        if (
            game[i] == cand[i + 1]
            and game[i + 1] == cand[i]
            and game[i] != game[i + 1]          # 确实不同，才有交换的意义
            and not is_branch(game[i])           # 分支不能随便换
            and not is_branch(game[i + 1])
            and (i * 4) not in relocs
            and ((i + 1) * 4) not in relocs
        ):
            swap_ok.add(i)
            swap_ok.add(i + 1)
            i += 2
            continue
        i += 1
    return swap_ok


def is_branch(w: int) -> bool:
    return (
        (w & 0xFC000000) in (0x14000000, 0x94000000)   # B / BL
        or (w & 0xFF000010) == 0x54000000              # B.cond
        or (w & 0x7E000000) in (0x34000000, 0x36000000)  # CBZ/CBNZ / TBZ/TBNZ
    )


def is_padding(w: int) -> bool:
    return w in (0x00000000, 0xD503201F)


def classify(g: int, c: int, g_reloc: bool, c_reloc: bool) -> str:
    if is_padding(g) and is_padding(c):
        return "pad"          # nop / 0 的差异，非实质
    if is_branch(g) and is_branch(c):
        # 只比 opcode 高字节和寄存器
        if (g >> 24) == (c >> 24) and (g & 0x1F) == (c & 0x1F):
            return "match"
        return "real"
    if g_reloc and c_reloc:
        # 都是重定位指令，比 opcode + 寄存器
        if (g & 0xFFC00000) == (c & 0xFFC00000) and (g & 0x1F) == (c & 0x1F):
            return "reloc"
        return "real"
    if g == c:
        return "match"
    return "real"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", type=Path, required=True, help="目标 .text 原始字节")
    ap.add_argument("--addr", type=lambda s: int(s, 0), required=True, help="函数在 .text 的偏移")
    ap.add_argument("--obj", type=Path, required=True)
    ap.add_argument("--func", required=True)
    args = ap.parse_args()

    rows = func_insns(args.obj, args.func)
    if not rows:
        print(f"未找到函数 {args.func}")
        return
    relocs = reloc_offsets(args.obj)
    game_bytes = args.text.read_bytes()
    G = [struct.unpack_from("<I", game_bytes, args.addr + i * 4)[0] for i in range(len(rows))]
    C = [r[1] for r in rows]

    swaps = find_swap_pairs(G, C, relocs)
    adrp_pairs = find_adrp_add_pairs(G, C)

    counts = {"match": 0, "reloc": 0, "pad": 0, "swap": 0, "adrp": 0, "real": 0}
    real_diffs = []
    for i, (off, c, txt) in enumerate(rows):
        if i in adrp_pairs:
            counts["adrp"] += 1
            continue
        if i in swaps:
            counts["swap"] += 1
            continue
        kind = classify(G[i], c, off in relocs, off in relocs)
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "real":
            real_diffs.append((i, G[i], c, txt))

    total = len(rows)
    trivial = sum(counts[k] for k in ("match", "reloc", "pad", "swap", "adrp"))
    print(f"函数 {args.func}: {total} 条指令")
    print(f"  完全匹配   : {counts['match']:4d}")
    print(f"  重定位占位 : {counts['reloc']:4d}  （链接后才有值，非差异）")
    print(f"  adrp+add   : {counts['adrp']:4d}  （取地址对，链接后等价）")
    print(f"  padding    : {counts['pad']:4d}  （nop/0，非差异）")
    print(f"  顺序交换对 : {counts['swap']:4d}  （同两条指令颠倒，语义等价）")
    print(f"  真差异     : {counts['real']:4d}")
    print(f"  → 实质匹配率: {trivial}/{total} = {trivial/total*100:.1f}%")
    if real_diffs:
        print(f"\n  真差异明细（前 10）:")
        for i, g, c, txt in real_diffs[:10]:
            print(f"    [{i:4d}] G={g:#010x}  C={c:#010x}   {txt[:44]}")


if __name__ == "__main__":
    main()
