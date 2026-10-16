#!/usr/bin/env python3
"""批量匹配验证：把一组已知源码编译后，在目标二进制里自动定位并判定匹配率。

这是"扩大验证规模"的主力工具。流程：
  1. 编译给定的源文件（用已确认的工具链配置）
  2. 拆出每个函数
  3. 用函数入口的前 N 条指令（归一化后）在目标 .text 里做指纹索引查找
  4. 命中后做全函数比对（含三类等价关系）
  5. 汇总统计

用法:
    python3 batch_verify.py --text work/text/text.bin \
        --objs 'tools/toolchain-samples/zlib-v17o3/*.o' \
        --target-dumps /tmp/dumps/   # 可选：预先 dump 的目标函数位置

判定口径（与 compare_func.py 一致）：
  - adrp 取址对：重定位占位，非差异
  - 尾部对齐填充：非差异
  - 相邻 store 顺序交换：语义等价
  - 其余不同 = 真差异
"""
from __future__ import annotations

import argparse
import glob
import json
import struct
import subprocess
from collections import defaultdict
from pathlib import Path

OBJDUMP = "/opt/homebrew/opt/llvm/bin/llvm-objdump"
OBJDUMP17 = "/opt/homebrew/opt/llvm@17/bin/llvm-objdump"


# ---------- 指令等价判定 ----------

def is_branch(w: int) -> bool:
    return (
        (w & 0xFC000000) in (0x14000000, 0x94000000)
        or (w & 0xFF000010) == 0x54000000
        or (w & 0x7E000000) in (0x34000000, 0x36000000)
    )


def is_padding(w: int) -> bool:
    return w in (0x00000000, 0xD503201F)


def is_addr_use(w: int) -> bool:
    if (w & 0xFF800000) == 0x91000000:
        return True
    if (w & 0xFFC00000) in (0xF9400000, 0xB9400000, 0x39400000, 0x79400000,
                            0xF9000000, 0xB9000000, 0x39000000, 0x79000000):
        return True
    if (w & 0x3F000000) == 0x3D000000:
        return True
    return False


def classify(g: int, c: int, gi: int, ci: int, gt: list[int], ct: list[int]) -> str:
    """返回 match / reloc / pad / swap / real。"""
    if g == c:
        return "match"
    if is_padding(g) and is_padding(c):
        return "pad"

    # adrp 取址对
    if (ct[ci] & 0x9F000000) == 0x90000000 and (gt[gi] & 0x9F000000) == 0x90000000:
        if ci + 1 < len(ct) and gi + 1 < len(gt):
            c1, g1 = ct[ci + 1], gt[gi + 1]
            if (
                is_addr_use(c1) and is_addr_use(g1)
                and (c1 & 0xFF000000) == (g1 & 0xFF000000)
                and ((c1 >> 5) & 0x1F) == (ct[ci] & 0x1F)
                and ((g1 >> 5) & 0x1F) == (gt[gi] & 0x1F)
            ):
                return "reloc"
    # adrp 对的第二条
    if ci > 0 and gi > 0:
        c0, g0 = ct[ci - 1], gt[gi - 1]
        if (c0 & 0x9F000000) == 0x90000000 and (g0 & 0x9F000000) == 0x90000000:
            if (
                is_addr_use(c) and is_addr_use(g)
                and (c & 0xFF000000) == (g & 0xFF000000)
                and ((c >> 5) & 0x1F) == (c0 & 0x1F)
                and ((g >> 5) & 0x1F) == (g0 & 0x1F)
            ):
                return "reloc"

    # 分支：只比 opcode 高字节 + 寄存器
    if is_branch(g) and is_branch(c):
        if (g >> 24) == (c >> 24) and (g & 0x1F) == (c & 0x1F):
            return "match"
        return "real"

    # 相邻交换
    if ci + 1 < len(ct) and gi + 1 < len(gt):
        if ct[ci] == gt[gi + 1] and ct[ci + 1] == gt[gi]:
            if not is_branch(ct[ci]) and not is_branch(ct[ci + 1]):
                return "swap"
    return "real"


# ---------- 反汇编 ----------

def obj_functions(path: Path) -> dict[str, tuple[list[int], list[int]]]:
    """返回 {函数名: ([编码], [段内偏移])}。"""
    out = subprocess.run([OBJDUMP, "-d", str(path)], capture_output=True, text=True).stdout
    funcs: dict[str, tuple[list[int], list[int]]] = {}
    cur = None
    encs: list[int] = []
    offs: list[int] = []
    for line in out.splitlines():
        s = line.strip()
        if s.endswith(">:") and "<" in s:
            if cur:
                funcs[cur] = (encs, offs)
            cur = s.split("<")[-1].rstrip(">:").strip()
            encs, offs = [], []
            continue
        if "\t" in line and cur is not None:
            head = line.split("\t", 1)[0].strip()
            try:
                off = int(head.split(":", 1)[0].strip(), 16)
                enc = int(head.split(":", 1)[1].strip(), 16)
            except (ValueError, IndexError):
                continue
            encs.append(enc)
            offs.append(off)
    if cur:
        funcs[cur] = (encs, offs)
    return funcs


