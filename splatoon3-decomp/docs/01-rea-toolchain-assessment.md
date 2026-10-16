# 2026-10-16 · 用 REA 做 Splatoon 3 静态逆向：推进计划

## 一句话结论

REA（`morluto/rea`）能用，但它**不是** Switch/NSO 工具，它的 native 分析后端是
Hopper / Ghidra / IDA。所以能不能跑通，取决于我们能不能**自己**先把 Switch 的 NSO
转成它能吃的 ELF。当前真正的卡点不是 REA，而是：**仓库里没有游戏本体的 `main`
NSO**，只有 Flexlion 装进去的替换模块。

## 现状盘点（已在本机核实）

### REA 是什么

- `morluto/rea` = "Reverse Engineer Anything"，一个 **MCP server**（TypeScript，
  MIT），把 Claude Code / Codex / Cursor 等 agent 接到逆向工具上。
- native 二进制分析必须有一个后端：**Hopper、Ghidra 或 IDA**。JS / .NET 静态分析
  才不需要引擎。REA **不会**自己装 Ghidra。
- 能力表里覆盖：native 二进制、ELF 布局、Go/Rust、WASM、EVM、SQLite、.NET、APK、
  Flutter、固件、pcap、逻辑信号、进程行为……
- 能力表里**没有**：Nintendo Switch、NSO/NRO、Unity、IL2CPP。文档里 ARM64 只出现在
  "host 是 ARM64"（Ghidra 跑在 Apple Silicon 上）和 AArch64 jump-table 反编译，
  指的是**代码架构**，不是 Switch 容器格式。
- 安装：`npx rea-agents setup`，npm 包 `rea-agents`（当前 6.5.0），要求 Node 22.x
  >= 22.19。

### 本机环境

| 项 | 状态 |
|----|------|
| Node | v22.22.3 ✅（满足 REA 要求） |
| Ghidra | ❌ 未装；`brew install ghidra` 可装（formula，12.1.4，依赖 openjdk@21） |
| Hopper / IDA | ❌ 都没有 |
| JDK | 只有 Corretto 11；Ghidra 12.1 需要 JDK 21+ |
| objdump | `/usr/bin/objdump`（macOS LLVM 版） |
| hactool / nstool | ❌ 都没装 |
| prod.keys / title.keys | ✅ 在 `~/.switch/` |

### 仓库里的二进制到底是什么

`live/runs/mod-probe-2026-10-15/` 下的 NSO **不是游戏本体代码**：

- `console-before.log` 显示安装前 `/atmosphere/contents/0100C2500FC20000` 是 **ABSENT**，
  说明这个目录是这次 Flexlion 安装创建的。
- `sdk.decompressed` 里全是 `Flexlion3`、`/mnt/c/Main/Splatoon2/Projects/Flexlion3/`、
  `~~exlaunch uwu~~` 的字符串 —— 这是 **Flexlion 自己的 exlaunch 载荷**。
- `subsdk0` 的 NSO module name 是 `nnSdk`，里面是 `hosFinalizeEvents` 之类的
  Nintendo SDK / NVIDIA(`nerd_gillette`) 内部符号 —— 是被 Flexlion 打过补丁的 SDK 模块。
- 安装清单里有 `main.npdm`（972B，只是描述符），**但没有 `main` 本体**。

**结论：要逆向 Splatoon 3 的真实玩法逻辑，得从游戏本体里取 `main` NSO。**
本机有的是：
- 本体 XCI：`/Users/galaxy/Downloads/喷射战士3/xci本体/Splatoon 3 [...][v0].xci`（5.1G）
- 更新 NSP：`/Users/galaxy/Downloads/喷射战士3/upd-v11.3.0/[UPD][11.3.0]...nsp`（7.3G）← 真正的 `main` 在这里

### 一个有用的好消息：NSO 格式是标准的

手工解出 `staged/.../subsdk0` 的 NSO 头（标准布局，非自定义）：

```text
magic "NSO0"  version=0  flags=0x3f
text   : file=0x106     mem=0x0        size=0x663700
rodata : file=0x3c176b  mem=0x664000   size=0x4cbe70
data   : file=0x5d706d  mem=0xb30000   size=0x554e8
bss    : 0xcfb18
build_id @0x40
```

标准 NSO 布局意味着现成工具链（hactool、switch-tools 的 `nso2elf`、Ghidra 的 NSO
loader）**可以直接用**，不需要自己写解析器。

### 运行时这一侧已经有了什么

- sys-botbase v2.5（TCP 6000）：能读 Build ID / 基址 / 原始内存、能注入摇杆输入。
- 实机运动已验证（用户确认 2 秒前进从街面走到台阶）。
- 游戏版本 11.3.0，**Build ID `28c4287aee36f749`**，Title ID `0100C2500FC20000`。
- 还**没有**玩法观测 schema：能让人物动，但读不到坐标 / 墨量 / 血量 / 场景。

## 关键概念：静态地址 ↔ 运行时地址必须对齐

