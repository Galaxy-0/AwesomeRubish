#!/usr/bin/env python3
"""匹配后处理：把候选代码里"语义等价但字节不同"的部分修正成目标的形式。

工作方式：链式调用下面的 rewriting pass，每个 pass 处理一类差异。
与 SSBU 的做法一致（他们的 tools/fix_*.py），但规则基于**我们自己的实测**，
不是照抄。

已确认的三类差异（见 docs/06-prologue-postprocess.md）：

  1. **prologue 调度**：编译器把「SIMD 零初始化块」排在寄存器保存块之前，
     目标排在之后。修正 = 把该块移到寄存器保存块之后。

  2. **相邻 store 交换**：两条独立的 store 顺序颠倒。修正 = 交换回来。
     （目标里顺序固定，上游 clang 有时反过来）

  3. **adrp+取址对**：`.o` 里是占位符，链接后才有值。**不需要修**，
     是比对工具该忽略的。

用法:
    python3 postprocess.py --obj in.o --func NAME --out out.o [--target-dump target.txt]

注：本脚本先做**内存态验证**（报告修正能带来多少提升），
真正改写 .o 需要更完整的 ELF 重写，留作后续工作。
"""
from __future__ import annotations

import argparse
import struct
import subprocess
from pathlib import Path

OBJDUMP = "/opt/homebrew/opt/llvm/bin/llvm-objdump"

# ---- 指令识别辅助 ----

def is_stp_pre(w: int) -> bool:
    """stp xA, xB, [sp, #-imm]!  (pre-index, 64-bit)"""
    return (w & 0xFFC003E0) == 0xA98003E0

def is_zero_init_block(w: int) -> bool:
    """SIMD 零初始化：movi v?.2d, #0"""
    return (w & 0xFFFFFC1F) == 0x6F00E400

def is_stp_q0(w: int) -> bool:
    """stp q0, q0, [sp, #imm]"""
    return (w & 0xFFC003FF) == 0xAD0003E0 or (w & 0xFFC003FF) == 0xAD0103E0

def is_str_xzr_or_reg_sp(w: int) -> bool:
    """str xR, [sp, #imm]"""
    return (w & 0xFFC003E0) == 0xF90003E0

def is_str_wzr(w: int) -> bool:
    """str wzr, [xN, #imm]"""
    return (w & 0xFFE003FF) == 0xB90003FF


def read_insns(path: Path, func: str) -> list[tuple[int, int]]:
    """返回 [(offset, encoding)]。"""
    out = subprocess.run([OBJDUMP, "-d", str(path)], capture_output=True, text=True).stdout
    cur = None
    rows = []
    for line in out.splitlines():
        s = line.strip()
        if s.endswith(">:") and "<" in s:
            cur = s.split("<")[-1].rstrip(">:").strip()
            continue
        if "\t" in line and cur == func:
            head = line.split("\t", 1)[0].strip()
            try:
                off = int(head.split(":", 1)[0].strip(), 16)
                enc = int(head.split(":", 1)[1].strip(), 16)
            except (ValueError, IndexError):
                continue
            rows.append((off, enc))
    return rows


def fix_zero_init_position(cand: list[int]) -> tuple[list[int], bool]:
    """把「movi v.2d + stp q0,q0」零初始化块移到寄存器保存块之后。

    目标形制：
        sub sp, sp, #N
        str/stp 保存寄存器 × K
        movi v0.2d, #0
        stp q0, q0, [sp, #imm]
        <body>
    上游形制：
        sub sp, sp, #N
        movi v0.2d, #0
        stp q0, q0, [sp, #imm]
        str/stp 保存寄存器 × K
        <body>
    """
    out = cand[:]
    # 找零初始化块
    zi = None
    for i in range(min(len(out) - 1, 16)):
        if is_zero_init_block(out[i]) and is_stp_q0(out[i + 1]):
            zi = i
            break
    if zi is None:
        return out, False

    # 找零初始化块之后的连续寄存器保存块
    j = zi + 2
    save_start = j
    while j < len(out) and (is_stp_pre(out[j]) or is_str_xzr_or_reg_sp(out[j]) or (out[j] & 0xFFC00000) == 0xA9000000):
        j += 1
    if j == save_start:
        return out, False   # 后面没有保存块，无需移动

    # 重排：sub sp | 保存块 | 零初始化块 | 其余
    block_zi = out[zi:zi + 2]
    block_save = out[save_start:j]
    new = out[:zi] + block_save + block_zi + out[j:]
    return new, new != out


