# Splatoon 3 Decomp

Splatoon 3（Switch, AArch64）的**静态逆向与匹配反编译**研究项目。

这是一个独立的个人研究项目，目标是理解游戏内部实现，产出可编译、可验证的
反编译源码。**不包含游戏资产，不能用来玩游戏，不公开分发。**

## 从这里开始

- **接手项目**：先读 [`docs/00-STATUS.md`](docs/00-STATUS.md) —— 进度总览、
  已验证事实、下一步、已知问题
- **用工具**：见 [`scripts/README.md`](scripts/README.md)
- **理解路线**：见 [`docs/02-project-roadmap.md`](docs/02-project-roadmap.md)

## 当前状态（2026-10-16）

**Phase 0 完成：提取链路打通 + 编译器工具链反推成功 + 匹配验证闭环成立。**

### 验证一：二进制身份

```text
系统运行时 (sys-botbase) : 28c4287aee36f749
提取的 11.3.0 main       : 28c4287aee36f749    ✅
```

### 验证二：能复现 Nintendo 的编译结果（关键）

用 zlib 1.2.11 的已知源码编译，在游戏 `.text` 里自动定位并逐指令比对
（29 个函数）：

| 区间 | 函数数 | 占比 |
|------|-------|------|
| **100%（零真差异）** | 7 | 24% |
| 99–100% | 1 | 3% |
| 90–99% | 18 | 62% |
| < 90% | 3 | 10% |

**平均实质匹配 95.2%，中位数约 95%。**

确认的编译器配置（**`-fomit-frame-pointer` 是关键**）：

```bash
clang 17.0.6 --target=aarch64-none-elf -O3 -mcpu=cortex-a57 -fomit-frame-pointer
```

去掉 `-fomit-frame-pointer` 平均分会从 95.2% 掉到 82.8%。

**对抗性验证**：把 `adler32.c` 的 `>=` 改成 `>` 重新编译，比对器检出 36 处
真差异（100% → 85%）——判据不是橡皮图章。

详见 `docs/05`、`docs/06`、`docs/07`。

### 意义

上游 clang 能复现 95%+ 的原生代码，**匹配反编译路线成立**。剩余差异以
**调度顺序**为主（同样的指令换了位置），少量是真代码差异（个例 `deflate` 68%）。

需要正视的一点：**函数越大越难匹配**（`crc32_z` 212 条 100%，`deflate` 900 条 68%）。
这个趋势是匹配反编译的固有特性，objdiff 用百分比而非二值正是这个原因。

**下一步是校准游戏自身代码的编译配置**（它的选项与库代码不同）。

## 目录结构

```text
binaries/       游戏可执行文件（受版权保护，gitignore）
  11.3.0/       分析主目标 = 运行中的版本
  base-v0/      本体版本，用于差分对照
romfs/          游戏 RomFS（参数、资源，9.4G，gitignore；不需可删）
symbols/        导出的符号库种子（入库 —— 这是我们的产出）
tools/
  sysroot/      最小 freestanding 头文件集（编译第三方库用）
  toolchain-samples/  已确认的编译器配置与样本
  bin/          hactool、nstool（gitignore，需自行编译）
  keys/         清理后的 key（gitignore，绝不入库）
scripts/        工具（见 scripts/README.md）
docs/           研究笔记（00-STATUS.md 是入口）
work/           临时工作区（gitignore）
```

## 关键事实

### 目标版本

运行中的是 **11.3.0**，所以静态分析必须对准它。本体 v0 的 main 是
`19fe149d2955756c`，**不能用来匹配运行时**。

### NSO 格式（标准布局）

```text
main (11.3.0, NSO0, LZ4, flags=0x3f)
  解压后 100.69 MB
    text   82.38 MB
    rodata 82.38 MB
    data   50.10 MB
  build_id 28c4287aee36f749
```

### 符号情况（决定难度的核心事实）

| 项 | 数量 | 性质 |
|----|------|------|
| `_ZN` C++ 符号 | 946 | ⚠️ 几乎全是 SDK 的（`nn::`） |
| `spl::` 类名 | **2,027** | ✅ 在 rodata 字符串表里，是真的 |
| `spl__` 参数表名 | **1,855** | ✅ 字符串 |
| `game__` 参数名 | 379 | ✅ 字符串 |
| `game::` 类名 | 92 | ✅ 字符串 |
| `UniqueSequence*` | 345 | ✅ 字符串 |
| 唯一字符串总数 | 81,218 | — |

**游戏自身代码没有 C++ 符号，但类型名和字段名以字符串形式保留在 rodata。**

这些名字来自 NintendoSDK 的反射/属性系统（`PropertyTable` ×160、`Reflection` ×45），
配合 `GameFlow` / `LocalBB` / `UniqueFlow` 数据驱动脚本系统（`GameFlow` ×235）。

这比 botw 的处境差（它有 Wii U 版符号作跳板），但比完全 strip 好得多：
**类名和字段名有，函数名没有。**

### 引擎

自研引擎 + Havok 物理（`hk2021_1_8_PhysicsClothAI` 等字符串）。待确认是否为 LunchPack。

## 复现提取

需要：游戏本体 XCI、11.3.0 更新 NSP、`prod.keys`（自备）。见 `docs/` 与 `scripts/`。

## 边界

提取产物是受版权保护的 Nintendo 代码，仅用于本地研究。不公开分发、不进 git。
