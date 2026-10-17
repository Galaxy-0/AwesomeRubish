# 进度

## 2026-10-17

1. **粗查**（notes/survey-11.3.0.md）：SDK 20.5.22（和 nxnative 已支持的 BotW 1.9.0 同一个 SDK），引擎 sead/agl/gsys（和马力欧惊奇同一家），
   模块只有 main + sdk，RomFS 9.4 GB 基本都是 .zs。
2. **改写器**：main 有个 jump table 的 adr/ldrh 离 br 有 10 条指令，把回看窗口从 8 加到 16 就过了。改写后 main 多出 38 MB patch 区。
3. **宿主起机**：
   - 内存：guest 块扩到 8 GB（Mac 上不受 iOS 的 5 GB 限制）
   - UsedMemory 要按改写前的模块大小报（不然 SetHeapSize 超池；游戏还拿 System/HeapSize 里 Program=0x8c00000 和它比）
   - 新加 `hle_spl3.c`：bcat / friends / album / pdm / ngc / account 扩展 / time 规则全部按"离线、什么都没有"回答
   - fs：MountCacheStorage、IsSaveDataExisting、MountSaveDataReadOnly
4. **当前位置**：nnMain 跑起来 → 起 20+ 线程、读 RomFS、开存档、NVN 设备 + Metal、音频渲染器 → 卡在第一次画东西（还没有着色器表）。

下一步：shader_split → dmsh_build（没 Xcode 用 nometal_run，运行时编 MSL）→ 看到标题画面。

### 着色器 + 首批画面（同日）
- shader_split：27,281 个着色器（effect 12k / uber 9.7k / lib 3.5k …）；翻译成功 27,274，失败 7（SPIRV-Cross subgroup / nullptr）
- 没装 Xcode：.NET 10 装在 ~/.dotnet10，链路走 nometal_run.py（metallib 里放的是 MSL 源码），Mac 宿主也打开了运行时现编
  （nvn_mtl.m `#if defined(DM_SHELL) || !TARGET_OS_IPHONE`）
- 跑到 600+ 帧，每帧约 1–2 万次 NVN 调用，3D 场景在渲染：阴影图、**3200×3200 墨水涂地图里有红/绿两队的墨**（对战逻辑真的在跑）
- 问题：最终 1080p 输出全黑；约 900 帧后主线程卡在 Presentation Thread 持有的锁上；红字：压缩格式渲染目标、
  nvnCommandBufferSetAlphaRef 没实现、SetRenderEnableConditional 恒画
- 着色器表（shader_*.tsv，几十 MB）不入库，用 shader_split 重新生成

## RL 4v4 路线（结论）
游戏没有离线 bot 对战。真正的 4v4 全武器/全地图/全模式 = **本地通信（ldn）私房**：开 8 个宿主进程，每个是一台"Switch"，
宿主把 nn::ldn 换成进程间虚拟网络（现在是直接返回失败的桩）。pia 本身在 main 里原生跑，只需要 ldn 层 + 收发包。

## M1 首次推进检查点（2026-10-17，历史失败，后续已修复）

当前按 GOAL.md 的最新顺序推进：M1 → 本地通信入口 → 双进程 LDN → 1v1 完赛 → 4v4 → RL 接口。
**当时 M1 尚未通过，M2–M6 未开始。** 以下保留失败证据；本轮完成结果见文末。

### 已实现及根因证据

- 最终 1080p 黑屏已找到一个直接原因：`ReportCounter(TIMESTAMP/TIMESTAMP_TOP)` 以前把 GPU 时钟同时写入 counter 和 timestamp 两个字段，
  而 `SetRenderEnableConditional` 以前完全忽略条件。SDK 20.5.22 的实际驱动 `sdk+0x4ef450` 发出的 timestamp semaphore payload 为 0。
  Splatoon 随后比较相隔 16 字节的两个 `NVNcounterData.counter`（64 位，非 +8 的 timestamp）。非零 counter 加恒画使后置的 clear-only pass 擦掉场景。
- 现在 timestamp report 为 `{0, gpu_ticks}`，增加 `OP_RENDER_ENABLE`，按 Direct / Equal / NotEqual 对 draw 和 clear 生效。
  对同次提交内尚未执行的查询或缓冲写入，在 CPU 读取条件前提交并等待 GPU；当前这个同步实现仍伴随下面的命令生命周期卡点，不能视为最终实现。
- `CopyCommands` 以前和 `CallCommands` 一样只保存源地址。现在复制记录、展开 JUMP 段、重定位记录内部的贴图快照；`CallCommands` 仍保留引用。
  覆盖源命令内存后进行 Metal 回放的像素检查通过，但**这项修正没有解决本次约 900 帧错误**。
- 命令回放增加头部有效性检查（op / size / alignment，附入口和调用位置），避免损坏的 size 让 Presentation Thread 无限空转。
  这是诊断与失败前置，不能当成锁死已修复。

### 自动化验证

