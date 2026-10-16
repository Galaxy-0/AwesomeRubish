# 2026-10-16 · 11.3.0 提取实测结果（决定性验证）

## 结论先行

**链路打通了，而且拿到了正确的二进制。** 运行时 Build ID 与提取出的 `main` 完全一致：

```text
系统运行时 (sys-botbase) : 28c4287aee36f749
提取的 11.3.0 main       : 28c4287aee36f749   ✅ 完全匹配
```

本体 v0 的 main 是 `19fe149d2955756c`（不同），所以**必须用 11.3.0 更新包**——
运行中的版本是 11.3.0，静态分析必须对准它。

## 环境与工具链（已实测可用）

| 工具 | 状态 | 用途 |
|------|------|------|
| hactool | ✅ 源码编译（`/tmp/hactool-build/hactool/hactool`） | NSP/XCI/NCA 提取、NSO 解压 |
| nstool | ✅ 源码编译（`/tmp/nstool/bin/nstool`） | **BKTR patch 处理**（hactool 做不到） |
| mbedtls@2 | ✅ brew 安装 | hactool 依赖 |
| pycryptodome | ✅ venv（`/tmp/vcrypt`） | 手工 NCA 解析 |

### 暗坑一：key 文件有畸形行

`~/.switch/prod.keys` 里有 33 个键**多带了尾部 `00`**（34 位 hex），hactool 解析时
直接报错退出：

```text
Key (77605ad2ee6ef83c3f72e2599dac5e5600) must be 32 hex digits!
```

受影响的是 `mariko_master_kek_source_05..15` 和 `master_kek_source_06..15`。
**这些键解密游戏内容根本用不到**（只用于主机密钥派生）。清理副本在
`/tmp/keys-clean/prod.keys`（198 行，丢掉 33 个畸形键，保留 RSA 长键）。

注意：hactool 即使传了 `-k` 也会先尝试加载 `~/.switch/prod.keys`，所以要么修原文件，
要么确保传的是干净的。

### 暗坑二：hactool 不能处理分段 BKTR

11.3.0 更新包的主 NCA 是 **BKTR patch 格式**（7.2GB，分段、需要 base NCA 重建）。
hactool 报 `Invalid BKTR layout!` 直接退出。**nstool 可以**：

```bash
/tmp/nstool/bin/nstool -k /tmp/keys-clean/prod.keys \
  --basenca /tmp/base-xci/f6e46265849db31008d3de7091299d7c.nca \
  -x / /tmp/patch-out \
  /tmp/nca-extract/b17c38424e33cec90d4407ef33c7848d.nca
```

耗时约 3 分钟，产出 `/tmp/patch-out/0/`（程序）和 `/tmp/patch-out/1/`（RomFS）。

关键元数据（nstool 读出）：

```text
Key Generation:  14        ← 用 master_key_14 派生，你手上的 key 够
SdkAddon Ver.:   20.5.22
RightsId:        0100C2500FC20800000000000000000E
```

## 提取产物

```text
/tmp/patch-out/0/main        51.86 MB  (NSO0, LZ4 压缩)   ← 游戏主程序 ✅
/tmp/patch-out/0/main.npdm   1.6 KB
/tmp/patch-out/0/rtld        10 KB
/tmp/patch-out/0/sdk         6.2 MB
/tmp/patch-out/1/            RomFS（游戏参数、资源）      ← 意外收获
```

解压后（`hactool -t nso0 --uncompressed`）：

```text
main.uncompressed  = 100.69 MB    (11.3.0)
   text   82.38 MB
   rodata 82.38 MB
   data   50.10 MB
```

（本体 v0 对照：91.99 MB。）

## 决定性发现：符号情况

**好消息与坏消息都很明确：**

| 项 | 数量 | 说明 |
|----|------|------|
| `_ZN` C++ 符号（11.3.0） | **946** | 且**几乎全是 SDK 的**（`nn::` 命名空间） |
| `spl::` 类名 | **2,027** | ⚠️ 在**字符串表**里，不是符号 |
| `spl__` 参数表名 | **1,855** | 同上，字符串 |
| `game::` / `game__` | 92 / 379 | 同上 |
| `UniqueSequence*` | 345 | 同上 |
| 唯一字符串总数 | **81,218** | 巨大 |

