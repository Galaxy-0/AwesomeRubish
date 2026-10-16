# 匹配 vs 非匹配反编译：为什么这个选择决定整个项目的形态

## 一、两种反编译到底差在哪

### 非匹配（non-matching / "差不多就行"）

目标：产出**语义等价**的 C++，能编译能跑、行为一致就行。

验证方式：**没有机械验证。** 只能靠人读代码判断"这段逻辑对不对"。

问题在于：这正是 LLM 最不可靠的地方。LLM 很擅长产出**看起来完全合理**的代码——
变量名对、控制流顺、注释像模像样——但可能：
- 边界条件搞错（`<` 写成 `<=`）
- 整数符号搞错（有符号/无符号）
- 少一个 case 分支
- 结构体字段偏移算错
- 调用了一个"名字很像但不是那个"的函数

**没有任何自动手段能发现这些。** 全靠人工审查。而人工审查的带宽是有限的——
一个人一天能认真读多少行反编译代码？几百行。而项目有几十万行。

### 匹配（matching / "逐字节一致"）

目标：产出的 C++ **编译后，每一个字节都等于原二进制**。

验证方式：**机械的、可自动化的、二值的。**

```text
写 C++ → 用目标编译器编译 → 对比生成的指令和目标二进制
                              ↓
                        完全一致 = 匹配 ✅
                        有任何差异 = 不匹配 ❌
```

工具是 `objdiff`（已确认**支持 ARM64 / Switch**）。它输出的是**匹配率百分比**，
比如"这个函数 8 条指令里 8 条对上 = 100%"。

**关键性质**：
1. **二值且客观**——不依赖任何人的判断
2. **有梯度**——匹配率是连续信号，不只是"对/错"
3. **不可能骗过去**——你没法让"错的代码"编译出"对的字节"（除非作弊用裸汇编，
   所以成熟项目**明令禁止 naked asm**）

## 二、为什么这个选择决定要不要上 agent 集群

这是全篇的核心。

### 匹配模式 = 天然的 RL 任务

每个函数是一个**独立任务**，有**可计算的奖励信号**（匹配率），成功判定**完全机械**。
这正好是 agent 集群的完美形态：

```text
任务：把 FUN_7103741990 反编译成匹配的 C++
状态：当前代码 + 编译失败信息 + objdiff 的指令 diff
动作：改代码
奖励：匹配率提升（或达到 100%）
终止：匹配 ✅ 或 尝试 3 次放弃
```

**这是一个有 ground truth 的搜索问题。** agent 可以自主迭代，因为每一步都能
知道"我离目标更近了还是更远了"。集群并行是因为函数之间基本独立。

### 非匹配模式 = LLM 幻觉的放大器

非匹配模式下**没有 oracle**。agent 产出代码后，唯一的裁判是另一个 LLM
（或者人）。而：

- **LLM 自评不可信**——它会给自己的错误输出打高分
- **LLM 互评也不可信**——同一个模型家族的盲区是相关的，换个模型只能缓解
- **人审是瓶颈**——集群开 10 个 agent，产出速度是人的 100 倍，
  但审查带宽还是那一个人

结果：**集群规模越大，错误产出越快，积压的未验证代码越多。** 这就是"放大错误"
的具体含义——不是 agent 变笨了，而是**产出的增长速度远超验证能力**，
最后你有一堆看起来很棒的代码，但不知道哪些是真的能用。

### 一句话总结

| | 匹配 | 非匹配 |
|---|---|---|
| 验证 | 编译器 + objdiff，机械 | 人读 / LLM 互评，主观 |
| 可否自动判定 | ✅ 可以 | ❌ 不行 |
| 集群适配度 | ✅ 完美 | ❌ 危险 |
| 单函数成本 | 高（可能反复几十轮） | 低（几分钟出一个） |
| 产出可信度 | 高（字节证明） | 未知 |

**匹配模式慢，但产出的每一行都被证明过。非匹配模式快，但你不知道哪些能信。**

## 三、真实的 agent swarm 先例：SSBU Decomp

`Super Smash Bros. Ultimate` 的匹配反编译项目（`sbergeron42/ssbu-decomp`）
**正在用 agent 集群做这件事**，它的 `CLAUDE.md` 是一份极其宝贵的实战文档。

### 它的规模数据

```text
11.3.0 对照（SSBU patch 13.0.4）：
  .text 总大小       27.0 MB
  总函数数           39,635
  字节匹配（真 C++）  10,025  (25.29%)
  非匹配编译          3,765  ( 9.50%)
  合计反编译         14,156  (35.72%)
  未处理             25,479  (64.28%)

按字节：1.89M / 27.0M = 7.00% compiled, 1.78% verified
```