def fix_adjacent_store_swaps(cand: list[int], target: list[int]) -> tuple[list[int], int]:
    """把相邻的可交换 store 对按目标顺序摆正。"""
    out = cand[:]
    fixed = 0
    n = min(len(out), len(target))
    for i in range(n - 1):
        if out[i] != target[i] and out[i] == target[i + 1] and out[i + 1] == target[i]:
            # 同一对，顺序颠倒
            if (out[i] & 0xFFC00000) in (0xB9000000, 0xF9000000, 0x3D800000, 0xBD000000, 0xFD000000):
                out[i], out[i + 1] = out[i + 1], out[i]
                fixed += 1
    return out, fixed


def trim_trailing_padding(cand: list[int], target: list[int]) -> int:
    """返回尾部 padding 条数（函数 ret 之后的对齐填充，非代码差异）。

    目标里这些位置常是 0，候选里是 nop（0xd503201f）——两者都是填充。
    """
    n = min(len(cand), len(target))
    # 找最后一个 ret
    last_ret = -1
    for i in range(n):
        if cand[i] == 0xD65F03C0:
            last_ret = i
    if last_ret < 0:
        return 0
    cnt = 0
    for i in range(last_ret + 1, n):
        if cand[i] in (0x00000000, 0xD503201F) and target[i] in (0x00000000, 0xD503201F):
            cnt += 1
    return cnt


def is_addr_use(w: int) -> bool:
    """adrp 之后的取址/访存指令。"""
    if (w & 0xFF800000) == 0x91000000:      # add imm
        return True
    if (w & 0xFFC00000) in (0xF9400000, 0xB9400000, 0x39400000, 0x79400000,
                            0xF9000000, 0xB9000000, 0x39000000, 0x79000000):
        return True
    if (w & 0x3F000000) == 0x3D000000:      # SIMD ldr/str q
        return True
    return False


def count_adrp_pairs(cand: list[int], target: list[int]) -> list[int]:
    """返回「adrp + 取址」对的索引（这些位置的差异是重定位占位，非真差异）。"""
    out = []
    n = min(len(cand), len(target))
    for i in range(n - 1):
        g0, g1 = target[i], target[i + 1]
        c0, c1 = cand[i], cand[i + 1]
        if (
            (g0 & 0x9F000000) == 0x90000000 and (c0 & 0x9F000000) == 0x90000000
            and (g0 & 0x1F) == (c0 & 0x1F)
            and is_addr_use(g1) and is_addr_use(c1)
            and (g1 & 0xFF000000) == (c1 & 0xFF000000)
            and ((g1 >> 5) & 0x1F) == (g0 & 0x1F)
            and ((c1 >> 5) & 0x1F) == (c0 & 0x1F)
        ):
            out += [i, i + 1]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", type=Path, required=True)
    ap.add_argument("--addr", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--obj", type=Path, required=True)
    ap.add_argument("--func", required=True)
    args = ap.parse_args()

    rows = read_insns(args.obj, args.func)
    if not rows:
        print(f"未找到 {args.func}")
        return
    game = args.text.read_bytes()
    G = [struct.unpack_from("<I", game, args.addr + i * 4)[0] for i in range(len(rows))]
    C = [r[1] for r in rows]

    print(f"函数 {args.func}: {len(C)} 条")
    raw = sum(1 for i in range(len(C)) if G[i] == C[i])
    print(f"  原始字节一致: {raw}/{len(C)} = {raw/len(C)*100:.1f}%")

    adrp = count_adrp_pairs(C, G)
    print(f"  [pass 1] adrp 取址对（重定位占位）: {len(adrp)} 条")

    cur, moved = fix_zero_init_position(C)
    print(f"  [pass 2] prologue 零初始化块重排: {'已移动' if moved else '无需移动'}")

    cur, nsw = fix_adjacent_store_swaps(cur, G)
    print(f"  [pass 3] 相邻 store 交换修正: {nsw} 处")

    pad = trim_trailing_padding(cur, G)
    print(f"  [pass 4] 尾部对齐填充: {pad} 条（非代码差异）")

    after = sum(1 for i in range(len(cur)) if G[i] == cur[i])
    effective = after + len(adrp) + pad
    print(f"  后处理后严格一致: {after}/{len(cur)}")
    print(f"  实质一致(含占位/填充): {effective}/{len(cur)} = {effective/len(cur)*100:.1f}%")

    explained = set(adrp)
    unexplained = [
        i for i in range(len(cur))
        if G[i] != cur[i]
        and i not in explained
        and not (cur[i] in (0, 0xD503201F) and G[i] in (0, 0xD503201F))
    ]
    if unexplained:
        print(f"  ⚠️ 未解释差异: {len(unexplained)} 处 @ {unexplained[:8]}")
        for i in unexplained[:5]:
            print(f"    [{i}] C={cur[i]:#010x} G={G[i]:#010x}")
    else:
        print("  ✅ 无未解释差异")


if __name__ == "__main__":
    main()
