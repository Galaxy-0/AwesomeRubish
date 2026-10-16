#!/usr/bin/env python3
"""从解压后的 main NSO 里导出符号库种子。

NintendoSDK 的反射系统把类型名和字段名作为字符串保留在 rodata 里。
这个脚本把它们抽出来，作为后续命名反编译产物的依据。

用法:
    python3 export_symbols.py <main.uncompressed> -o symbols/
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# 游戏自有命名空间前缀 —— 这些是真正有价值的（非 SDK）
GAME_PREFIXES = {
    "spl::": "类名 (RTTI/反射)",
    "spl__": "参数表/属性表名",
    "game::": "类名",
    "game__": "参数名",
    "UniqueSequence": "序列类",
    "UniqueFlow": "数据流节点",
    "UniqueNode": "数据流节点",
    "GameSeq": "游戏序列",
    "Coop": "Salmon Run",
    "Msn_": "单机/英雄模式",
    "Plz_": "广场",
    "LayoutMsg/": "UI",
}

# SDK 命名空间 —— 识别出来但单独归类
SDK_PREFIXES = ("nn::", "nn__", "nv::", "hk", "hkx", "hkp", "hcl", "nvn", "NintendoSdk")

MANGLED = re.compile(rb"_Z[A-Za-z0-9_]{4,}")
PRINTABLE = re.compile(rb"[ -~]{4,}")


def load_strings(path: Path) -> list[str]:
    raw = path.read_bytes()
    return [m.decode("latin1") for m in PRINTABLE.findall(raw)]


def classify(strings: list[str]) -> dict:
    uniq = sorted(set(strings))
    buckets: dict[str, list[str]] = {k: [] for k in GAME_PREFIXES}
    sdk: list[str] = []

    for s in uniq:
        matched = False
        for p in GAME_PREFIXES:
            if s.startswith(p):
                buckets[p].append(s)
                matched = True
                break
        if not matched and s.startswith(SDK_PREFIXES):
            sdk.append(s)

    return {
        "total_unique_strings": len(uniq),
        "game_buckets": {k: v for k, v in buckets.items() if v},
        "game_names_total": sum(len(v) for v in buckets.values()),
        "sdk_string_count": len(sdk),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("binary", type=Path, help="解压后的 main（NSO, 未压缩）")
    ap.add_argument("-o", "--out", type=Path, default=Path("symbols"))
    args = ap.parse_args()

    strings = load_strings(args.binary)
    result = classify(strings)

    args.out.mkdir(parents=True, exist_ok=True)

    # 每个命名空间一个清单文件，方便 review
    for prefix, names in result["game_buckets"].items():
        safe = prefix.replace("::", "-classes-").replace("__", "-params-")
        safe = safe.replace("/", "-").strip("-")
        (args.out / f"{safe}.txt").write_text("\n".join(names) + "\n", encoding="utf-8")

    (args.out / "summary.json").write_text(
        json.dumps(
            {
                "source": args.binary.name,
                "total_unique_strings": result["total_unique_strings"],
                "game_names_total": result["game_names_total"],
                "sdk_string_count": result["sdk_string_count"],
                "buckets": {k: len(v) for k, v in result["game_buckets"].items()},
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"总唯一字符串: {result['total_unique_strings']}")
    print(f"游戏自有名合计: {result['game_names_total']}")
    print("分类:")
    for k, v in result["game_buckets"].items():
        print(f"   {k:18s} {GAME_PREFIXES[k]:20s} {len(v)}")
    print(f"\n输出到 {args.out}/")


if __name__ == "__main__":
    main()