静态反汇编看到的地址是 `镜像基址 + 文件内偏移`，运行时 sys-botbase 读的是
`模块基址 + 偏移`。三个 ID 必须对上，否则整条链是废的：

1. 反汇编用的 `main.nso` 的 **Build ID** 必须 == 运行时的 `28c4287aee36f749`；
2. sys-botbase 报的 **模块基址** 要作为重定位基准；
3. Ghidra 里 image base 要设成与 NSO 段映射一致。

这一步出错是**静默**的 —— 能跑出结果，但全是错的。所以第 1 个里程碑就是先钉死对应关系。

## 推进路线

### Phase A — 环境（REA + Ghidra 跑通）

1. `brew install ghidra`（自带 openjdk@21）；导出 `GHIDRA_INSTALL_DIR`。
2. `npx rea-agents setup`，把 MCP 注册到 Claude Code。
3. `rea doctor --provider ghidra --json` 确认后端可用。
4. **先拿一个无关的 ARM64 小二进制做冒烟测试**（比如 `/usr/bin/objdump` 或随便一个
   Mach-O），确认 `rea decompile` 能出 C，再去碰 Switch 二进制。

### Phase B — 造出反汇编器能读的镜像

工具链已确认存在（不用自己写解析器）：

1. **hactool**（`SciresM/hactool`，已确认支持 `-t nsp` / `nca` / `--exefsdir` /
   `NSO0 --uncompressed`）从 11.3.0 更新 NSP 里抽出 ExeFS，得到 `main`。
   本机已有 `~/.switch/prod.keys`，可直接解密。
2. 转成 Ghidra 能读的形式，两条路：
   - **a. Ghidra 插件**：`Adubbz/Ghidra-Switch-Loader`（374★，"Nintendo Switch
     loader for Ghidra"）直接吃 NSO/NRO/NSO0。**首选这条**，省掉手工映射段表。
   - **b. 转 ELF**：devkitPro `switch-tools` 的 `nso2elf`，再让 REA 走普通 native
     流程。
3. **校验**：转出来的 Build ID 必须是 `28c4287aee36f749`；再和运行时 sys-botbase
   读到的段基址交叉验证。

### Phase C — 第一个定向逆向问题（这才是真正的产出）

不要想着"把整个游戏反编译成源码"——那不现实，Splatoon 3 也没有 N64/Wii 时代的
decomp 项目。REA 的正确用法是**定向调查**：给一个运行时现象，找到产生它的代码。

建议第一个目标选**墨量（ink）**，因为：
- 本机有金手指文件做线索：`/Users/galaxy/Downloads/喷射战士3/11.1.0金手指.zip`，
  其中 "Unlimited Ink" 指向 `0388A5D8` 和 `0135994C`；
- 但那组地址是 **v11.0.1 / BID `360D502237522135`** 的，**不能直接用**，只能当锚点；
- 先用 restore code 的原始指令字节在 11.3.0 镜像里做模式匹配，定位对应函数；
- 再用 REA 反编译那个函数，找出 player struct 里 ink 字段的偏移；
- 最后**运行时验证**：在训练场里用 sys-botbase 读那个地址，看墨量变化对不对得上。
- 这一步跑通 = "静态假设 → 运行时证实" 闭环成立，后面全部复用。

### Phase D — 铺开观测 schema

按同样流程依次恢复：ink、位置(x/y/z)、血量、相机 yaw/pitch、目标距离。写成带版本号的
JSON schema 放仓库里。

### Phase E — 接回 RL 循环

用内存读替换像素启发式（`heuristics/detect_frame.py`），视觉保留做校验。有了可读状态，
确定性 step / reset 才有可能。

## 备选与互补路线（别忽略）

- **社区前作**：`DesperC/Awesome-Splatoon3-Hacking`（资源合集）、
  `unvirus/proconcon`（键鼠转换）、`nvnprogram/HoianViewer`（玩家模型/渲染）、
  以及 Flexlion 自己的 `botinfo.json` / `fxconfig.json`（已经暴露了很多数据模型，
  比如材质名表）。先读这些能省大量时间。
- **运行时优先**：不一定非得先做静态逆向。sys-botbase 已经有内存读写，可以用"扫描 +
  差分"直接找 ink 地址（金手指地址当起点），静态 RE 用来**解释**找到的东西。
  两条路是互补的，不是二选一。

## 需要你拍板的点

1. 先做 **Phase A 环境**（装 Ghidra + 注册 REA），还是先做 **Phase B 提镜像**？
2. 第一个逆向目标确认是 **ink**，还是你想先要 **玩家坐标**（对 RL 更有用，但没有
   现成金手指线索，要从碰撞/相机那块找）？
3. 反汇编用 **Ghidra（免费，REA 官方验证）** 还是你有 **IDA/Hopper** 授权？

## 边界

- 只做私有、离线、自有硬件的实验；不上线对战、不做账号自动化、不碰其他玩家。
- 反编译产物**不要**公开分发（Nintendo 代码）；REA 的 DISCLAIMER 也是这个调子。
- 这套东西的定位是给 RL 提供观测/奖励信号，不是为了做作弊器。