**注意最后一个数字**：按字节算只有 **1.78% 真正字节匹配**。因为小函数容易匹配，
大函数难。项目自己诚实地说"字节加权才是真实的源码恢复进度"。

这是**一个成熟项目、有集群、已经跑了几个月**的成果。这个数字是我们必须正视的
基准线——**它不是"AI 一上就 80%"的故事。**

### 它的架构（直接可抄）

```text
Orchestrator（主仓库 master 分支）
  · 合并 worker 分支
  · 跑全局验证
  · 独占维护 data/functions.csv
  · 处理工具链修复

Workers（git worktree + worker/pool-* 分支，a 到 j 共 10 个池）
  · 认领模块 → 反编译 → 本地编译验证
  · 只能改自己领地内的文件
  · 禁止改 functions.csv（防冲突）
```

### 它踩过的坑（这是最值钱的部分）

**坑一：agent 爱抄 Ghidra 伪代码。**
> "Write C++ that a Bandai Namco developer would have written. If Ghidra shows a pattern,
> understand it and rewrite it idiomatically — do NOT copy-paste Ghidra pseudocode."

这条被写进硬规则，违反会被自动拒绝。

**坑二：agent 爱用裸偏移访问，破坏结构体恢复。**
> "STRUCT FIRST — 如果函数在同一个指针上访问 3 个以上偏移，**必须**先定义/扩展
> 结构体再写函数。`param_1[0xe7]` 和 `*(u64*)(sub + 0x790)` 会被拒绝。"

理由极其重要：**结构体知识是复利的**。每个函数反编译时暴露的字段信息，
会加速后面所有函数的匹配。用裸偏移就丢掉了这个复利。

**坑三：agent 用裸汇编假装进度。**
> "NO `__attribute__((naked))`. Naked asm is BANNED outright. 如果 3 次尝试后
> 还不匹配，就跳过——**不要用粘贴的汇编来虚报进度**。"

这直接印证了我前面的观点：**有 oracle 才能防作弊**。匹配率可以被裸汇编骗过，
所以他们干脆禁用，并把历史上的 366 个裸汇编函数单独归类、不计入"真源码恢复"。

**坑四：agent 在同一个失败点上烧光整个会话。**
> "Stop-and-document rule：如果 Ghidra MCP 报错/超时，**不要重试**同一个地址。
> 记到 `manual_extraction_needed.md`，然后继续下一个。"

> "3-attempt limit：如果一个函数 3 次编辑-编译-验证循环还不匹配，跳过。
> 不要在一个函数上钻牛角尖。"

**坑五：agent 的注意力/上下文极贵，所以有明确的效率规则。**
> - "绝不为了重新看输出而重编译——跑一次 `tee` 到文件，然后 grep"
> - "把 Ghidra 结果存磁盘（不是 /tmp，重启会没），下次读文件而不是重新调用"
> - "不要修基础设施——工具坏了就在 commit 里报告，交给 orchestrator"

**坑六：命名必须有可追溯的证据链。**
> "每个命名字段必须包含名字**是如何推导出来的**，可追溯到二进制证据"
> ```
> situation_kind    // +0xD8 [derived: situation_kind_impl (.dynsym) reads this as s32]
> field_0xE0_s32    // +0xE0 [inferred: bitmask pattern in 12 functions, no proven name]
> unk_0xE4[0x5C]    // unknown padding, honest gap
> ```
> "**NEVER** label an inferred field name as if it were confirmed.
> Wrong names that look authoritative mislead the community."

这一条对我们特别重要——**假名污染知识库，比不命名代价大得多**。

### 它的验证流水线

```text
worker 提交前自检：python tools/review_diff.py pool-{letter}
  ↓ 分数 <50 或有 REJECT 违规 → 自己修
  ↓
orchestrator 复检：review_diff.py 会 REJECT 违规 diff
  ↓
tools/verify_all.py --update —— 权威进度来源
```

注意 `review_diff.py` 的规则都是**机械可检的**（有没有 naked、有没有 Ghidra 默认名、
`reinterpret_cast` 密度是否超 10%）。**这是把"代码质量"变成了可自动裁决的规则。**

## 四、我们（Splatoon 3）的具体情况

### 好消息：工具链反推的路径已经有了

SSBU 的 `RESEARCH.md` 给出了完整的 SDK→Clang 映射方法，而且**我们的 SDK 版本
已经从二进制里提取出来了**：