一键入口：`bash tests/run_all.sh`（依赖安装见 `tests/README.md`）。
先构建宿主与无游戏素材 GPU 测试，再使用独立新存档运行真实游戏；产物仅写 `work/tests/`。

- 条件渲染及 CopyCommands 真实 Metal 像素检查：**108 checks, 0 failed**。
  覆盖开关、Equal / NotEqual、64 位高字、忽略 timestamp 字段、draw / clear、直接恢复、同提交 timestamp producer、覆盖复制源内存。
- NVN 检查：**64 项，失败 0**。保留嵌套 CallCommands 的回放覆盖。
- M1 集成门槛：75 秒运行至至少 2400 帧，末尾帧计数持续增加，600/1200/2400 帧截图 1920×1080、平均 RGB 方差 ≥25、非黑像素 ≥5%，
  无 CRASH/FATAL/看门狗/GPU 执行错误，并完成 SIGTERM 优雅退出。任何一项失败均返回非零。
- 本次一键集成验证：**FAIL**。约 20 秒、900 帧附近因 invalid command 中止（return code -6）；只达到最后一次周期日志 600 帧，1200 / 2400 帧截图缺失。
  600 帧截图方差 **6849.88**、非黑像素 **78.71%**，尺寸 **1920×1080**，证明已出真实场景，不能证明持续运行或 M1 完成。
  原始证据：`work/tests/m1-20261017-221732-297032/{host.log,result.json,frame_600.png}`。
  最终代码复跑 `work/tests/m1-20261017-221924-164900/` 同样失败：两组 GPU/NVN 检查仍通过，600 帧截图方差 **6813.59**、非黑像素 **78.98%**，随后出现损坏 CALL。
- 早期未加入查询同步的 `work/run/m1-long.log` 曾运行 100 秒至约 5700 帧，
  `work/m1/long_{1200,2400,4000}.png` 可见开场与角色选择；随后同步版本稳定复现失败，故不使用早期成功覆盖当前失败。

### 卡点（按 GOAL.md 分工条款，记录后停下等指示）

**现象与定位**：

- `work/run/m1-stall-sampled.log` / `work/m1/watchdog.sample.txt`：约 897 帧停顿时，主 GPU fence 已提交与已完成相等，出图队列入 / 完成均为 897；
  Presentation Thread 的采样停在嵌套 `mtl_exec` 命令解码循环，主线程等待它持有的锁。没有证据表明是 GPU fence 未完成。
- 加 guard 后，`work/run/m1-command-chain.log` 在嵌套深度 2 的 CALL 目标入口直接报损坏命令头，`entry == invalid address`、`prev == NULL`。
  最终一键结果同样复现：`op=1471414272 size=120 depth=2`，op 不是合法的自定义命令；第一次一键复跑还读到了未对齐的 `size=119`。
- `work/run/m1-copy-lifetime.log` 证明修正 CopyCommands 后仍然命中同类错误；不能把 CopyCommands 误实现认定为本次锁死的已证根因。

**已试假设与结果**：

1. GPU 队列或呈现栅栏互等：采样及 fence 状态不支持；编码线程正在执行 CPU 命令解码。
2. 后置条件清屏导致黑屏：修正后截图恢复；已由像素回读和真实游戏截图支持。
3. CopyCommands 源内存被重用：原实现确有问题且修正通过独立测试，但真实游戏仍坏在 CALL 源入口；尚未闭环。
4. 新增的查询完成等待使提交中 event / counter 更早对游戏可见，暴露 cached CALL 的命令内存生命周期或回收问题：**待证实**。
   下一步应追踪损坏目标对应的 EndRecording / CallCommands / AddCommandMemory / FinalizeCommandHandle，确认原始命令段何时被覆盖或释放，
   同时审计分段提交的完成回调；避免用跳过损坏列表、取消全部同步或永远不释放内存来伪造通过。

仍有旧红字：压缩格式渲染目标不能挂载、8 位索引缓冲存在同提交 GPU 写入、AlphaRef 未实现等；本次未声称所有画面和渲染语义正确。
没有改接 LDN、启动多开对战或连接任天堂服务。

### 补丁保存

基线仍为 nxnative `9579030e5b1f0443c12b7376559560915b6d4c4b`。提交前执行：

```sh
# New source files must first be made visible to git diff; do not add test binaries or game data.
git -C upstream add -N dm/gfx/tests/t_render_enable.m
bash tools/update-patch.sh
git -C upstream apply --reverse --check ../patches/0001-splatoon3.diff
```

`tools/update-patch.sh` 排除 `dm/games/0100C2500FC20000/shader_*` 与 `c1_full.tsv`。
截图、NSO、RomFS、着色器包、密钥以及本地测试日志均不入库。

## M1 卡点第 1 轮：完成（2026-10-17）

**当前状态：M1 PASS；提交推送后进入 M2。** 按本轮指示先取覆盖者证据，再修复并跑一键回归。

### 抓到的实际覆盖者

