#!/usr/bin/env python3
"""编译器匹配试验台。

把一份 C 源码用不同 clang 版本/flags 编译，和目标二进制的某个函数逐指令对比，
给出匹配率。这是 Phase 0 的核心工具：它把"编译器版本反推"变成可量化的问题。

用法:
    python3 match_probe.py --target binaries/11.3.0/main.uncompressed \
        --func-addr 0x17d8 --func-len 0x38 --source work/match/probe1.c

设计要点:
  - 忽略 BL 的立即数（重定位未解析），只比 opcode
  - 忽略 ADRP 的立即数（同理）
  - 报告逐条 diff，方便人判断是"调度差异"还是"真的写错了"
"""
from __future__ import annotations

import argparse
import struct
import subprocess
import sys
from pathlib import Path

# 需要忽略立即数的指令（重定位相关）
RELOC_OPCODES = {
    "bl", "b", "adrp", "add",  # add 用于 adrp+add 取地址
}


def read_target_func(nso_path: Path, addr: int, length: int) -> bytes:
    """从解压后的 NSO 读函数字节。text 段 file_off=0x100, dst_off=0。"""
    data = nso_path.read_bytes()
    text_file_off, _text_dst_off, text_size = struct.unpack_from("<III", data, 0x10)
    if addr < text_size:
        start = text_file_off + addr
        return data[start : start + length]
    raise ValueError(f"地址 {addr:#x} 超出 .text ({text_size:#x})")


def disasm_with_encoding(binary_path: Path) -> list[tuple[int, int, str]]:
    """返回 [(offset, encoding, text)]。

    llvm-objdump 的行格式是:  "       0: a9be7bfd     \\tstp\\tx29, x30, ..."
    ——偏移和编码之间是空格，编码和文本之间是 tab。所以先按 tab 切。
    """
    objdump = _find_objdump()
    out = subprocess.run(
        [objdump, "-d", str(binary_path)], capture_output=True, text=True
    ).stdout
    rows = []
    for line in out.splitlines():
        if "\t" not in line:
            continue
        head, txt = line.split("\t", 1)
        head = head.strip()
        if not head.endswith(":") is False and ":" not in head:
            continue
        try:
            off = int(head.split(":")[0].strip(), 16)
            enc = int(head.split(":", 1)[1].strip(), 16)
        except (ValueError, IndexError):
            continue
        rows.append((off, enc, txt.strip()))
    return rows


def _find_objdump() -> str:
    for cand in (
        "/opt/homebrew/opt/llvm/bin/llvm-objdump",
        "/opt/homebrew/opt/llvm@20/bin/llvm-objdump",
    ):
        if Path(cand).exists():
            return cand
    return "llvm-objdump"


def norm_mnemonic(text: str) -> str:
    """取助记符 + 操作数结构（丢弃立即数值，保留寄存器）。"""
    # 去掉注释
    text = text.split("//")[0].strip()
    if not text:
        return ""
    parts = text.split(None, 1)
    mnem = parts[0]
    ops = parts[1] if len(parts) > 1 else ""
    # 对重定位类指令，只保留助记符和寄存器名
    if mnem in ("bl", "b", "adrp"):
        # 去掉数值目标
        ops = parts[1].split(",")[0].strip() if len(parts) > 1 else ""
        if mnem == "adrp":
            ops = ops.split(",")[0] if "," in ops else ops
    return f"{mnem}\t{ops}"


def compare(target: list[tuple[int, int, str]], cand: list[tuple[int, int, str]]):
    """逐条对比，返回 (匹配数, 总数, diff列表)。

    对重定位类指令（bl/b/adrp）忽略立即数，只比助记符和目标寄存器：
    不同链接顺序下这些立即数本来就不一样，不该算作不匹配。
    """
    diffs = []
    n = max(len(target), len(cand))
    matched = 0
    for i in range(n):
        t = target[i] if i < len(target) else None
        c = cand[i] if i < len(cand) else None
        if t is None or c is None:
            diffs.append((i, t, c))
            continue
        if _same_insn(t[2], c[2]):
            matched += 1
        else:
            diffs.append((i, t, c))
    return matched, n, diffs


def _same_insn(a: str, b: str) -> bool:
    """判断两条指令是否"实质相同"（忽略重定位立即数、注释、跳转目标）。"""
    ma, oa = _split(a)
    mb, ob = _split(b)
    if ma != mb:
        return False
    # 分支/取址类：忽略地址部分
    if ma in ("bl", "b", "adrp", "adr"):
        return True
    # 其余按操作数字符串比（已在 _split 里去掉注释与本地标签）
    return oa == ob


def _split(text: str) -> tuple[str, str]:
    text = text.split("//")[0].strip()
    if not text:
        return "", ""
    parts = text.split(None, 1)
    mnem = parts[0]
    ops = parts[1] if len(parts) > 1 else ""
    # 去掉 "<...>" 形式的符号标注
    if "<" in ops:
        ops = ops.split("<")[0].strip().rstrip(",").strip()
    return mnem, ops


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", type=Path, required=True, help="解压后的 NSO")
    ap.add_argument("--func-addr", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--func-len", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--obj", type=Path, default=Path("/tmp/match_probe.o"))
    ap.add_argument(
        "--clang", default="/opt/homebrew/opt/llvm/bin/clang", help="clang 路径"
    )
    ap.add_argument("--flags", default="", help="额外编译 flags")
    args = ap.parse_args()

    target_bytes = read_target_func(args.target, args.func_addr, args.func_len)

    # 目标反汇编：裸二进制 -> ELF（写到独立文件，不要原地覆盖）
    raw_bin = Path("/tmp/_target_func.bin")
    tmp_elf = Path("/tmp/_target_func.elf")
    raw_bin.write_bytes(target_bytes)
    tmp_elf.unlink(missing_ok=True)
    subprocess.run(
        [
            "/opt/homebrew/opt/llvm/bin/llvm-objcopy",
            "-I", "binary", "-O", "elf64-littleaarch64", "-B", "aarch64",
            "--rename-section", ".data=.text,alloc,load,readonly,code",
            str(raw_bin), str(tmp_elf),
        ],
        capture_output=True,
    )
    target_dis = disasm_with_encoding(tmp_elf)

    # 编译候选
    cmd = [
        args.clang, "--target=aarch64-none-elf", "-O2",
        "-mno-implicit-float", "-fno-exceptions", "-fno-rtti",
        "-ffunction-sections", "-c", "-o", str(args.obj), str(args.source),
    ] + args.flags.split()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("编译失败:", r.stderr[:400])
        sys.exit(1)

    cand_dis = disasm_with_encoding(args.obj)
    matched, total, diffs = compare(target_dis, cand_dis)

    print(f"匹配: {matched}/{total} = {matched/total*100:.1f}%")
    if diffs:
        print("\n差异:")
        for i, t, c in diffs[:15]:
            t_s = f"{t[2]}" if t else "(缺失)"
            c_s = f"{c[2]}" if c else "(多余)"
            print(f"  [{i:2d}] 目标: {t_s:44s} | 候选: {c_s}")


if __name__ == "__main__":
    main()