**判定**：游戏自己的代码**没有 C++ 符号**（没被保留 mangled name）。但我们有
**2,027 个 `spl::` 类名 + 1,855 个 `spl__` 参数表名 + 379 个 `game__` 参数名**，
它们以字符串形式存在于 `rodata`。

这些名字来自 NintendoSDK 的**反射/属性系统**（`PropertyTable` 出现 160 次，
`Reflection` 45 次），配合 `GameFlow`/`LocalBB`/`UniqueFlow` 脚本系统
（`GameFlow` 235 次）。也就是说：**游戏用一套数据驱动的反射系统注册类型，
所以类型名和字段名被保留成了运行时可查的字符串。**

### 这对项目意味着什么

**这是本项目可行性的核心依据，也是唯一的关键有利条件。** 意义：

1. **类名可恢复**：`spl::AILiftBase`、`spl::AttackEventMulti16` 这类名字是真的，
   不是猜的。可以据此命名函数、切分编译单元。
2. **字段名可恢复**：`spl__BulletBombMoveParam` 这类参数表名暗示了结构体字段。
   配合 RomFS 里的参数文件（`/tmp/patch-out/1/` 有大量 `.byml.zs`）可以交叉验证
   字段类型和顺序。
3. **但函数边界仍需自己找**：没有符号就没有函数名到地址的映射，这部分要靠
   Ghidra 分析 + 交叉引用推导。

**难度定位**：介于 botw（有 Wii U 版符号作跳板）和完全 strip 之间。类名/字段名有，
函数名没有。**比最坏情况好得多，但远不是"有符号表"的轻松模式。**

## 下一步应该做什么

1. **保护这些产物**——`main`、RomFS、uncompressed 都该放到持久目录（不要留在 `/tmp`，
   重启会没）。建议放进新建的 `splatoon3-decomp/` 项目目录，用 .gitignore 排除
   （受版权保护，且体积大）。
2. **反向利用字符串表**：把 2,027 个 `spl::` 类名 + 参数表名导成清单，作为符号库种子。
   这是最高价值的低成本动作。
3. **RomFS 参数文件**：`/tmp/patch-out/1/` 里是完整游戏参数（byml 格式），
   能和参数表名互相印证。BYML 解析工具有现成的。
4. **确认引擎**：从字符串看像自研引擎 + Havok 物理（`hk2021_1_8` 出现）。需确认是否
   LunchPack。
5. **反推 clang 版本**：仍然是头号关键路径（见另一份路线文档）。

## 复现命令（完整链路）

```bash
# 1. 修 key（丢弃 33 个畸形键）
#    产出 /tmp/keys-clean/prod.keys

# 2. 从更新 NSP 抽 NCA
hactool -t pfs0 -k /tmp/keys-clean/prod.keys --outdir=/tmp/nca-extract "<11.3.0.nsp>"

# 3. 从本体 XCI 抽 base NCA（BKTR 重建需要）
hactool -t xci -k /tmp/keys-clean/prod.keys --securedir=/tmp/base-xci "<本体.xci>"

# 4. 用 nstool 做 BKTR patch 重建 + 提取（hactool 不行）
nstool -k /tmp/keys-clean/prod.keys \
  --basenca /tmp/base-xci/f6e46265849db31008d3de7091299d7c.nca \
  -x / /tmp/patch-out /tmp/nca-extract/b17c38424e33cec90d4407ef33c7848d.nca

# 5. 解压 NSO
hactool -t nso0 -k /tmp/keys-clean/prod.keys \
  --uncompressed=/tmp/patch-main.uncompressed /tmp/patch-out/0/main
```

## 边界

提取产物是受版权保护的 Nintendo 代码，只用于本地研究，**不公开分发、不进 git**。

---

## 补充：旧项目文档的去向

原本临时写在 `splatoon-rl-lab/notes/` 的三份逆向文档已迁入本项目：

```text
docs/01-rea-toolchain-assessment.md   REA 工具评估（结论：非承重，可用可不用）
docs/02-project-roadmap.md            项目路线与 agent 化设计
docs/03-extraction-verified.md        本文档 —— 提取实测结果
```

`splatoon-rl-lab`（视觉/RL）与本项目目标不同，两者独立。
