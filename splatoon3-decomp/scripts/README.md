# 工具索引

## 活跃工具（scripts/）

按典型工作流顺序：

| 脚本 | 用途 | 典型用法 |
|------|------|---------|
| `extract.sh` | 从游戏文件提取 `main`（XCI + NSP → NSO） | `./scripts/extract.sh <base.xci> <update.nsp>` |
| `export_symbols.py` | 从 `main.uncompressed` 导出类名/字段名 | `python3 scripts/export_symbols.py binaries/11.3.0/main.uncompressed -o symbols` |
| `compare_func.py` | **单函数**比对（含三类等价关系） | 见下 |
| `batch_verify.py` | **批量**验证：在目标里自动定位并判分 | 见下 |
| `postprocess.py` | 后处理：把候选修成目标形式 | 见下 |

### compare_func.py —— 单函数比对

判断一个已知源码编译出的函数是否与目标一致。

```bash
python3 scripts/compare_func.py \
  --text work/text/text.bin \
  --addr 0x1dc450 \
  --obj /tmp/zlib-test/final/trees.o \
  --func init_block
```

输出把差异分成五类，**这是理解匹配率的关键**：

| 类别 | 含义 | 是否算差异 |
|------|------|-----------|
| 完全匹配 | 字节一致 | 否 |
| 重定位占位 | `.o` 里是未链接占位符 | 否 |
| adrp+add | 取地址对，链接后等价 | 否 |
| padding | `nop` vs `0` 的对齐填充 | 否 |
| 顺序交换对 | 同两条指令颠倒，语义等价 | 否 |
| **真差异** | 其余 | **是** |

### batch_verify.py —— 批量验证

把一批 `.o` 里的所有函数在目标 `.text` 里自动定位并判分。**这是扩大验证
规模的主力工具。**

```bash
python3 scripts/batch_verify.py \
  --text work/text/text.bin \
  --objs '/tmp/zlib-test/final/*.o' \
  --window 16 \
  --out /tmp/report.json
```

**注意**：在 20M 条指令上建索引约需 2–3 分钟，建议后台跑：

```bash
nohup python3 scripts/batch_verify.py ... > /tmp/batch.log 2>&1 &
```

两个关键机制（少了会漏掉大量函数）：
- **多窗口探测**：不用函数开头做指纹（prologue 差异会破坏它），
  而是开头/中部/靠尾多个窗口分别查
- **局部对齐微调**：命中位置 ±6 条指令内搜索最佳对齐

### postprocess.py —— 后处理

链式 4 个 pass，把 97–99% 推到 100%：

```bash
python3 scripts/postprocess.py \
  --text work/text/text.bin --addr 0x1dc450 \
  --obj /tmp/zlib-test/final/trees.o --func init_block
```

**当前限制**：只做**内存态验证**（证明"修了会到 100%"），不真正改写 `.o`。
真实 ELF 改写留作后续工作（可能需要先决定是否改用 objdiff）。

## 归档工具（scripts/archived/）

早期版本，已被上面的工具取代，保留作为参考和演进记录：

| 脚本 | 被谁取代 | 说明 |
|------|---------|------|
| `match_probe.py` | `compare_func.py` | 第一版单函数比对，等价类不全 |
| `measure_prologue_fix.py` | `postprocess.py` | 只测 prologue 一种修复 |
| `find_known_funcs.py` | `batch_verify.py` | 只搜已知函数的精确指纹，漏检多 |

## 辅助资源（tools/）

| 路径 | 内容 |
|------|------|
| `tools/sysroot/include/` | 最小 freestanding 头文件集（编译 zlib/OpenSSL 用，目标平台无 libc） |
| `tools/toolchain-samples/README.md` | 已确认的编译器配置 + 复现步骤 |
| `tools/toolchain-samples/zlib-v17o3/*.o` | 用最佳配置编译的 zlib 产物（gitignore，可复现） |
| `tools/bin/` | hactool / nstool（gitignore，需自行编译） |
| `tools/keys/` | 清理后的 prod.keys（**gitignore，绝不入库**） |

## 环境依赖

```text
brew install llvm@17          # 编译器（版本关键）
/opt/homebrew/opt/llvm@17/bin/clang
```

比对时还需要 `llvm-objdump` / `llvm-readelf`（brew llvm 自带）。

## 编造最小 sysroot 的原因

目标平台是 Switch（无 libc），而 zlib/OpenSSL 需要标准头文件。
`tools/sysroot/include/` 提供最小替身，配合 `-ffreestanding -nostdinc` 使用。

如果编译别的库遇到缺头文件，照 `tools/sysroot/include/` 里的样式补即可
（大多是空壳声明，因为只编译不求链接）。