```text
Splatoon 3 11.3.0 的 SDK 组件版本（从二进制字符串提取）：
  NintendoWare_G3d2-20_5_22-Release
  NintendoWare_Vfx2-20_5_22-Release
  NintendoSDK_libcurl-20_5_22-Release
  NintendoWare_Font-13_3_6-Release
  NintendoWare_Ui2d-13_3_6-Release
  Pia-6_32_3-Release
  NPLN-1_38_1-Release
  SDK 20.5.22.0
```

对照 SSBU 已知的映射表：

| 游戏 | NintendoSDK | 上游 Clang |
|------|-------------|-----------|
| Super Mario Odyssey | ~3.x-4.x | 3.9.1 |
| BotW v1.5.0 | ~4.x | 4.0.1 |
| Minecraft Switch | 4.4.1 | 4.0.1 |
| Captain Toad v1.3.0 | 8.2.0 | 8.0.0 |
| SSBU v13.0.4 | 8.2.1 | 8.0.0 |

**Splatoon 3 用的是 SDK 20.5.22 —— 比 SSBU 的 8.2.1 新了一大截。**
所以不能直接照搬 Clang 8.0.0，需要自己确定 20.x 对应哪个上游 Clang。
但**方法完全一样**（见下节）。

### 好消息：SSBU 的关键 flag 已知

```bash
-target aarch64-none-elf -mcpu=cortex-a57 -O2 -fPIC -mno-implicit-float \
-ffunction-sections -fdata-sections -fno-common -fno-exceptions -fno-rtti -std=c++17
```

关键发现：**`-mno-implicit-float` 是必须的**——不加的话编译器会用 SIMD 寄存器清零
内存（`movi v0.2d + str q0`）而不是标量 `str xzr` 对。这个坑可以直接绕开。

已知的 NX Clang 分叉：上游 Clang 用 `orr Wd, wzr, #imm` 编码位掩码常量，
任天堂的分叉用 `movz Wd, #imm`。SSBU 的解法是 `tools/fix_orr_movz.py` 后处理脚本。

### 好消息：我们比 SSBU 有的优势

1. **我们有 `spl::` 类名（2,027 个）** —— SSBU 靠社区命名，我们有官方反射系统的名字
2. **我们有 RomFS 参数文件** —— 能和参数表名交叉验证字段
3. **SSBU 趟过的路我们不用再趟**

### 坏消息

1. **没有符号**（和 SSBU 一样），函数边界要靠 Ghidra 推
2. **SDK 20.5.22 的 Clang 版本未知**，要自己反推（这是头号关键路径）
3. **体量**：SSBU 的 .text 是 27 MB，我们的是 **82.38 MB（text）**，约 3 倍

## 五、建议

### 先做匹配模式的最小闭环（不要先搭集群）

按 Phase 0 的顺序：

1. **反推 clang 版本**——用 SSBU 的方法：
   - 从二进制搜编译器字符串（我们已经搜过，没有直接版本串）
   - **对比 codegen 模式**：挑几个小函数，用不同 Clang 版本编译，对比指令选择
   - 查 `decomp.me` 的 Switch clang 编译器仓库
   - 查 KinokoDecomp-S / botw 的 SDK 映射经验
2. **搭 objdiff 单函数闭环**——先用一个函数验证"写 C++ → 编译 → diff"跑通
3. **只有闭环成立后**，才谈集群

### 关键判据

**如果在第 1 步卡住（找不到能匹配的 Clang），那匹配路线不成立，要重新评估。**
这个判断必须尽早做，因为它决定后面所有投入的方向。

### 如果走匹配路线，集群规模不要贪大

SSBU 用 10 个池（a-j）。考虑到：
- 我们的 .text 是它的 3 倍
- 但 orchstrator 是人，审查带宽有限
- 工具链比它更陌生（SDK 20.x vs 8.x）

**建议先开 2-3 个 worker 跑通流程，再逐步扩。** 集群的瓶颈从来不是 agent 数量，
而是知识库质量 + 人的审查带宽。

### 边界

无论走哪条路，反编译产物**不公开分发**。SSBU 项目虽然公开，但它有社区基础和法律
评估；我们保持私有研究定位更稳妥。

## 六、一句话回答你的问题

**匹配模式才撑得起集群，因为它把"反编译对不对"变成了编译器能回答的问题。**

非匹配模式下，集群越大、产出越快、错误积压越多——因为验证只能靠人，
而人的带宽不随 agent 数量增长。SSBU 的实战数据（几个月、10 个池、
按字节 1.78% 真匹配）说明这条路可行但很陡，而它能成立的前提正是**有 objdiff
这个机械裁判**。
