# 已确认可匹配的编译器配置与样本

## 配置（Phase 0 反推结果）

```bash
brew install llvm@17
clang-17 --target=aarch64-none-elf -O3 -mcpu=cortex-a57 \
  -ffreestanding -nostdinc -isystem tools/sysroot/include -I<zlib> \
  -c -o out.o <file>.c
```

## 匹配结果（zlib 1.2.11）

| 函数 | 长度 | 匹配率 |
|------|------|--------|
| `_tr_flush_bits` | 36 | 100.0% |
| `crc32_z` | 212 | 99.5% |
| `adler32_z` | 240 | 99.2% |
| `build_tree` | 552 | 99.1% |

合计 1032/1040 = **99.2%**。

> **后续修正**：这 6 个是简单样本。扩大到 29 个函数后平均 **95.2%**，
> 且配置需要加 `-fomit-frame-pointer`。见 `docs/07-batch-verification.md`。

## 复现步骤

```bash
# 1. 下载 zlib 1.2.11
curl -sL https://zlib.net/fossils/zlib-1.2.11.tar.gz | tar xz

# 2. 编译（用上面的配置）
# 3. 用 scripts/match_probe.py 或 find_known_funcs.py 比对
```

`zlib-v17o3/*.o` 是用上述配置编译出的产物，保留用于复现验证。
`sysroot/` 是最小 freestanding 头文件集（编译 zlib 需要，因为目标平台没有 libc）。

## 更新（2026-10-16 批量验证后）

**配置中必须包含 `-fomit-frame-pointer`：**

```bash
clang-17 --target=aarch64-none-elf -O3 -mcpu=cortex-a57 -fomit-frame-pointer \
  -ffreestanding -nostdinc -isystem tools/sysroot/include -I<src> -c -o out.o <file>.c
```

原因：游戏里 zlib 区域**零帧指针**（而游戏自身代码 99% 有帧指针）。
不加这个 flag，平均匹配率会从 95.2% 掉到 82.8%。

**29 个 zlib 函数的匹配率分布**：100% × 7，90–99% × 18，<90% × 3（详见 docs/07）。

**已否证**：`-DZLIB_DEBUG`（会让匹配率掉到 73.9%）。