- 新增 `nvn_cmdwatch.[ch]`：在 QueueSubmitCommands 遍历可达 CALL/JUMP 链，登记命令段及 AddCommandMemory 的来源范围，逐条保存 hash；
  可选择对相应页写保护，直到 CPU 解码完毕。对同页邻接对象写入解除页保护并继续 hash 检查；两次提交之间保留宽容写入历史。
  `DM_NVN_CMDWATCH=<起始帧>` 开启，`DM_NVN_CMDWATCH_HASH=1` 只检查 hash；默认关闭，不保留游戏命令副本。
- `work/run/m1-cmdwatch-exact.log` / `m1-cmdwatch-created.log` 证明：坏目标在约 897–899 帧的 QueueSubmit 入口已经损坏；
  对应列表在约 534–535 帧创建时，BEGIN 仍为合法的 `0x0000000800000002`。损坏头部后来变成该列表宿主尾段的地址。
- 进一步对缓存 BEGIN 的 JUMP payload 写入设保护，`work/run/m1-cmdwatch-writer.log` 实际捕获：
  `pc=cmd_new_segment+0x134`、`lr=cmd_new_segment+0x130`，调用链为
  `cmd_alloc → h_nvnCommandBufferEndRecording → main+0x46ca2e8`。这是**录制阶段的宿主写入**，发生在 535 帧，随后直到约 898 帧才调用被破坏的缓存列表。
- 最终对照构建 `work/run/m1-end-regression-writer-shmap.log` 再次捕获实际 store，并打印 PC/LR/线程：
  532 帧 `addr=0x716f4cbbb0 pc=0x1005d4a14 lr=0x1005d4a10 thread=0x1eaa5ff80`；另两个录制工作线程也命中同类写入。
  这个构建仅恢复旧 END 余量，其他修复均保留，独立存于 `work/m1/dmhost-end-defect`。
- 已用 `tools/nsosym.py` 对游戏调用点符号化，输出为 `work/m1/cmdwatch-writer-symbols.txt`。main 的相关内部函数已剥离符号，工具只找到 past-end 的最近导出，不能将它当作真实方法名；宿主函数名由实际崩溃回溯给出。

### 根因与修复

`cmd_alloc` 对所有记录统一要求额外 **24 字节** 尾部保留，EndRecording 也走同一规则。
即使尾部足够放 8 字节 END，它仍要求至少 32 字节，触发多余的补内存回调和段切换。
回调期间游戏可以打包相邻的缓存列表，随后宿主写入的 16 字节 JUMP，其后 8 字节目标地址覆盖了邻接 BEGIN。
第一次看到锁死时只是较晚的受害者；本轮证据没有把完成信号提前可见确认为这次损坏的直接根因。

- END 现在只分配自身的 8 字节，不预留后续 JUMP；普通记录继续保留原规则。
- 同时按实际 SDK 20.5.22 `sdk+0x4b8fa0` 修正 GetCommandMemoryUsed：返回当前调用方内存段的累计消耗，BeginRecording 不清零，AddCommandMemory 清零；
  宿主补段字节不计入游戏的分配用量，实际写进游戏段的 JUMP 仍计入。单独修复这个用量问题曾复跑失败，不能将它替代 END 覆盖证据作为锁死根因。
- 原有查询同步等待保留；没有跳过损坏命令、关闭同步或无限保留游戏命令内存。

### 自动化回归及对照

- `bash tests/run_all.sh`：**PASS**。
- 条件渲染 / 复制像素检查：**108 checks, 0 failed**。
- NVN 检查：**70 项，失败 0**。新增当前段跨 recording 累计、新段清零、宿主补段用量隔离，以及 END 尾部边界 / 邻接 BEGIN 保护检查。
- 修复前用量检查出现 3 项失败：`work/m1/usage-before.log`。
  仅恢复旧 END 余量规则的对照构建仍使 2 项边界检查失败：期望用量 72、实际 80；邻接 BEGIN 被替换成宿主段地址。
  证据 `work/m1/end-before.log`；该对照可执行文件仅在 `work/m1/`，正式源码和宿主保持修复版。
- 真实游戏完整运行 **75 秒**，周期日志帧数 **3300**，末尾持续增长；退出码 **0**，完成 SIGTERM 优雅退出；无 CRASH/FATAL/看门狗/GPU 执行错误。
  证据：`work/tests/m1-20261017-225702-924452/{result.json,host.log,frame_*.png}`。

| 截图帧 | 尺寸 | RGB 平均方差 | 非黑比例 |
| --- | --- | ---: | ---: |
| 600 | 1920×1080 | 6827.90 | 78.90% |
| 1200 | 1920×1080 | 4742.49 | 99.94% |
| 2400 | 1920×1080 | 5434.37 | 91.40% |

2400 帧人工检查可见完整角色选择界面。M1 通过只涵盖画面非黑与本轮持续运行门槛，图形中原有压缩目标 / AlphaRef 等红字仍待按后续实际阻塞处理。
