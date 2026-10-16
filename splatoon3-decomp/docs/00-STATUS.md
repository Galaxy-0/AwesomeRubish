# 进度总览

> 最后更新：2026-10-16

## 一句话状态

**Phase 0 完成。** 提取链路打通、编译器工具链反推成功、匹配验证闭环成立
（zlib 29 函数平均 95.2%）。项目已具备开始处理游戏自身代码的条件。

## 里程碑

| 阶段 | 状态 | 关键证据 |
|------|------|---------|
| 提取链路 | ✅ 完成 | Build ID 与运行时完全一致 `28c4287aee36f749` |
| 工具链反推 | ✅ 完成 | `clang 17.0.6 -O3 -mcpu=cortex-a57 -fomit-frame-pointer` |
| 匹配验证闭环 | ✅ 完成 | zlib 29 函数，平均 95.2%，7 个 100% |
| 后处理 | ✅ 基本完成 | 3 个 pass 把 97–99% 推到 100% |
| **游戏自身代码** | ⬜ **未开始** | ← **下一步** |

## 已验证的事实（可依赖）

1. **二进制身份**：`binaries/11.3.0/main.uncompressed` 就是运行时那份
   （Build ID `28c4287aee36f749`，与 sys-botbase 报的一致）。
   本体 v0 是 `19fe149d2955756c`，**不能用来匹配运行时**。

2. **编译器配置**：
   ```
   clang 17.0.6 --target=aarch64-none-elf -O3 -mcpu=cortex-a57 -fomit-frame-pointer
   ```
   去掉 `-fomit-frame-pointer` 平均分从 95.2% 掉到 82.8%。

3. **游戏自身代码的编译选项不同**：全 `.text` 有帧指针（99%），
   但 zlib 区域零帧指针。所以上面的配置**只对库代码正确**，
   游戏自身代码需要相反设置（`-mno-omit-frame-pointer` 或默认）。

4. **符号现状**：游戏自身代码**无 C++ 符号**（函数名全丢），
   但 rodata 保留了 2,027 个 `spl::` 类名 + 1,855 个 `spl__` 参数表名
   （见 `symbols/`）。这是命名的依据。

5. **差异性质**：剩余不匹配以**指令调度**为主（同样指令换位置），
   少量是真代码差异。`deflate`（900 条，68%）是已知长尾个例，原因未定。

## 关键文档

| 文档 | 内容 |
|------|------|
| `docs/02-project-roadmap.md` | 总体路线与 agent 化设计 |
| `docs/03-extraction-verified.md` | 提取实测结果 |
| `docs/04-matching-vs-nonmatching.md` | 为什么选匹配路线（含 SSBU 先例研究） |
| `docs/05-clang-version-findings.md` | 工具链反推全过程（含失败路径） |
| `docs/06-prologue-postprocess.md` | 后处理与 100% 闭环 |
| `docs/07-batch-verification.md` | 29 函数批量验证与 `-fomit-frame-pointer` 发现 |
| `scripts/README.md` | 工具索引与用法 |

## 目录状态

```text
binaries/11.3.0/        分析主目标（gitignore）
binaries/base-v0/       本体版本，差分对照用（gitignore）
romfs/                  游戏 RomFS 9.4G（gitignore；如不需可删，省空间）
symbols/                5,376 个游戏自有名字 ← 核心产出，入库
tools/sysroot/          最小 freestanding 头文件集
tools/toolchain-samples/ 已确认配置 + 样本
work/text/text.bin      .text 段提取（gitignore，可由 extract 流程重建）
scripts/                活跃工具 + archived/
```

## 下一步（按优先级）

### 1. 校准游戏自身代码的编译配置 ← 最优先

库代码只是标尺，**真正目标是游戏自身代码**。已知它的编译选项与库不同
（帧指针相反）。用同样的批量方法快速确定：

- 挑几个 `spl::` 类对应的函数（可从 `symbols/spl-classes.txt` 挑简单名字）
- 用 `batch_verify.py` 试不同 flag 组合
- 难点：游戏代码没有已知源码，所以**不能像 zlib 那样直接比对**。
  可行的办法：
  - 先找游戏里**内嵌的第三方代码**（Havok？OpenSSL 有源码）
  - 或用「已知编译器行为」推断（比如帧指针、常量编码模式）

### 2. 决定验证工具路线

当前自制的比对器可用，但社区标准是 **objdiff**。二选一：
- 继续用自制工具（已熟悉，但需要自己维护等价类规则）
- 接 objdiff（标准、UI 好、社区通用，但要搭构建系统）

**这个决定影响是否值得实现真实 ELF 改写。**

### 3. 扩大第三方库样本

- OpenSSL 1.1.1w 源码已下载（`/tmp/openssl-test/`，需更完整的 sysroot）
- Havok 有 76 条源码路径线索，但源码不公开

### 4. 开始游戏代码的骨架恢复（Phase 1）

用 Ghidra + `symbols/` 的类名，建立子系统地图。

## 已知问题 / 待解

| 问题 | 影响 | 状态 |
|------|------|------|
| `deflate` 68% | 长尾个例 | 原因未定；已否证 `ZLIB_DEBUG` 假设 |
| 游戏代码编译选项未知 | 阻塞 Phase 1 | 待校准 |
| `postprocess.py` 不真正改写 `.o` | 无法产出最终产物 | 待实现，优先级取决于验证工具选择 |
| OpenSSL 编译缺 libc | 样本来源受限 | 需扩充 `tools/sysroot/` |
| `romfs/` 占 9.4G | 磁盘 | 如不需可删 |

## 复现验证（确认工具链仍可用）

```bash
# 1. 确认二进制在位
ls -la binaries/11.3.0/main.uncompressed

# 2. 确认 .text 提取（如 work/ 被清过需重建）
python3 -c "
import struct
d=open('binaries/11.3.0/main.uncompressed','rb').read()
fo,dst,sz,tot=struct.unpack_from('<IIII',d,0x10)
open('/tmp/t.bin','wb').write(d[fo:fo+sz])
print('text size', hex(sz))"

# 3. 快速比对一个已知 100% 的函数（需先按 toolchain-samples 重建 trees.o）
python3 scripts/compare_func.py --text work/text/text.bin --addr 0x1dc6d0 \
  --obj tools/toolchain-samples/zlib-v17o3/trees.o --func _tr_flush_bits
# 期望：实质匹配率 100.0%
```

## 边界（不变）

只做私有、离线、自有文件的实验。反编译产物**不公开分发**。
本项目的定位是研究/互操作性/理解游戏内部，不是作弊器或盗版工具。
