#!/usr/bin/env python3
"""测量 prologue 调度差异对匹配率的影响，并验证"后处理修复"是否有效。

背景（见 docs/05-clang-version-findings.md）：
  目标二进制里 35,106 个带 stp x29,x30 + str x19 的 prologue，100% 都是
  'mov x29, sp' 紧跟在 stp/str 之后；而上游 clang 会把它调度到更后面。

本脚本：
  1. 编译候选源码
  2. 计算原始匹配率
  3. 应用 "prologue 归一化"（把 mov x29,sp 转回标准位置）后再算匹配率
  4. 报告提升幅度

这不修改实际代码，只做"如果修了会怎样"的测量。
"""
from __future__ import annotations

import argparse

import struct
import subprocess
from pathlib import Path

OBJDUMP = "/opt/homebrew/opt/llvm/bin/llvm-objdump"
OBJCOPY = "/opt/homebrew/opt/llvm/bin/llvm-objcopy"

# 指令编码
STP_X29_X30_PRE = 0xA9BE03FD  # stp x29, x30, [sp, #-0x20]!   (mask 0xFFE003FF)
MOV_X29_SP = 0x910003FD       # mov x29, sp


def read_func(nso: Path, addr: int, length: int) -> bytes:
    data = nso.read_bytes()
    file_off, _dst, size = struct.unpack_from("<III", data, 0x10)
    if addr >= size:
        raise ValueError(f"{addr:#x} out of .text")
    return data[file_off + addr : file_off + addr + length]


def to_elf(raw: bytes, out: Path) -> Path:
    b = Path("/tmp/_mp.bin")
    b.write_bytes(raw)
    out.unlink(missing_ok=True)
    subprocess.run(
        [OBJCOPY, "-I", "binary", "-O", "elf64-littleaarch64", "-B", "aarch64",
         "--rename-section", ".data=.text,alloc,load,readonly,code", str(b), str(out)],
        capture_output=True,
    )
    return out


def words(path: Path) -> list[int]:
    """反汇编取指令编码序列。"""
    out = subprocess.run([OBJDUMP, "-d", str(path)], capture_output=True, text=True).stdout
    res = []
    for line in out.splitlines():
        if "\t" not in line:
            continue
        head = line.split("\t", 1)[0].strip()
        if not head.endswith(":") and ":" not in head:
            continue
        try:
            enc = int(head.split(":", 1)[1].strip(), 16)
        except (ValueError, IndexError):
            continue
        if len(head.split(":", 1)[1].strip()) == 8:  # 只要 4 字节指令
            res.append(enc)
    return res


def disasm_lines(path: Path) -> list[str]:
    out = subprocess.run([OBJDUMP, "-d", str(path)], capture_output=True, text=True).stdout
    res = []
    for line in out.splitlines():
        if "\t" not in line:
            continue
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        txt = parts[1].strip()
        if txt:
            res.append(txt)
    return res


def normalize_prologue(insns: list[int]) -> tuple[list[int], bool]:
    """把 mov x29,sp 移到 stp x29,x30 之后（目标的行为）。返回 (新序列, 是否改动)。"""
    if MOV_X29_SP not in insns:
        return insns, False
    idx = insns.index(MOV_X29_SP)
    # 找到最近的 stp x29,x30
    stp_idx = None
    for i in range(idx - 1, max(-1, idx - 5), -1):
        if (insns[i] & 0xFFE003FF) == 0xA9A003FD or (insns[i] & 0xFFE003FF) == 0xA9BE03FD or (insns[i] & 0xFFE0FFFF) == 0xA98003FD:
            stp_idx = i
            break
        # 也接受 stp 带不同 imm 前缀
        if (insns[i] & 0xFFC003FF) in (0xA98003FD, 0xA9B003FD, 0xA9BE03FD):
            stp_idx = i
            break
    if stp_idx is None:
        return insns, False
    # str x19,[sp,#imm] 紧跟 stp 的话，插入点在它之后
    insert_at = stp_idx + 1
    if insert_at < len(insns) and (insns[insert_at] & 0xFFE003FF) == 0xF90003F3:
        insert_at += 1
    if insert_at == idx:
        return insns, False
    new = insns[:]
    new.pop(idx)
    new.insert(insert_at, MOV_X29_SP)
    return new, True


def score(a: list[int], b: list[int]) -> tuple[int, int]:
    n = max(len(a), len(b))
    m = 0
    for i in range(n):
        x = a[i] if i < len(a) else None
        y = b[i] if i < len(b) else None
        if x is not None and y is not None:
            # bl/b 忽略立即数
            if (x & 0xFC000000) == 0x94000000 and (y & 0xFC000000) == 0x94000000:
                m += 1
                continue
            if x == y:
                m += 1
    return m, n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", type=Path, required=True)
    ap.add_argument("--func-addr", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--func-len", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--clang", default="/opt/homebrew/opt/llvm/bin/clang")
    ap.add_argument("--flags", default="")
    args = ap.parse_args()

    tgt = words(to_elf(read_func(args.target, args.func_addr, args.func_len), Path("/tmp/_tgt.elf")))
    obj = Path("/tmp/_cand.o")
    cmd = [args.clang, "--target=aarch64-none-elf", "-O2", "-mno-implicit-float",
           "-fno-exceptions", "-fno-rtti", "-ffunction-sections", "-c", "-o", str(obj),
           str(args.source)] + args.flags.split()
    if subprocess.run(cmd, capture_output=True).returncode != 0:
        print("编译失败")
        return
    cand_raw = words(obj)

    # 去掉函数末尾 padding（连续的 udf/0）
    while cand_raw and cand_raw[-1] in (0x0, 0xD503201F):
        cand_raw.pop()

    m0, n0 = score(tgt, cand_raw)
    cand_norm, changed = normalize_prologue(cand_raw)
    m1, n1 = score(tgt, cand_norm)

    print(f"目标 {len(tgt)} 条 / 候选 {len(cand_raw)} 条")
    print(f"  原始匹配      : {m0}/{n0} = {m0/n0*100:.1f}%")
    print(f"  prologue 归一后: {m1}/{n1} = {m1/n1*100:.1f}%   (改动={changed})")
    if m1 > m0:
        print(f"  → 提升 {m1-m0} 条")


if __name__ == "__main__":
    main()