def norm_for_index(w: int) -> int:
    """指纹归一化：抹掉分支目标和重定位立即数。"""
    if is_branch(w):
        return (w & 0xFF000000) | (w & 0x1F)
    if (w & 0x9F000000) == 0x90000000:      # adrp
        return (w & 0x9F000000) | (w & 0x1F)
    if (w & 0x7F800000) == 0x32000000:      # orr imm
        return (w & 0x7F800000) | (w & 0x1F)
    return w & 0xFFE0FC00 | (w & 0x1F)      # 通用：opcode + Rd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", type=Path, required=True)
    ap.add_argument("--objs", required=True, help="glob")
    ap.add_argument("--window", type=int, default=16)
    ap.add_argument("--out", type=Path, help="JSON 报告输出")
    args = ap.parse_args()

    data = args.text.read_bytes()
    n = len(data) // 4
    GW = [struct.unpack_from("<I", data, i * 4)[0] for i in range(n)]

    W = args.window
    # 建索引（只索引每个位置，用归一化指纹）
    print(f"建索引（{n:,} 条指令，窗口 {W}）...")
    idx: dict[tuple, list[int]] = defaultdict(list)
    for i in range(0, n - W):
        idx[tuple(norm_for_index(GW[i + j]) for j in range(W))].append(i)
    print(f"  唯一指纹数: {len(idx):,}")

    results = []
    files = sorted(glob.glob(args.objs))
    print(f"待测文件: {len(files)}")

    # 探针窗口：不能只用函数开头——prologue 调度差异会破坏开头的指纹。
    # 用多个窗口分别查找，取命中率最高的对齐位置。
    def probe_offsets(total: int) -> list[int]:
        cands = {0}
        for w_start in (16, 24, 32, 48):
            if w_start + W <= total:
                cands.add(w_start)
        if total >= W * 2:
            cands.add((total - W) // 2)   # 中部
        if total >= W + 8:
            cands.add(total - W - 4)      # 靠尾
        return sorted(c for c in cands if c + W <= total)

    for p in files:
        pname = Path(p).stem
        for fname, (encs, offs) in obj_functions(Path(p)).items():
            if len(encs) < W + 4 or len(encs) > 8000:
                continue
            total = len(encs)

            def score_at(start: int):
                """在给定起点算真差异数；越界返回 None。"""
                if start < 0 or start + total > n:
                    return None
                G = [GW[start + j] for j in range(total)]
                counts = defaultdict(int)
                real_idx = []
                for j in range(total):
                    k = classify(G[j], encs[j], j, j, G, encs)
                    counts[k] += 1
                    if k == "real":
                        real_idx.append(j)
                return {
                    "file": pname, "func": fname, "addr": start * 4, "len": total,
                    "exact": counts["match"], "reloc": counts["reloc"],
                    "pad": counts["pad"], "swap": counts["swap"],
                    "real": counts["real"],
                    "effective_pct": (total - counts["real"]) / total * 100,
                    "real_idx": real_idx[:20],
                }

            best = None
            for wr in probe_offsets(total):
                key = tuple(norm_for_index(x) for x in encs[wr:wr + W])
                for off in idx.get(key, [])[:4]:
                    guess = off - wr
                    # 局部对齐微调：真实入口可能差几条指令
                    for delta in range(-6, 7):
                        cand = score_at(guess + delta)
                        if cand is None:
                            continue
                        if best is None or cand["real"] < best["real"]:
                            best = cand
                    if best and best["real"] == 0:
                        break
                if best and best["real"] == 0:
                    break
            if best:
                results.append(best)

    results.sort(key=lambda r: -r["effective_pct"])
    print(f"\n找到 {len(results)} 个函数匹配\n")
    print(f"{'实质匹配':>8s} {'长度':>5s} {'真差异':>6s}  {'文件':16s} {'函数':34s} {'地址':>10s}")
    print("-" * 92)
    for r in results[:50]:
        print(f"{r['effective_pct']:7.1f}% {r['len']:5d} {r['real']:6d}  "
              f"{r['file']:16s} {r['func']:34s} {r['addr']:#10x}")

    # 汇总
    if results:
        perfect = sum(1 for r in results if r["real"] == 0)
        avg = sum(r["effective_pct"] for r in results) / len(results)
        print(f"\n=== 汇总 ===")
        print(f"  总函数数     : {len(results)}")
        print(f"  零真差异     : {perfect} ({perfect/len(results)*100:.1f}%)")
        print(f"  平均实质匹配 : {avg:.2f}%")
        bins = {"=100%": 0, ">=99%": 0, ">=95%": 0, ">=90%": 0, "<90%": 0}
        for r in results:
            p = r["effective_pct"]
            if p >= 99.999: bins["=100%"] += 1
            elif p >= 99: bins[">=99%"] += 1
            elif p >= 95: bins[">=95%"] += 1
            elif p >= 90: bins[">=90%"] += 1
            else: bins["<90%"] += 1
        for k, v in bins.items():
            print(f"    {k:8s}: {v}")

    if args.out:
        args.out.write_text(json.dumps(results, indent=2))
        print(f"\n报告写入 {args.out}")


if __name__ == "__main__":
    main()
