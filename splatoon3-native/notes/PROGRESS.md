# 进度

当前：M1–M5 已通过；完整八端 M5 签收版本为 `2006a98`，后续错误路径修复为 `b0b590c`。
M6 按后续指示分层推进：**A 双端帧动作 / 像素环境已通过**（随机结算 + reset 第二局）；B 内部字段和 C 八端随机策略尚未验收。详见文末。

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

## M2 第 1 轮：虚拟六轴生效；后续路线 BLOCKED（2026-10-17）

**M2 尚未通过，未提交 / 推送，M3 未开始。** 保留 M1 的 `cdcfa5f` 为已完成里程碑。

### 输入读取与更简单路线的检查

- 接续工作区原有的虚拟六轴、右摇杆、FIFO 调试输入和 22 项 HID 检查；没有丢弃上轮未提交改动。
- 增加 `DM_HID_TRACE=1`：在真正的 GetNpad / GetSixAxisSensorStates 返回路径记录状态，限每 60 个呈现帧一条。
  `work/run/m2-explore1.log` 的 5100 帧读到 `ry=32767`，8760 帧读到 `rx=32767`；
  5640 帧读到六轴 `rate=0.1000,0,0`。这些是接口返回证据，不只是在输入线程打印“已注入”。
- 实际截图确认右摇杆水平转向有效；本轮教学阶段右摇杆垂直输入没有改变俯仰。
  5200 / 5300 / 5400 帧分别试 Plus / X / Minus，仍停在教学画面，没有打开可关闭体感的设置。
  **只说明本轮没有找到这条简路，不声称整个教学绝对不支持关闭体感。**

### 六轴历史缓冲问题及修复

- 旧实现只返回一条当前 SixAxisSensorState，其他缓存槽保持全零。游戏调用点
  `main+0x459b920` 请求 16 条，忽略返回数量；`main+0x4d4f704` 固定处理全部 16 条。
  `main+0x4d4f838..0x4d4f8bc` 检查全零加速度 / 默认姿态，设置无效标记，并可能清空本次有效样本数。
  静态证据保存在 `work/m2/hid-main-dis.txt`，游戏自身代码 / 反汇编不入库。
- 改成按 200 Hz 时钟推进、最新在前的 16 条虚拟历史；各句柄读取共享同一采样时间轴，读取次数不推进采样号。
  改变角速度前先把上一段历史补齐；较长读间隔只保留最新 16 条，避免无界积累。
  布局仍为 0x60 字节，保留旋转矩阵与重力向量。没有写教学标记、相机或角色位置。
- HID 检查扩展为 **73 checks, 0 failed**：原有姿态 / 右摇杆 / ZR 之外，验证 16 条历史都有效、加速度模长、
  采样号顺序、连续读取不推进、下一个时钟样本推进、零容量读取。
- 修复后 `work/run/m2-explore3.log` 持续读到 `count=16`；17640 帧实际读到非零角速度。
  5250 帧截图出现 **Hold steady!**，5520 帧进入 **Follow that Smallfry!**，之后成功取武器、射击和爬墙。
  这支持历史不足是此前体感输入被丢弃的直接原因；未进行“仅还原历史实现”的独立游戏对照复跑。
- 当前 `G*` 名字仍对应原始传感器轴；正 X / `GUp` 在本次游戏里使镜头向下，未完成对物理手柄的方向 / 量级校准。

### 已走到的位置与保存的路线

`work/m2/explore3/` 的截图：

| 帧 | 实际观察 |
| --- | --- |
| 5520 | 小鲑鱼瞄准完成，进入移动教学 |
| 8760 | 进入 ZL 游墨教学 |
| 12090 | 提示跳下去检查小鲑鱼找到的东西 |
| 14700 / 15420 | 已取武器，进入气球射击 |
| 19560 / 21000 | 前两个气球已打破，出现后续路线提示 |
| 24780 / 26130 | 涂墙并上爬；第二段墙面需要继续补墨 |
| 27480 | 进入 **Look left and right with R!** 区域 |
| 39000 | 后续转向 / 移动探索又回到了取武器附近的三脚架区域 |

保存 `tools/routes/m2-opening-prefix.keys`：41 个书写步骤（含重复语法），从新建角色到两段爬墙，
截至 `f26711:ZL+LUp~5`；后面返回武器区的失败导航不放进该前缀。
它从探索日志重建，**尚未独立重放，不能声称可复现，更不是完整 M2 路线**。
帧号控制动作开始，hold 仍按墙钟秒数，因此帧率变化会影响移动 / 转向距离。

探索宿主已 SIGTERM 优雅退出。周期帧数至 42300，最后长帧记录为 42422 帧 / 885.76 秒；
未出现 CRASH / FATAL / 看门狗 / GPU 执行错误。没有到达大厅，所以这段运行不能替代“入口后连续十分钟”的 M2 验收。

### M2 自动化门槛与验证边界

- 新增 `tests/test_m2.py`，统一入口 `bash tests/run_all.sh --milestone m2 --frame <入口截图帧>`。
  用独立空存档执行完整 DM_KEYS、在指定帧与人工确认的本地通信入口参考图比较（局部 SSIM ≥0.90、RGB MAE ≤0.06），
  匹配后继续运行 ≥600 秒，检查帧增长、失败标记与优雅退出。产物、路线 / 参考图 SHA256 均留在 `work/tests/`。
- 完整路线预期文件 `tools/routes/m2-local-lobby.keys` 和参考图 `work/m2/reference-local-lobby.png` **尚不存在**。
  前缀不允许拿来代替完整路线；参考图不得由待验收的同次运行自动生成。
- 本轮执行该测试的默认预检：**FAIL / preflight**，如实报告缺少完整路线、参考图和已验证截图帧。
  结果：`work/tests/m2-20261017-235655-811579/result.json`。
  图像比较器仅做合成图 sanity 检查：同图 SSIM=1 / MAE=0，反色图被拒绝；
  真实大厅图的阈值、完整路线和十分钟 soak **均未验证**。

### 最终基础回归与补丁

- 最终版 `bash tests/run_all.sh` **PASS，退出码 0**：108 项 Metal 条件渲染 / CopyCommands、70 项 NVN、
  73 项 HID 检查全部通过；独立新存档运行 75 秒至周期帧数 3600，末尾帧数增长，三张 1080p 非黑截图达标，
  无运行时失败标记，SIGTERM 优雅退出、宿主退出码 0。
  证据：`work/tests/m1-20261017-235753-589631/{result.json,host.log,frame_*.png}`，
  总入口日志 `work/m2/final-regression-rerun.log`。
- 最终版 `bash tests/run_all.sh --milestone m2` **FAIL，退出码 1**：三组单元 / GPU 检查均通过，
  M2 预检因完整路线、参考图和入口截图帧缺失而拒绝运行。
  证据：`work/tests/m2-20261017-235926-456599/result.json` 和 `work/m2/m2-dispatch-preflight.log`。
- 已把新增 `dm/host/tests/t_hid_motion.c` 纳入 intent-to-add 后执行 `bash tools/update-patch.sh`；
  补丁仍以 `9579030` 为基线，排除 shader 表与 `c1_full.tsv`。
  upstream 源码 `diff --check` 和 `git -C upstream apply --reverse --check ../patches/0001-splatoon3.diff` 均通过。
  生成补丁内的空白上下文行会被外层 `git diff --check` 误报；未改写补丁上下文，外层其他源文件空白检查通过。
  未提交游戏数据 / 截图，也未暂存、提交或推送主仓库改动；工作范围保持在 `splatoon3-native/`。

### 历史教学路线卡点（2026-10-18 已放弃）

右摇杆教学之后尚未找到稳定离开这片区域的路线；尝试左右转向、前进、跳跃后回到了武器区。
场景存在大面积黑色表面，原有压缩渲染目标 / AlphaRef / 8 位索引红字仍在；但**没有证据将这次导航失败归因于某一条 GPU 红字或碰撞缺陷**。
也没有足够证据排除人工方向判断错误、墙钟 hold 随帧率变化导致的转向偏差，或仍需完成某个教学触发点。

该轮曾计划继续核对教学路线；此计划已被 2026-10-18 的参考存档方案替代，不再继续或复跑教学前缀。
只有完整 M2 图像门槛与入口后十分钟测试 PASS，才更新完成状态、commit + push 并继续 M2.5。

## M2 第 2 轮：参考存档启动 BLOCKED（2026-10-18）

**当前状态：M1 保持历史 PASS；M2 未通过；未 commit / push；M2.5 未开始。**
已按最新 GOAL 放弃开场教学、右摇杆教学及其导航路线。旧前缀和探索产物仅留作历史，
不再作为下一轮推进方案。六轴 16 样本历史修复、`tools/pad.py`、`tools/CONTROLLER.md`
和 M2 测试框架均保留。

### 参考档保护与测试调整

- 从指定原件 `../splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat`
  只读复制到 `work/save_ref/save.dat`，副本权限为 `0444`；未修改原件权限或内容。
- 大小 **188,719 字节**，SHA256：
  `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。
  两次启动前分别用 `shutil.copyfile` 创建独立、可写的 `save/save.dat`，`DM_SAVE` 仅指向运行副本。
  两次结束后重新计算原件及参考档 hash，均与上述值相同。
- `tests/test_m2.py` 已改用同一参考档，每次创建独立副本，预检 hash、记录来源 / hash / 大小，
  结束时检查参考档未变；清除继承的 `DM_*` 配置后设置验收环境。
  保留入口参考图比较和到达后至少 600 秒运行门槛，没有生成虚假的完整路线或入口参考图。
  `--save-ref` 可指定含同一参考档的目录；截图与存档仍仅保存在忽略的 `work/`。

### 两次独立启动的证据

| 运行 | 输入 | NVN 补段耗尽帧 | 退出码 | 产物目录 |
| --- | --- | ---: | ---: | --- |
| 首次导入 | `f1200:ZL+ZR~0.2*4/600`，崩溃时尚未执行 | 113 | -6 | `work/m2/save-probe-20261018-001211/` |
| 独立复核 | `DM_KEYS=""`，无 FIFO | 104 | -6 | `work/m2/save-recheck-20261018-001304/` |

每个目录包含 `input.json`、`host.log`、`exit.json`、`result.json` 及独立运行存档。
复核还保存了 `frame_30.png`、`frame_60.png`、`frame_90.png`、`frame_100.png`。
人工检查第 100 帧是黄绿 / 紫色加载过渡画面，**尚不能确认已进入可操作的广场或大厅**。

两次日志均有 `fs open ... saveMount:/save.dat mode=1`，随后成功写入运行副本并提交事务，
还加载了 `content:/Pack/Actor/Fld_BankaraCity.pack.zs`、`Fld_LocalLobbyBuilding.bfres.zs`、
`DObj_FldObj_DoorTVStationLocalLobby.pack.zs` 等资源。
这些支持游戏已按参考档进入广场加载路径，但不能单独证明全部存档内容有效或入口已可操作。
没有观察到存档损坏提示，也不能将本次失败判定为“存档进度错误”。

### 当前卡点（停止，等下一步指示）

**直接失败**：广场加载期间，宿主先报“游戏回调补不够（需 56 字节），改用宿主补段”，
随后在同一呈现帧内累计申请 4096 个 256 KiB 段，达到 1 GiB 上限并主动中止：

```text
FATAL NVN 命令内存：游戏池已空，宿主补段已达 1024 MB 仍未被游戏的块回收
```

无输入的第二次运行复现同样的失败类型，排除了尚未执行的教学 / 进门按键作为必要触发条件。
未提高内存上限、跳过绘制、修改存档进度或关闭已有同步来掩盖失败。

**待证假设**：广场新增录制路径可能依赖真实 NVN 的 command / control memory 用量及补内存回调语义。
`hle_nvn.c` 的 `cmd_alloc_reserve`、`hostseg_take`、`GetCommandMemoryUsed` / `GetControlMemoryUsed`
值得在后续获准排障时追踪。当前只确认了“同帧补段耗尽”，没有回溯 / 调用方循环证据，
不能断言为泄漏、某个具体函数语义错误或参考档格式不兼容。

参考档启动验证被宿主故障阻断；根据 GOAL.md 的“卡住时把现象、日志、已试假设写进卡点后停下”条款，到此停下。
尚无入口路线、入口参考图或十分钟 soak；不提交推送，不进入 M2.5。

### 验证与范围

- `bash tests/run_all.sh --milestone m2`：Metal **108 checks, 0 failed**、NVN **70 项，失败 0**、
  HID **73 checks, 0 failed**；M2 **FAIL / preflight**，明确缺少完整路线、入口参考图、已验证截图帧。
  产物 `work/tests/m2-20261018-001312-190390/result.json`。这次没有重跑 M1 的 75 秒集成验收。
- 最终版直接执行 `.venv/bin/python tests/test_m2.py` 仍为 **FAIL / preflight**，同样缺少上述三项，
  并正确记录参考档来源、188,719 字节和 SHA256；产物 `work/tests/m2-20261018-001451-995555/result.json`。
- 已重新执行 `bash tools/update-patch.sh`；upstream 源码空白检查、补丁反向应用检查通过，
  外层除补丁上下文外的源码 / 文档空白检查通过。结束时无运行中的 `dmhost`。
- 所有本轮源码 / 文档改动均在 `splatoon3-native/`；父仓库其它工作区改动未暂存或改动。
  原有 `upstream/` 修改保留；补丁仍排除游戏 shader 表与 `c1_full.tsv`。

## M2 卡点第 1 轮：完成（2026-10-18）

**M2 PASS；提交推送后进入 M2.5。** 本轮按指示先取来源证据，再修复并完成参考档路线的入口及十分钟验收。

### 1 GiB 命令补段的直接原因

- 增加按呈现帧 / 命令缓冲对象 / guest LR / 命令类型聚合的 `DM_NVN_MEMTRACE=<起始帧>`。
  表固定 4096 槽，普通事件只打印前两次和 2 的幂次计数；补段和结束事件逐条打印。
  默认关闭，不改变录制内容，不复制游戏代码或资源。
- `work/m2/memtrace-full-20261018-004502/{host.log,summary.json}`：同一帧的 **4097 次补段对应 4097 个不同的 BEGIN**，
  同一 BEGIN 最多补一次。来源为 `main+0x4672c84` **3689 次**、`main+0x4672ba8` **408 次**，分散在 6 个录制缓冲对象。
  已完成的 4096 条补段录制，其 `logical_used - guest_used` **全部为 40 字节**：最后一条 32 字节 `OP_BIND_UBO` + 8 字节 END。
- 旧实现每条尾段固定借出 **256 KiB**，4096 条就耗尽 1 GiB，实际尾段总量只有 **160 KiB**。
  这是有限的大批材质缓存录制被宿主分配粒度放大；本轮证据不支持同一条录制反复增长的死循环假设。
- 调用点通过 `tools/nsosym.py` 输出到 `work/m2/memtrace-symbols.txt`。
  main 的这些内部方法已剥离符号，工具的最近导出为 past-end，不能据此虚构类名；
  调用类型由实际 `OP_BIND_UBO` 记录与调用点反汇编确认。

### 回调与 END 边界核对

- 实际注册的回调是 `main+0x45c44fc`，反汇编只有一条 `ret`；证据 `work/m2/memory-callback-dis.txt`。
  内存不足时宿主确实调用两次，前后 cursor / end 不变，没有新的 AddCommandMemory 给块被忽略。
  典型 minSize 是 **56 字节**，即本宿主的 32 字节记录 + 24 字节后续链接余量。
- M1 的 END 分配规则保留：只分配自身 8 字节。原有 88 字节段、72 字节实际用量及邻接 BEGIN 保护检查继续通过。
  本次补段发生在最终 UBO 绑定，已完成尾段的 END 没有再开新段；没有恢复旧 END 预留或取消查询同步。
- 回调优先仍保留。新增有效回调检查证明：游戏在回调给出的新块被采用，cursor 位于游戏池内，宿主补段池没有增长。
  不修改忽略 control-memory 计数等其它语义来掩盖本次问题。
- 补段改为按请求大小分配，最小 256 字节，大记录分配能完整容纳记录及链接余量的容量。
  总上限仍是 1 GiB，回收仍由原游戏内存范围复用触发。
  新增 5000 条短缓存列表的有界内存、内容保留、回收复用，以及超过旧固定段大小的记录检查。

### 后续真实运行暴露的资源生命周期问题

- 命令补段修复后能直接读档进入可操作的 Bankara 广场。
  但旧图形资源回收使常驻在约一分钟内超过原有 24 GiB 上限，例如
  `work/m2/lobby-explore-20261018-004815/host.log` 第 1500 帧为 **26787 MB**，退出码 86。
  未抬高或关闭看门狗。
- `defer_drain()` 原先可在无外层 autorelease pool 的 guest / Metal feedback 线程上退休资源。
  增加其自身的局部 pool；撤回了扩大整个提交 pool 范围和给 serial_del 加 pool 的试验，正式修复仅包住退休操作。
  真实 16 MiB Metal 缓冲在线程上退休的回归：旧 body 对照 **110 checks, 1 failed**
  （`work/m2/retire-pool-control.log`），局部 pool 版 **110 checks, 0 failed**。
- 第一次完整 M2 测试 `work/tests/m2-20261018-010805-100338/result.json`：
  入口图像已过（SSIM **0.95099**、RGB MAE **0.01750**），但到达后约 **65 秒**仍因常驻超限退出 86，故 **FAIL**。
  原始失败保留，不以到达截图代替十分钟验收。
- 进一步发现按 pool / offset / description 共享的私有纹理保留了动态分辨率的历史尺寸。
  该次共享表从约两千条增长到 **10298 条**，活跃序号数仅 **5660**。
  现在仅在存储被不同描述复用时，退休重叠且已无活跃序号引用的旧缓存；有活跃序号的解释保留，
  描述符视图缓存随 generation 失效，旧 GPU 引用仍保留到 fence 完成。
  新增检查覆盖活跃别名保留、无主旧描述退休、fence 前后驻留状态；Metal 检查扩展到 **116 项**。
- `work/m2/alias-retire-20261018-011238/` 重新走到私房菜单，至约 6900 帧、131 秒后主动 SIGTERM 优雅退出，退出码 0；
  后段常驻约 **11 GiB**。2400 帧与原独立参考图 SSIM **0.95493**、RGB MAE **0.01604**。
  这仍只是修复探索运行，不代替正式十分钟测试。

### 本地大厅入口的前置依赖与新路线

- 原离线 `nn::ldn::Initialize` 固定返回 `0x2a2`，游戏短暂显示 `Preparing local play...` 后返回广场；
  `work/m2/defer-pool-20261018-010129/host.log` 记录到两次失败初始化。
- 仅 main 构建 `28c4287aee36f7499da60f3e68b54c70`、显式 `DM_LDN_FRONTEND=1` 时，建立进程内空闲上下文（状态 Initialized）。
  实际成功初始化后还调用 `SetProtocol(1)`；未覆盖该服务入口会因 SDK 服务指针为空而崩溃，
  `work/m2/ldn-idle-20261018-010357/host.log` 的 `sdk+0x55f160` 已符号化为 `nn::ldn::SetProtocol + 0x20`。
  现已覆盖协议配置并校验值。状态 / 协议常量参考 [libnx 的 LDN 头文件](https://github.com/switchbrew/libnx/blob/master/nx/include/switch/services/ldn.h)。
- 这只支持显示本地入口；默认及未知构建仍离线。OpenStation、OpenAccessPoint、建房、扫描、加入、数据收发均未实现，
  不报告创建或连接成功。没有开始 M3 的进程间网络实现，没有连接任天堂服务。
  新增 10 项前端检查覆盖开关、构建门控、协议校验、Finalize 和连接操作仍失败。
- 完整路线 `tools/routes/m2-local-lobby.keys`：300 帧 ZL+ZR → 450 帧 X 地图 → 540 / 570 帧 Down（跳过禁用的 City 行，选中 The Shoal）
  → 660 帧 A → 1500 帧 L Match Menu。终点是选中的 **Private Battle / Battle with nearby players** 菜单，不再按确认，不创建房间。
- 独立探索参考图 `work/m2/reference-local-lobby.png` 来自 `work/m2/ldn-protocol-20261018-010604/frame_2400.png`，已人工确认。
  SHA256 `a79f793fda57ae2c01cdeb81bfaef7081192daebc052ebb4dc511272d9e79da0`；来源及检查备注保存在同名 JSON。
  参考图不由验收运行生成，不入库。正式验收截图帧为 2400，默认命令 `bash tests/run_all.sh --milestone m2`。

### 对照与当前验收状态

- `tests/test_m1.py` 新增 `--save-ref`，通过同一 M1 框架复制参考档启动；修复前同样复现 FATAL，
  证据 `work/m2/m1-seeded-before.log`。同期空存档检查通过，支持是广场材质加载路径暴露了补段放大。
- 带前两项修复的 M1 完整回归 `work/tests/m1-20261018-010140-755190/result.json`：**PASS**，75 秒、2700 帧、退出码 0。
- 包含纹理缓存退休修复的空存档回归与 M2 十分钟门槛已重新执行，最终结果如下。
- 最终缓存修复后的空存档一键回归 `work/tests/m1-20261018-011504-796398/result.json`：
  **PASS**，75 秒、3900 帧、退出码 0；600 / 1200 / 2400 帧 1080p 截图通过，无运行时失败标记。
- 新增别名退休检查曾遇到测试时序竞争：GPU fence 被发布时，feedback 回调中的 CPU 驻留表清理尚未结束。
  测试已在 fence 后加入 feedback 队列同步，再检查退休状态；未修改应用的完成信号顺序或放宽期望。
  失败保留在 `work/m2/alias-retirement-race.log`；重跑 Metal **116 项**、NVN **79 项**、HID **73 项**、LDN 前端 **10 项**均通过。
- 当前正式验收产物为 `work/tests/m2-20261018-011812-525657/`，日志入口 `work/m2/m2-final-acceptance-rerun.log`。

### M2 最终验收与交付范围

- `bash tests/run_all.sh --milestone m2`：**PASS，退出码 0**。Metal **116 项**、NVN **79 项**、HID **73 项**、LDN 前端 **10 项**均通过。
- 新的独立参考档副本于 **2400 帧**到达已人工确认的 Private Battle 入口，与独立探索参考图比较：
  SSIM **0.956701**（门槛 ≥0.90）、RGB MAE **0.016059**（门槛 ≤0.06）。
- 到达后持续运行 **600.739 秒**；最后采样为启动后 **660.73 秒 / 37200 帧**，末尾帧数增长。
  无 CRASH / FATAL / 看门狗 / GPU 执行失败；SIGTERM 优雅退出耗时 0.005 秒，宿主退出码 **0**。
- 常驻周期日志峰值 **17054 MB**，末次（35700 帧）**9270 MB**；没有提高 24 GiB 看门狗上限。
  游戏图像仍有此前记录的压缩目标等图形限制；这次通过仅覆盖本地私房入口、图像门槛与十分钟稳定运行。
- 原件和只读参考档在全部运行后 SHA256 均保持
  `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。
- 提交前重新生成补丁，排除 shader 表和 `c1_full.tsv`；补丁反向应用检查及源码空白检查通过。
  只提交 `splatoon3-native/` 的脚本、测试、文档和补丁；存档、截图、日志、游戏模块及父仓库其它工作不入本次提交。
  此时只达到私房入口，尚未建房或验证任何双进程通信；M3–M6 未开始。

## 2026-10-18：M2.5 进行中（未验收、未提交）

M2 已以 `4a51b06` 推送。以下是后续工作区改动，**不表示 M2.5 完成**。

### 多身份与运行时武器拥有判定

- `DM_PLAYER=0..7` 给本进程单一本地账号返回不同 UID，低 64 位为
  `0x78626c0000000001 + player`，高 64 位保持 `0x53574e4154495645`；昵称为 `RL-0` 至 `RL-7`。
  所有本地账号枚举、预选、存在检查与读取接口使用同一身份。默认 UID / `DM_NICK` 行为保留。
  显式参数范围和 main 构建号均检查；未知构建拒绝启用。
- `work/m2/identity-0-20261018-014553/`、`identity-1-20261018-014554/` 的两个真实宿主分别读到
  UID 尾数 `...0001` / `...0002` 和 `RL-0` / `RL-1`，并进入武器界面；均退出码 0。
- 通过 `../splatoon3-decomp/symbols/` 的类名 / 参数字符串定位 `HaveWeaponMap` 和武器元数据，
  再以 NSO 反汇编、游戏调用栈与 UI 读内存验证实际路径。
  `main+0x338b9d0` 是通用物品拥有判定，武器分支从 `main+0x338bbe0` 开始；
  但仅在此处挂钩不能解锁 UI，实际武器 UI `main+0x4401bc0` 内联了拥有表搜索。
- 工作中的 `DM_FULL_UNLOCK=1` **目前只覆盖武器**：武器拥有判定对非负 ID 返回 true，
  UI 的内联拥有判断走 owned 分支；不修改 HaveWeaponMap，不向存档补武器条目。
  仅允许 main `28c4287aee36f7499da60f3e68b54c70`，安装前验证全部原指令，默认不装任何覆盖。
- 本地 WeaponInfoMain BYML 表共有 **331 行**，其中 **174 行 Type=Versus**，每行带原生副 / 特殊组合。
  其余包括 Coop / Mission / Other / Rival，不属于本次 4v4 装备目录。
  UI 遍历全部 331 行，故覆盖拥有判断时必须额外保留 `Type=Versus` 的约束。
  使用已不再可达的内联树搜索代码空间，插入原生类型筛选；装备其它分类仍走原逻辑。
- 第一版类型筛选误把目录行包装对象当成元数据，结果实际 UI 列表为 **0**，没有当作成功。
  证据 `work/m2/weapon-unlock-first-20261018-020437/`。
  探针证明包装对象 `+8` 才指向元数据，修正后 `work/m2/weapon-unlock-typed-20261018-020658/`
  在 UI 实际列表 `+0x668` 读到 `0xae = 174`；截图人工确认武器列表有 15 页。
- `work/m2/weapon-unowned-equip-20261018-020856/` 中，脚本选择末页的 Splatana Stamper Nouveau，
  实际装备 ID 由 `2040` 变为 **8001**，模型与副 / 特殊图标一起切换，退出码 0。
  不使用训练场或单人作为验收替代。
- 新增 `tests/test_m25.py`、`tests/test_host_options.py`：读取本地 BYML 生成预期 ID 集合，
  从原生 UI 列表插入及完成计数采集真实集合；关闭 / 重开界面后再检查，并验证真实账号读接口。
  `--weapons-only` 仅运行组件，结果始终不把完整 M2.5 标为 PASS。
  无该参数时地图 / 模式未验收会使完整测试失败。
- 21 个独立进程单元用例通过，涵盖全部 8 个身份、默认昵称、非法输入、构建与指令门控；
  其中解锁 native-code 单元执行 19 项检查，覆盖有效 / 负 ID、五种元数据类型和装备其它分类旁路。
  Metal 116 / NVN 79 / HID 73 / LDN 10 项在本轮组件验收前重新通过。

### M2.5 卡点：私房地图 / 模式设置的前置依赖

- `work/m2/private-settings-frontier-20261018-020647/host.log`：从已确认的 Private Battle 入口，
  第 2700 帧按 A 后调用 **`LDN OpenStation: unavailable`**。当前前端仅初始化，未提供 Station / AP / 房间。
- 第 2700 帧截图仍为 Private Battle 菜单；该次 70 秒运行因并行运行变慢，未到后续截图帧，
  因此不声称已经用该图看到地图 / 模式设置或错误对话框。
  另一次提前在 1800 帧按 A 的试验（`work/m2/private-settings-blocked-20261018-020919/`）
  未命中 OpenStation，2100 帧仍为广场；它不是有效的设置界面证据。
- **地图 / 模式拥有判定尚未实现，也未覆盖实际私房设置的全部选项。**
  仅凭武器 174 项和多身份不能签收 M2.5；当前卡在进入设置前的 LDN Station / 房间依赖。
  不把 OpenStation / 建房服务改成固定成功来伪造通过，不开始 M3 网络实现。
  完成当前武器 / 身份组件的独立验收与补丁整理后，按卡点规则停下，等待里程碑顺序或依赖处理指示。

### M2.5 武器 / 身份组件正式结果

- `bash tests/run_all.sh --milestone m25 --weapons-only`：退出码 **0**，仅组件通过。
  `work/tests/m25-20261018-021115-405220/result.json` 明确记录
  `weapons_passed: true`、`identity_passed: true`、**`passed: false`**。
- 关闭覆盖的真实 UI 列表为 **101 个唯一 ID**；启用覆盖的两个真实宿主，各在首次进入与关闭重开后
  读到 **174 / 174 个唯一 ID**，每次 ID 集合都严格等于本地 `Type=Versus` 全目录；无缺项、无额外条目。
- 两个进程最终装备 ID 均为 **8001**，该 ID 不在 101 项对照中；退出并重新打开装备界面后仍保留。
  UI 截图非空且为 1920×1080，两次宿主优雅退出码均为 0，无运行时失败标记。
- 读取侧身份分别为 `78626c0000000001:53574e4154495645 / RL-0` 和
  `78626c0000000002:53574e4154495645 / RL-1`；不是仅输出环境变量。
- 游戏目录表 SHA256 `fdfddc6bce0ac83460eba37cbafcbf0e4afd2548faf5664dc8f3a47c65ac7681`，
  原件及只读参考档测试前后仍为指定 SHA256。新武器选择由游戏自身保存到运行副本，未修改原件或参考档。
- 账号首次读日志改用原子的一次标记以避免多线程重复打印；随后重建宿主，重新跑 21 个选项用例通过。
  补丁已重新生成并反向应用检查通过，新增 upstream 文件已纳入补丁；游戏数据、截图及日志未入库。
- M2.5 未达地图 / 模式门槛，所以本轮相关补丁、测试、文档作为未提交工作区改动保留；
  **没有为 M2.5 commit / push，没有开始 M3**。

### 私房前置依赖的最终补证与停止位置

- `work/m2/private-settings-final-evidence-20261018-021601/`：使用最终宿主、全新参考档副本，独立运行 **100.053 秒**，退出码 **0**。
- 2400 帧截图与 M2 入口参考图 SSIM **0.957457**、RGB MAE **0.015140**，确认 A 键之前仍在正确的 Private Battle 菜单。
- 第 2700 帧按 A 后日志出现 **`LDN OpenStation: unavailable`**。
  已人工检查 3000、3600 帧截图：均退回 **Bankara 广场**，没有进入私房 / 地图 / 模式设置界面。
  同目录 `summary.json` 保存输入、比对结果、人工检查结论与退出结果。
- 最后再次核对原件及只读参考档：均为 188,719 字节，指定 SHA256 不变，参考档权限仍为 0444。
- 此处已完成能独立推进的武器 / 身份工作，**停在 M2.5 的地图 / 模式卡点**。
  需由里程碑制定者决定是否先开放相应 M3 前置依赖，再继续实际私房设置验收；本轮不自行扩大实现范围。

## 2026-10-18：M2.5 按调整后的范围验收

GOAL.md 于 2026-10-18 将地图 / 模式解锁与私房设置验证移到 M4；M2.5 的完成条件现在是武器全解锁与多身份。
上文关于地图 / 模式导致完整 M2.5 不能 PASS 的结论是调整前的历史记录，不再是当前验收门槛。

- `tests/test_m25.py` 已同步范围：武器 / 身份全过才输出 `passed: true`，地图 / 模式明确标为
  `deferred_to_m4`，未声称这些功能已经实现；`--weapons-only` 保留为兼容别名。
- 重新运行 `bash tests/run_all.sh --milestone m25`，产物目录
  `work/tests/m25-20261018-022316-033235/`，总入口日志 `work/tests/m25-adjusted-acceptance.log`。
- 21 个独立进程用例、Metal 116 / NVN 79 / HID 73 / LDN 前端 10 项检查均通过。
- **M2.5 PASS / 完成**：最终 `result.json` 为 `passed: true`、`weapons_passed: true`、
  `identity_passed: true`、`errors: []`。对照为 101 件；两个启用宿主均首次 / 重开为 174 / 174 件，
  集合严格等于本地 Versus 目录，末页新武器 8001 实际装备并保持。身份读取分别为 RL-0 / RL-1，UID 不同。
  三个真实宿主退出码均为 0，无运行时失败标记，参考档与原件 SHA256 均未变。
- 已重新生成补丁并通过 upstream 反向应用检查与源码空白检查；补丁继续排除 shader 表和 `c1_full.tsv`。
  只提交 `splatoon3-native/`。M3 在该提交推送之后开始；地图 / 模式仍待 M4。

## 2026-10-18：M3 虚拟本地通信实现与真实验收

M2.5 已按调整后的口径完成并以 `b5c0f99` 推送，随后开始 M3。下列组件通过本身不代替双游戏验收。

### 实现与无游戏检查

- 新增 `tools/ldn/air.py`：独立的 Unix domain socket 空气服务；每次实验一个 socket / 房间域，
  权限 0600，已有路径不覆盖，进程身份 0..7 不可重复注册。无 OS IP socket、外部网络或在线服务。
- `upstream/dm/host/hle_ldn.c` 替代原空闲 LDN stub。实现 Station / AP、创建 / 私有创建、扫描与过滤、
  加入 / 私有加入、NetworkInfo / IPv4 / SecurityParameter、广播数据更新、节点历史、接纳策略、拒绝和退出。
  状态由服务确认并异步发布；SystemEvent 接到真实内核事件。仅显式 `DM_LDN_AIR` 和已知 main 构建启用，
  要求 `DM_PLAYER=0..7`；未启用时保留离线与 M2 空闲前端。
- 游戏的 PIA 代码继续原生运行；`nn::socket` 的 UDP / Poll / EventFd 接到同一服务的虚拟描述符和数据队列。
  数据只能发给同房成员或该虚拟子网广播；队列有界，离房会清空旧包，外部目的地址拒绝。TCP / DNS / SSL 继续不可用。
- 扫描返回从创建参数构造、由后续 SetAdvertiseData 原样更新的 NetworkInfo；会话、用户节点、版本和信标一致。
  使用 libnx / Switchbrew 的公开 ABI 布局，并核对本地 SDK 22 C++ 包装器（NetworkInfo 0x480、ScanFilter 0x60、
  UserConfig 仅复制前 32 字节，LDN IPv4 为 host order、BSD sockaddr 为 network order）。
- `tests/test_ldn_air.py` 用两个独立 C 假客户端直接调用与 dmhost 同一份 HLE，不读取游戏文件。
  当前 **59 项检查全过**：状态前置条件、会话 / 信标、Scene / Channel / NetworkType 过滤、密码 / 接纳策略、
  双方节点、事件、IPv4 / 安全参数 / 历史、双向收包、Poll / EventFd、复用端口、错误号、离房与退出清理、重初始化。
  最终整合入口组件产物：`work/tests/ldn-air-20261018-025205-536818/`。
- `tests/run_all.sh --milestone m3` 先构建并检查通用组件、虚拟 LDN 组件，再启动独立参考档的 A、B。
  A 真实建房后才启动 B；要求扫描 / 加入同一会话、宿主最新状态同房两节点、双方实际收包，并稳定十秒。
  保存每次独立的路由、截图、日志、结果，始终核对参考档与原件 SHA256。完整入口不因组件通过而直接 PASS。

### 真实游戏暴露并修复的问题

1. 最初数轮已完成真实 OpenStation / 空扫描，但游戏显示通信错误并回广场，尚未建房。
   `work/m3/explore-20261018-023107/`、`023307/`、`023502/`、`023718/` 保留。
   游戏在 `main+0x9576cc` 轮询 GetNetworkInfo，并显式忽略 `0x40cb` 的 LDN InvalidState 范围；
   通用离线 `0x2a2` 会被记录为通信故障。改为真实 LDN 状态错误后，`work/m3/explore-20261018-024005/frame_3000.png`
   已人工确认进入 Rooms / Y Create a Room；未在空闲状态伪造网络信息成功。
2. 从房间列表切到创建时，游戏 Finalize / 重新 Initialize 并复用 SystemEvent 存储。
   宿主绑定表保留已关闭的写句柄，触发 `SystemEvent 写端句柄失效 0x1030`。
   新增显式清除绑定，等 reader 不再触发后才允许 guest 销毁 / 复用；服务还确认释放身份，避免重连竞争。
3. NetworkType 应为 LDN 位 2，扫描按 bitmask 匹配；与是否 Private 无关。
   同时保留游戏传入的 Scene、SessionId、节点和信标；没有注入固定游戏房间或 erepo 信标。
4. 首次完整验收 `work/tests/m3-20261018-024250-143375/` 已真实 CreateNetwork、发布游戏信标、
   创建 UDP socket 并 Bind 12345，但 SO_REUSEPORT 0x200 尚不支持，后续房间撤销；该次 FAIL 保留。
   加入该选项和两端均须启用的绑定语义，并以组件检查覆盖。
5. 第二 / 三轮 `work/tests/m3-20261018-024531-282572/`、`024856-176835/` 继续在建房后撤销。
   第三轮取得原始 ErrorResultVariant：类型 1、Result `0x33d73e`，即 **2318-6635**；
   游戏非阻塞收包路径为 `main+0x92c490`，flags=0x80，重试错误按 SDK 的 errno **11** 处理。
   空队列原先用了 BSD / Darwin 的 35，导致游戏把正常空读当成故障。现将服务 wire errno 转成 SDK 的 Linux/newlib 编号，
   包括 EAGAIN=11、EADDRINUSE=98、ENETDOWN=100、ENETUNREACH=101；LDN Result 与 socket errno 分开处理。
   同时修正 SendTo 的有符号 -1 返回（避免 uint32_t 条件表达式变成正 4294967295），加入原生执行检查。
- 第四轮正式入口：`work/tests/m3-20261018-025206-059726/`，总日志 `work/tests/m3-acceptance-fourth.log`。
  Metal 116 / NVN 79 / HID 73 / LDN 前端 10、21 个身份 / 解锁进程用例和 59 项 LDN 检查均通过；
  真实游戏阶段的最终结论记在下方。

### 第四轮通信验证（有诊断输入，完整自动路线另跑）

- A 稳定建房，B 的真实 Scan 返回 1；`player-1/frame_3000.png` 已人工确认 **RL-0 / Joinable**。
  扫描返回的会话 ID 与游戏发布信标和房主一致：`200afdf4b656b3313ac3a0fe6575984b`。
- B 的 3900 帧 A 只打开 **Join this room?** 对话框，4200 帧截图确认仍待第二次确认。
  本轮通过 FIFO 诊断补按 A，记录在 `diagnostic-input.json`，因此不把它当成最终全自动验收。
- 补按后真实 Connect 成功：A 为 state=3 / node=0 / nodes=2，B 为 state=5 / node=1 / nodes=2。
  两个游戏实际通过 UDP 从服务取出对方帧，日志至少到双方各 64 帧，稳定同房十秒后均正常退出。
  没有再出现 2318-6635，证明 errno 修正让真实 PIA 通信继续推进。
- 自动路线补上 B 的 `f4500:A` 二次确认。最后一轮重新使用全新存档副本、全自动输入，
  接收证据也按完整 session 对齐；最终验收结论在下方，不以这次诊断补按代替。

### M3 最终全自动验收与交付

**M3 PASS / 完成。** `bash tests/run_all.sh --milestone m3 --timeout 360` 返回 **0**。
最终产物为 `work/tests/m3-20261018-025742-268957/`，总日志 `work/tests/m3-acceptance-final.log`。

- 全新参考档副本、全自动 DM_KEYS，无补按或游戏状态改写：A 在 2700 帧进入房间列表、3300 帧 Y、3900 帧 A 建房；
  B 在 2700 帧扫描、3900 帧选中 RL-0、4500 帧确认加入。完整输入保存于各进程 `input.json`。
- 服务确认 A 创建、B 扫描并加入同一完整会话 **`5e237a024b437776ac1121d30ceba948`**。
  扫描信标直接来自 A 游戏的 SetAdvertiseData，字段与房主 NetworkInfo 一致；没有虚构扫描结果。
- 两个宿主最新状态：A **AP-created / node 0 / nodes 2**；B **Station-connected / node 1 / nodes 2**。
  双方各从服务实际 Recv 至少 **128 个**该会话的数据帧，服务转发累计至少 256 帧；原生 PIA 继续运行。
  同房稳定 **10.164 秒**，通过十秒门槛。
- 人工检查 B 的 `frame_3000.png` 显示 **RL-0 / Joinable**；`frame_4800.png` 已进入私房，列表同时显示 **RL-0 与 RL-1**。
  图像只留 `work/`，不入库。该画面不是地图 / 模式全解锁验收，没有开始 M4 对战。
- 两个宿主优雅退出码均为 **0**，最后采样帧分别 **9000 / 4800**；无 CRASH / FATAL / 看门狗 / GPU 执行失败。
  原件与只读参考档前后 SHA256 仍为指定值。通用组件、21 个身份 / 解锁进程用例、59 项虚拟 LDN 检查均通过。
- 重新生成 `patches/0001-splatoon3.diff`，继续排除游戏 shader 表和 `c1_full.tsv`。
  通过当前源码反向应用检查、独立临时 index 对 upstream HEAD 的正向应用检查，以及源码空白与 Python 语法检查。
  仅提交 `splatoon3-native/` 内源码补丁、脚本、测试和文档；游戏数据、存档、日志、截图及父仓库其它工作未提交。
- **当前下一里程碑是 M4**：实际 1v1 私房开局并到结算，同时补地图 / 模式全解锁及全选项验证。
  M3 完成不表示 M4、4v4、多开资源优化或 RL step 接口已经完成。

## 2026-10-18：M4 地图 / 模式与 1v1（验收进行中）

M3 基线为 `3522186`。本轮只推进 M4；下列诊断结果本身不表示完整 M4 PASS。

### 地图目录与两处赛季过滤

- 以本地 11.3.0 的 `RSDB/VersusSceneInfo.Product.b30.rstbl.byml.zs` 为权威目录：共 26 行，
  **25 行 `IsDisplayInStageList=true`**，ID 为 1..24 和 26；ID 25 / `Vss_Manbou00` 标为隐藏，不纳入普通私房地图。
  ID 26 是 Urchin Underpass；目录保留原生场景名 / 布局，不导入外部游戏数据。
- 原始 `?/19` 受参考档的已解锁赛季 **4** 限制。`main+0x39047d0` 构建房间地图列表，
  `main+0x39049f4` 的 `b.gt` 排除目录 Season 高于上限的行。
  第一版只绕过此处，原生列表实测 25 个唯一 ID、完成计数 25，房间卡片变为 `?/25`，但这不够。
- `work/tests/m3-20261018-031124-289123/player-0/frame_7800.png` 保留了第一版的反例：
  实际选择面板仍为 **19 项**。`Cmn_SelectStage_00` 通过 `main+0x31f4ff0` 另建目录，
  `main+0x31f52d8` 有独立的赛季过滤；已补上第二处覆盖。
- 两处覆盖都只将赛季 `b.gt` 改为 NOP，继续保留 `IsDisplayInStageList` 检查。
  沿用 `DM_FULL_UNLOCK=1`、main 构建号 `28c4287aee36f7499da60f3e68b54c70` 和全套原指令预校验；
  默认关闭，不修改拥有表或参考档。模式无需新增覆盖：Turf War、Splat Zones、Tower Control、Rainmaker、Clam Blitz
  在原生私房中已全部可选，第二轮固定输入实际轮选并保存截图 / 本机 OCR。
- `t_spl3_unlock` 扩展到开启时 **61 项原生执行检查**：两处显示标记 / 赛季过滤覆盖显示与隐藏、Season -1..8、
  关闭 / 开启两种情况，并保留武器及分类检查。21 个身份 / 开关 / 构建 / 签名进程用例通过。

### 开局路线与网络诊断

- 第一轮 `work/tests/m3-20261018-030520-058679/` 用 FIFO 找到实际队伍设置路线；
  `player-0/frame_11400.png` 确认 RL-0 = Alpha、RL-1 = Bravo。
  该轮仍由 M3 的 120 秒同房保持门槛结束，不能作为 M4 整局验收。
- 第二轮 `work/tests/m3-20261018-031124-289123/` 使用全自动 DM_KEYS：A 建房，B 加入，
  五模式轮选、地图面板翻页、选 Scorch Gorge，A 把两人分别设为 Alpha / Bravo 并开始，双方确认准备。
  `player-0/frame_13500.png` 已加载地图，`player-1/frame_9600.png` 为实际对战 HUD，时间 **2:51**。
  为切换到包含两处地图修复及完整判定的正式入口，主动中止此诊断；两宿主均优雅退出 0，
  该目录的 `result.json` 为 `passed: false`，不以诊断运行代替正式验收。
- 空气服务新增每五秒逐端 metric：完整 session、收 / 发数据报与 payload 字节、当前排队、队列峰值、丢包数。
  保留既有每 socket 256 包上限。第二轮到入图时队列峰值 2、丢包 0；没有通过加大队列或跳过同步来制造开局。
- 新增 `tests/test_m4.py`，接到 `tests/run_all.sh --milestone m4`：动态核对房间列表和实际选择面板的完整 ID 集合 / 完成计数，
  本机 Vision OCR 核对五模式与双方 Victory / Defeat，并要求双方实际进入 InGame / ResultJudge / ResultWinners，
  从 InGame 到判定至少 178 秒。探针只采样，不改写比赛、队伍、倒计时或结算。
  独立存档副本、原件 / 参考档前后 hash、运行错误与优雅退出仍作为硬门槛。
- 最终入口已启动：`bash tests/run_all.sh --milestone m4 --timeout 1200`，总日志 `work/m4/acceptance-final.log`，
  产物 `work/tests/m4-20261018-031759-249564/`。
  前置 Metal 116 / NVN 79 / HID 73 / LDN 前端 10、21 个进程用例、59 项虚拟 LDN 检查通过。
  **正式双游戏整局结果待本节后续记录；当前不签收 M4，不 commit / push。**

### M4 最终全自动验收与交付

**M4 PASS / 完成。** `bash tests/run_all.sh --milestone m4 --timeout 1200` 返回 **0**。
最终产物 `work/tests/m4-20261018-031759-249564/`，总日志 `work/m4/acceptance-final.log`；
`result.json` 为 `passed: true`、`errors: []`。上文“进行中 / 待结果”为验收过程记录，以本节为最终结论。

- 全新参考档副本，全程固定 DM_KEYS，无 FIFO 补按、无队伍 / 倒计时 / 结算内存改写。
  A 建房后启动 B；完整同房会话 **`5a6b3f91b5df99a30ae03b761f83186e`**。
  A 选涂地 / Scorch Gorge，RL-0 = Alpha、RL-1 = Bravo，双方自动确认准备并实际入图。
- **地图选项 25 / 25**：房间地图列表与实际选择面板的唯一 ID 集合都严格等于本地可显示目录，
  无缺项、无额外项，两处完成计数都是 25。`player-0/frame_7500.png` 人工确认第二页追加地图及 `?/25`；
  `frame_8100.png` 确认第三页 Urchin Underpass。不是只检查房间卡片。
  目录 SHA256 `bd69f94732014b6bbdd6fd2f9c89d0f67333ac84a1714faffd74069d5af09367`。
- **五模式全部可选**：`settings-ocr.jsonl` 从原生设置截图依次识别 Turf War、Splat Zones、Tower Control、Rainmaker、Clam Blitz，
  `result.json` 五项均为 true；没有为已开放的模式增加无必要覆盖。
- **完整 1v1 到双端结算**：A 的 InGame / ResultJudge / ResultWinners 相对宿主启动时间为
  **363.4446 / 549.4420 / 564.9022 秒**；B 为 **262.4213 / 448.3558 / 463.4163 秒**。
  对局进入至判定分别 **185.9974 / 185.9345 秒**，中途不输入；倒计时自然走完。
  已人工复核 A `frame_21000.png` 的 **VICTORY**、B `frame_16500.png` 的 **DEFEAT**，
  与原生序列探针及本机 OCR 一致；双方随后都到个人结算 / 装备画面。
- 空气服务最后 590.113 秒采样：A 发 **4247 包 / 555451 payload 字节**，B 已全部取出；
  B 发 **4298 包 / 556370 payload 字节**，A 已全部取出。双方当时排队 0，整个采样周期队列峰值均为 **2**、丢包 **0**。
  大厅、入图、对战、结算均使用同一 PIA / 虚拟 LDN 会话；没有绕过 PIA 或伪造对端消息。
  此局无需修改队列容量、时钟或额外同步逻辑。
- 两个宿主均优雅退出 **0**，最后采样帧为 **21900 / 17700**；无 CRASH / FATAL / 看门狗 / GPU 执行失败。
  原件及只读参考档前后 SHA256 保持指定值。截图、日志、存档副本、OCR 产物和本地游戏目录不入库。
- 完整入口前置的 Metal 116 / NVN 79 / HID 73 / LDN 前端 10、21 个身份 / 门控进程用例和 59 项虚拟 LDN 检查全过。
  解锁原生执行检查开启时 61 项，关闭时保留两个赛季限制及隐藏标记。
  重新生成源码补丁，排除 shader 表和 `c1_full.tsv`；当前源码反向应用、独立临时 index 对 upstream HEAD 的正向应用、
  源码空白检查、Python 语法及 shell 语法检查通过。

当前边界：本次跑完的是 **Scorch Gorge / 涂地 1v1**；25 地图及五模式的全选项已验收，
没有声称每个地图 / 模式组合都各跑完一局。胜利动画仍可见角色模型渲染缺件（如 `frame_21000.png`），
本轮不把流程 / 网络 PASS 扩大为完整图形正确性。**下一里程碑 M5，尚未开始 4v4、省资源改造或 RL 接口。**

## 2026-10-18：M5 资源优先（进行中）

起点为已推送的 M4 `e6a92c7`。本节记录 M5 的资源剖析、实现和分级准入；
**下列单进程 / 组件结果不是 M5 的 4v4 PASS，最终结论见本节后续记录。**

### 先测量，以及旧日志的口径纠正

- M1 Max / 64 GiB；开始时没有 dmhost，系统已有约 **13,755.5 MiB swap**。
  这是其它历史负载留下的基线，不作为本任务可使用的余量；本轮不关闭其它应用、不调整 swap。
- 旧 `[nvn-mtl] 内存 ... 常驻` 字段实际来自 `TASK_VM_INFO.phys_footprint`，**不是 `resident_size` / RSS**。
  本轮将新日志标签改为“物理占用”，`DM_MEMSTAT` 同时记录 footprint、RSS、guest / code / malloc / GPU VM 分类、
  Metal 分配、压缩页。Metal no-copy pool 与 guest 内存重叠，不能将 Metal allocated 与 RSS 相加。
- M4 宿主基线剖析：`work/m5/baseline-20261018-033142-737848/`。
  房主先单独启动，建房后才启动一个对端；大厅与对战按焦点进程分别计量，不能把这称为单机独自开始的 1 人比赛。
  仅为取对战样本，双方入图约 40 秒后主动正常退出；其 `result.json` 按 M4 整局门槛为 false，**不代替 M4 / M5 正式验收**。
  最初将基线可执行文件移到 `work/m5/`，相对 shader 表路径失效，产生一次 FATAL；
  失败保存在 `baseline-20261018-033122-202870/`，改用 host 目录中的独立基线副本后重新测量。
- 基线焦点宿主 footprint 峰值 **12,477 MiB**。大厅稳定时约 **4,648 MiB**；
  对战 InGame+10..35 秒平均 **5,004 MiB**，该窗末样本为 4,899 MiB、Metal allocated 4,110 MiB、
  guest 分类常驻 1,799 MiB、code 148 MiB、malloc 186 MiB。
  `work/m5/baseline-vmmap.txt` 的大厅快照中，GPU owned/unmapped 约 2.2 GiB、guest/Metal 共用映射约 1.5 GiB。
  这些分类存在重叠；未将 VM region 常驻之和当成唯一物理内存。
- 命令分配器约 0.15–0.17 GiB；命令 spill 只有数 MiB，均不是几 GiB 占用的大头。
  低分辨率仍保留原游戏贴图、原生渲染和 GPU 状态。启动时存在远高于稳定值的 Metal/driver 分配峰值，
  不能用稳定值乘 8 后同时冷启动。

### 当前实现与已通过的独立检查

- `DM_HEADLESS=1` 抑制 `DM_WINDOW` 建窗，跳过最终 host composition / drawable / screen present；
  保留游戏 NVN / Metal 命令执行、交换链推进及显式原始截图诊断。记录真实内部 pass / draw / frame 与 host 提交计数。
  headless 未显式指定 `DM_OPMODE` 时默认 handheld；多开入口显式传入 `DM_OPMODE=0`。
- 掌机有效区域实际为 **`WindowCrop 0,0 1280x720`**。原始交换链仍由游戏分配为 1920×1080，
  因而原始截图尺寸本身不能证明是否使用 720p；未用宿主缩放伪装降低内部渲染分辨率。
- Mac loader 从同一 `.patched.bin` 做 file-backed `MAP_PRIVATE` 映射，text / patch 为 RX；
  relocation / data / key 与显式运行时覆盖按 COW 私有化，不把地址相关重定位写回磁盘。
  RomFS 的只读打开使用 `PROT_READ|MAP_SHARED`，关闭时 unmap；guest 的 ReadFile 输出仍须复制，因为游戏可修改输出缓冲。
  shader 文件加载已有 mmap，本轮显式使用 `PROT_READ|MAP_SHARED`。
  本机无 Xcode，shader 文件包含 MSL 源码并由 Metal 运行时编译；**没有声称 Metal 内部编译对象 / 管线也成为跨进程共享页**。
- 宿主派生渲染管线缓存上限 2,048、计算管线上限 512；退役对象保留到 GPU fence 完成。
  headless 主命令 allocator 上限从 8 限到 3，不分配最终呈现专用 allocator / buffer；命令 spill 硬上限从 1 GiB 降至 128 MiB。
  不按年龄丢弃可能含有效 GPU 状态的渲染目标 / 贴图。
- 新增 `DM_WEAPON=<Versus ID>`：在已验证 11.3.0 本地玩家参数构造路径的两次武器读取处给出请求值，
  由原生目录生成 main/sub/special kit；不修改参考存档，不覆盖远端 PIA 参数。
  构建号与两条原指令均验证后才修改；测试入口从本地 Versus 目录验证参数是否合法，并读取 native kit 证明实际取值。
- 已通过：Metal 条件渲染 116 项（普通与 headless）、NVN 79、文件系统 74（含 mmap offset / EOF / 负偏移 / close/reopen）、
  身份 / 解锁 / 武器 32 个独立进程用例、虚拟 LDN 59 项。
- `tests/test_m5.py` / `tools/m5_resources.py` 保存每两秒系统与逐进程样本、controller 输入、VM / footprint 快照；
  每个新进程入房并度过启动峰值后才启动下一个。新增 swapout、swap 比启动基线增长超过 16 MiB、
  内存压力非 normal 或本任务 footprint 合计超过 44 GiB 即停止并回收本次宿主。
  只读项目文件的共享页另按 backing inode + file offset、实际 PRESENT/EXTERNAL、非 DIRTY/COPIED 的页查询去重；
  不把所有 external_pager 映射（其中包括 Metal guest pool）都当成可跨进程共享的文件页。

### 单进程低资源大厅验收

- `work/tests/m5-1p-20261018-033802-977810/`：`--players 1`，`phase_passed: true`、`passed: false`（未完成 4v4）。
  同时设置 `DM_WINDOW=1` 与 `DM_HEADLESS=1`，确认不建窗；720p 有效 crop、内部 pass / draw 持续增长、
  screen submit / composite 为 0，达到第 6,000 帧后优雅退出 0，参考档与原件 hash 不变。
- 4,200 帧后的采样区间约 **52.09 fps**；最大 footprint **4,126 MiB**、最大 RSS **2,028 MiB**，
  最后 footprint **3,880 MiB**、Metal allocated **3,282 MiB**、guest 常驻 **1,629 MiB**。
  冷启动 footprint 峰值仍为 **10,039 MiB**，因此 ≤6 GiB 目前指稳定运行，不能扩大为冷启动全程峰值。
  大厅 `footprint` 快照为 3,849 MiB，GPU owned/unmapped 1,790 MiB、guest 1,628 MiB、malloc small 162 MiB。
- 第一版 memstat 的 `clean_file_resident` 仅按 external_pager 统计，误包含 Metal 映射；
  该旧字段约 1.1 GiB **不能作为共享节省量**。后续已要求真实 backing pathname，并增加按页去重的项目文件快照。

当前正在运行两进程完整对战验证；4 / 8 进程尚未签收。所有游戏数据、存档、截图与日志只在 work/，本轮暂不 commit / push。

### 两进程低资源整局通过

- `work/tests/m5-2p-20261018-034011-814855/`：`--players 2 --weapons 8001,2040 --timeout 1000`，
  **`phase_passed: true`、`errors: []`、`passed: false`（尚不是八端 M5）**。
  固定初始 DM_KEYS 加已记录的自动 FIFO 控制器脚本，完成 Scorch Gorge / Turf War 的 1v1。
- 原生 kit 多次读回：RL-0 均为 **8001**、RL-1 均为 **2040**；实际对战截图 `player-0/frame_16200.png`
  可见 Splatana、双方武器 HUD 及运行中的倒计时。不是仅打印请求参数。
- A 的 InGame / ResultJudge / ResultWinners 为 **312.6198 / 498.5976 / 509.2032 秒**；
  B 为 **220.6556 / 406.6102 / 417.1031 秒**。入图到判定分别 **185.9778 / 185.9546 秒**，自然走完整局。
  两端最终帧 **21,600 / 17,400**，都优雅退出 0，参考档与原件 hash 不变，无运行 / GPU 失败标记。
- 对战阶段 FPS **33.83 / 36.57**；单进程低资源大厅参考 **52.09 fps**，场景 / 人数不同，
  这个比值不是严格同负载的并行加速比。双端大厅为 **42.66 / 41.17 fps**。
- 对战稳定 footprint 最大 **4,470 / 3,843 MiB**，RSS 最大 **2,208 / 2,223 MiB**。
  入图快照 group footprint **8,335 MiB**；全阶段采样最高 footprint 合计 **9,418 MiB**，RSS 合计 **4,494 MiB**。
  全阶段 GPU 利用率平均 **82.57%**（AGX 全机指标）；swap 增长 **0**，压力始终 normal。
- 本轮的旧 `clean_file_resident` 字段仍包含 Metal 映射，不能用它推导共享量。
  新版宿主在随后四进程准入的两端快照中，通过实际页查询确认：两端各 **99.46875 MiB** clean project file 页，
  inode + offset 去重后合计 **99.46875 MiB**，重复部分 **99.46875 MiB**。
  产物 `work/tests/m5-4p-20261018-034929-733670/joined-2-shared.json`；没有将 guest / GPU 私有页算入共享。

四进程正按顺序加入，仅验收同房和资源；通过后才启动八端整局。当前未签收 M5，未 commit / push。

### 四进程资源准入通过；正式八端入口已启动

- `work/tests/m5-4p-20261018-034929-733670/`：`--players 4 --admission-only --weapons 8001,2040,10,3000`，
  `phase_passed: true`、`errors: []`、`passed: false`。四个真实宿主依次加入会话
  **`e3eaa0bfd758312e81699e2d3ac68fd8`**，此阶段只检查同房 / 资源，没有开始 2v2 或将其当作 4v4。
- 四端实际 native kit 分别为 **8001 / 2040 / 10 / 3000**；最终帧 **29,100 / 24,360 / 15,360 / 6,060**，
  全部优雅退出 0。第三 / 四个进程各经历了约 73 / 84 秒运行时 shader 源码冷编译，
  长帧主要花在 library / PSO 创建，实际 GPU 执行仅十几毫秒；不是内存压力或 LDN 假成功。
- 大厅阶段 FPS **39.60 / 38.64 / 37.31 / 36.01**；这些阶段均值包含逐个加入的过程，不全部是四端稳定窗口。
  对应稳定 footprint 最大 **4,020 / 3,390 / 3,386 / 3,264 MiB**，RSS 最大 **2,035 / 2,027 / 2,046 / 2,038 MiB**。
  全阶段 footprint 合计峰值 **15,112 MiB**；AGX GPU 利用率全阶段平均 **86.86%**，无新增 swap，压力始终 normal。
- 最终 project clean file 页每端 **96.21875 MiB**，映射合计 **384.875 MiB**，唯一物理文件页 **96.21875 MiB**，
  重复部分 **288.65625 MiB**；见 `lobby-shared.json`。这是明确限定的项目文件页统计，非全机 PSS。
- **wrapper 失败保留**：在该 shell 等待四端 Python 子进程期间修改了 `tests/run_all.sh`，
  子进程已保存通过结果并退出后，shell 用旧文件偏移继续读取新内容，产生末尾引号解析错误、退出非零。
  因此不把本次四端 wrapper 整体称为退出 0；四端 native / 资源数据与通过的独立组件仍有效。
  修正后重新通过 `bash -n`，随后从完整入口开始八端验收；该运行期间冻结入口和被执行源码。
- 正式八端命令为 `bash tests/run_all.sh --milestone m5 --players 8 --mode 0 --stage-id 1 --weapons 8001,2040,10,3000,0,1000,6000,7010 --timeout 3000`。
  总日志 `work/m5/eight.log`，产物 `work/tests/m5-8p-20261018-040151-632282/`。
  前置普通渲染 **128**、headless 渲染 / 呈现旁路 **131**、NVN **79**、HID **73**、LDN frontend **10**、
  host options **32**、文件系统 **74**、虚拟 LDN **59** 全通过。
  八端实际整局结果待下文，当前仍不签收 M5、不 commit / push。

### M5 最终停止位置：八端同房通过，开局加载触发内存压力，整局未通过

**M5 未 PASS；按“不用 swap 硬撑”的约束停止。没有 commit / push，没有进入 M6。**
本节是本轮最终结论，覆盖上文“八端结果待下文”的进行中状态。

- 完整入口 `work/m5/eight.log` 退出 **1**；最终产物
  `work/tests/m5-8p-20261018-040151-632282/result.json` 为 `passed: false`、`phase_passed: false`。
  原始失败、controller、逐秒 memstat、两秒资源采样和全部截图保留，没有以重跑覆盖。
- 八端真实加入同一完整会话 **`603153bc1d223be4015e3cee86072093`**。
  服务最后一次 join 为 `player=7 / host=0 / nodes=8`；全部 HLE 端都读到正确 state / node / nodes=8 和同一 session 前缀。
  八端 UID / 昵称不同，原生 kit 多次读回分别为 **8001 / 2040 / 10 / 3000 / 0 / 1000 / 6000 / 7010**，无回落 ID。
- 八个进程均 `DM_HEADLESS=1`、`DM_OPMODE=0`、原生有效 crop 1280×720；内部 pass / draw 与 frame 持续增长，
  真实 host `screen_submits=0`、`composite=0`。原始截图仅是显式诊断，不上屏。
- 已由固定控制器脚本选 **Turf War / Scorch Gorge（stage ID 1）** 并进入分队 / 准备流程。
  最终准备 A 于启动后约 **1,981.295 秒**对八端同时发送。约 **1,995.315 秒**的开局加载期间，
  `kern.memorystatus_vm_pressure_level` 从 **1 / normal** 变为 **2 / warning**，采样器立即结束实验。
  **所有八端的 InGame / ResultJudge / ResultWinners 均为空**；因此没有 4v4 入图、完整三分钟或结算证据。
  未延长压力窗口、未关闭其它应用、未调整 swap、未再次启动八端。

八端同房后的共同稳定窗口约 **36.23 秒**（所有客户端至少到 5,000 帧，且在第一个设置输入之前）。
以下八行来自同一个八端并发窗口，避免拿早先两端 / 四端时的较高 FPS 当成八端 FPS。
单进程参考为上文 **52.09 fps 的低资源大厅入口**；私房菜单、武器和人数不同，比例仅供资源比较，不是严格同场景加速比。

| 玩家 | 武器 ID | 八端大厅 fps | 单进程参考的比例 | footprint 最大 MiB | RSS 最大 MiB | compressed 最大 MiB |
|---|---:|---:|---:|---:|---:|---:|
| RL-0 | 8001 | 20.91 | 40.13% | 4293 | 1074 | 969 |
| RL-1 | 2040 | 21.24 | 40.77% | 3434 | 1080 | 961 |
| RL-2 | 10 | 21.02 | 40.34% | 3448 | 1071 | 972 |
| RL-3 | 3000 | 21.05 | 40.41% | 3431 | 1065 | 965 |
| RL-4 | 0 | 20.96 | 40.24% | 3213 | 1072 | 955 |
| RL-5 | 1000 | 21.11 | 40.52% | 3114 | 1058 | 970 |
| RL-6 | 6000 | 21.18 | 40.66% | 3101 | 1238 | 977 |
| RL-7 | 7010 | 21.09 | 40.49% | 3141 | 1549 | 591 |

- 该窗口 footprint 合计最大 **27,153 MiB（26.52 GiB）**，RSS 合计最大 **9,205 MiB（8.99 GiB）**；
  GPU 全机利用率平均 **98.92%**、最大 **99%**。每端稳定 footprint 小于 6 GiB，但这不足以证明开局峰值也可接受。
- `joined-8-shared.json` / `lobby-shared.json`：每端项目 clean file 页 **96.21875 MiB**，映射合计 **769.75 MiB**，
  去重后唯一页 **96.21875 MiB**，重复部分 **673.53125 MiB**。统计只含实际 resident、clean、external 且非 copied 的项目文件页；
  不含 mutable guest、GPU private、Metal 编译对象或全部系统 shared libraries，不能当成完整 PSS。
- 资源停止时（**2026-10-18 04:35:06.978 +08**）：任务 footprint 合计 **28,669 MiB（28.00 GiB）**，
  RSS 合计 **9,918 MiB（9.69 GiB）**，八端 compressed 记账合计 **7,710 MiB（7.53 GiB）**。
  因而触发的是系统 warning，**不是 44 GiB 任务上限**。
- 系统 compressor 从本阶段基线 **9,794.05 MiB（9.56 GiB）** 增至 **19,298.52 MiB（18.85 GiB）**。
  同一时刻 AGX `Alloc system memory` 为 **42,207,199,232 bytes（39.31 GiB）**，
  `In use system memory` 为 **24,291,115,008 bytes（22.62 GiB）**。
  这些是全机 driver / kernel / VM 指标，互有重叠，**不得与任务 footprint / RSS 直接相加**。
  仅看约 1 GiB / 端的低 RSS 会漏掉 GPU owned/unmapped、driver 分配、被压缩的 guest 页和其它应用负载。
- 本阶段 swap used 从 **13,747.5 MiB** 降至 **13,739.5 MiB**，最大增长 **0 MiB**；
  `Swapouts` 始终为 **6,864,757**，增量 **0**。Pageouts 增加不等于新增 swapout；本轮没有用磁盘换出撑过门槛。
- 八端最终采样帧 **60,480 / 56,100 / 49,860 / 43,980 / 34,980 / 26,520 / 18,600 / 11,100**，
  全部 SIGTERM 优雅退出 **0**，无 CRASH / FATAL / GPU 执行失败；原件和参考档 hash 不变。
  停止后核对 dmhost / 本次 air 均已退出，系统压力恢复 normal，`memory_pressure -Q` 约 70% free。
- 详细结构化汇总：同目录 **`resource-stop-summary.json`**。2 / 4 端结果、八端失败日志与截图均保留在 work/，不入库。

#### 资源瓶颈与验收边界

1. 大头是 **guest working set + GPU 贴图 / buffer / driver 工作集，以及冷启动 / 入图瞬时分配**。
   代码文件共享确实有效，但八端只去掉约 0.66 GiB 的重复 clean 项目文件映射，无法单靠它解决全机压力。
   一条典型八端大厅资源记录：贴图分配约 2.15 GiB、buffer 约 0.70 GiB、命令 allocator 约 167 MiB，
   618 个 shader、1,386 个渲染 PSO、2 个计算 PSO、C1 分配约 4.13 MiB；这些分配口径也不能直接与 guest 相加。
   本机 nometal shader 源文件累计读入约 20.76 MiB，稳定时 file mapping live=0；Metal 内部编译对象无法用公开 API 单独精确记账。
   没有把源码输入大小 / shader 数量当成 Metal 编译代码的实际物理占用，也没有声称它们已完全跨进程共享。
2. **在当前机器其它应用仍运行的会话条件下，八端大厅可维持，但开局加载没有通过无内存压力的准入门槛。**
   本次数据不能推出“任何干净的 64 GiB 环境都绝对无法八开”，也不能推出“只要每端稳定小于 6 GiB 就一定可跑完八端整局”。
   不为了通过实验关闭用户应用或放宽压力 / swap 停止条件；后续资源优化 / 更干净的实机环境应另行验收。
3. 还发现独立的控制 / OCR 卡点，未用补按或改判掩盖：八端分队 UI 中 **RL-0 仍为 Either**，
   RL-1..3 为 Alpha，RL-4..7 为 Bravo；首个队伍 Right 输入未形成预期显式分配。
   本机 Vision 把 RL-0 / RL-1 读作 **RL-O / RL-I**，触发昵称检查失败。
   即使后续解决资源问题，也需补足进入分队后的等待与 OCR 歧义处理，再重新验证原生 4v4 人数；
   当前没有把 Either 的潜在自动补齐当成已经证明的 4v4。

**停在这里，保留未提交的 M5 实现 / 测试 / 补丁与证据。下一步仍是 M5，不是 M6。**

## 2026-10-18：M5 继续，指挥方调整后的验收口径

- 已先将上一轮实现、测试和资源失败证据作为阶段提交 **81a2edf** 推送 origin/main；只提交 splatoon3-native，游戏数据仍全部忽略。
- 本次指示覆盖上一节历史停止线：允许 warning；仅 critical、相对本次启动基线新增 Swapouts 超过 2 GiB，或某宿主崩溃才按资源条件停止。
  swapout 按 vm_stat 的实际 page size 乘计数增量，不能以 swap used 净变化替代。功能错误和整局超时仍须据实失败，不能签收。
- 正在落实 GPU pipeline binary archive 的本地磁盘缓存、上传暂存的上传完成回收和上限，以及开局纹理上传两端一批的准入。
  MSL source-to-IR 仍走系统编译器缓存，尚无证据证明全部 MTLLibrary 对象跨进程共享。最终效果与峰值组成待本轮实测。

### 新缓存 / 暂存版本的单进程复测

- `work/tests/m5-1p-20261018-100443-813022/`：native 子进程到 6,000 帧，`phase_passed: true`、错误为空、优雅退出 0；原件 / 参考 hash 未变。
  全程采样 footprint 峰值 **4,715 MiB**，RSS 峰值 **2,046 MiB**，大厅稳定 footprint 最大 **3,279 MiB**、**44.77 fps**。
  对比上一轮单进程冷峰 **10,039 MiB**，本次组合修改后下降约 **53%**；这不是单独某一项改动的消融实验。
- 上一轮峰值 guest 常驻约 1.6 GiB、Metal allocated 约 9.3 GiB，上传旧块已降至 0–32 MiB，延迟队列只有 1–4 个；
  因此不能把那额外几 GiB 直接定性为上传旧块泄漏。新版本将每次 pipeline 构建封在 autorelease pool、headless 禁止一次预测派发最多 384 个后台编译任务，
  使用磁盘 GPU binary archive；同时上传暂存在自己 upload feedback 完成时释放，不再等下一次 replay fence。
- 新版资源样本：第 1,800 帧贴图 **1,245,591,424 bytes**、buffer **758,694,048 bytes**、命令 **173,473,856 bytes**、C1 **4,325,376 bytes**，
  Metal allocated **4,360,060,928 bytes**；上传在途峰值 **100,663,296 bytes（96 MiB）**，当时在途为 0。
  604 个 shader 的源文件输入累计约 20.47 MiB，1,383 个渲染 PSO / 2 个计算 PSO；剩余 Metal 记账包含驱动 / 编译 / 内部对象，公开 API 未细分到每类。
  不将此差额断言为纯 shader，也不把 guest + Metal / buffer 重叠口径相加。
- 原始冷建日志中 GPU 归档 `hit=0 / miss=1301 / write=1301 / error=0` 为下界，磁盘归档约 118 MiB。
  后续新进程已经出现 `hit=713 / miss=88 / write=88 / error=0`，命中路径使用 **FailOnBinaryArchiveMiss**，不能静默回退再伪装命中。
- 新增 GPU 归档组件检查：冷建写盘、严格命中、损坏归档回退并原子替换；普通渲染 **132** / headless **135** 检查通过。
  资源规则测试覆盖 warning + 恰好 2 GiB 继续、swap used 净减少但 swapout 增量超过 2 GiB 停止、critical 停止。
- wrapper 失败仍保留：该单进程测试执行中误修改了正在等待它的 shell 文件，子进程通过后 wrapper 出现 EOF 解析错误、退出 2。
  后续正式两端入口已重新启动并冻结脚本；不把该单进程 wrapper 标成退出 0。

### 两端整局复测与进一步冷峰定位

- `work/tests/m5-2p-20261018-100747-103147/`：两端自然入图到判定 **185.9277 / 185.9920 秒**，均到 ResultWinners、优雅退出 0；
  对战 **32.28 / 34.76 fps**、稳定 footprint 最大 **3,665 / 3,695 MiB**、RSS 最大 **2,251 / 2,267 MiB**。
  全程合计 footprint 峰值 **8,039 MiB**、RSS 峰值 **4,590 MiB**，压力始终 normal、新增 swapout **0**。
- 该次正式入口仍退出 **1**，唯一验收错误是 `native team UI missing RL-1`：Vision 将其读成 **RL-T**，
  所以仅 O/I 容错不够。原始结果不改写；原生队伍截图明确为 RL-0 Alpha、RL-1 Bravo，GetUid / GetNickname 读回与请求一致。
  后续身份门槛改用这两个接口实际输出缓冲中的 UID / 昵称，并验证 UID 唯一；OCR 只验模式与队伍人数。
- 四端后续测试（`work/tests/m5-4p-20261018-101846-484656/`）已暴露单次低冷峰并不稳定：
  房主独自启动第 63 秒 / 2,760 帧出现 footprint **11,230 MiB**、Metal allocated **10,671 MiB**、GPU ledger **9,397 MiB**，guest 常驻 **1,633 MiB**。
  同期后台预热为 0 行，GPU 归档约 1,274 hit / 27 miss；上传在途 0、峰值 96 MiB。
  资源样本中贴图约 2.3 GiB、buffer 0.68 GiB、命令 0.17 GiB，远低于 Metal 总分配；不能将差额说成贴图上传暂存或全部重编 PSO。
  随后 live shader / PSO 数量基本不变，Metal 总分配从约 10.4 GiB 回落到 3.6 GiB，支持还有驱动内部临时 / 保留分配，但公开 API 不足以逐类精确拆开。
- 针对宿主可控部分，另补 shader library / reflection 的逐次 autorelease pool；
  fence 后已退役、独立且无 parent / buffer / heap 的 GPU private 资源标记 Empty，允许丢弃内容。
  绝不 purge guest no-copy shared backing、仍有效的游戏贴图或纹理 view。只累计 discard 请求字节，不把它当作已释放物理字节。
  资源 inventory 也按 texture parent / buffer 去重，避免视图重复记账。
  新组件检查普通 **134** / headless **138** 通过；该版本实机冷峰与八端效果仍待后续测试，当前四端进程继续使用启动时的旧二进制。

### 四端 2v2 整局通过，验证加载错峰

- `work/tests/m5-4p-20261018-101846-484656/`：正式 wrapper 退出 **0**，`phase_passed: true / errors: []`，
  `passed: false`（不是八端 M5）。四端同房 **69a55ad854ec519235a026a132c87272**，武器 **8001 / 2040 / 10 / 3000**；
  Turf War / Scorch Gorge，自然入图到判定 **188.6674 / 188.6897 / 188.7249 / 188.7111 秒**，均到 ResultWinners、优雅退出 0。
  首个分队等待及实际身份读回均通过，原件 / 参考 hash 不变。
- 开局四个控制器仍立即确认，由原生 PIA 决定就绪；宿主只限制新建 ≥256 KiB 的 packaged 贴图上传。
  两个跨进程 flock 名额：首批 player 3 / 0 同时取得；player 1 / 2 等待 **8,793 / 10,066 ms**，
  前批新大贴图上传安静且 Metal 分配回落或稳定后才放行。没有改 PIA 消息、倒计时或 InGame / 结算状态。
  四端本次均正常进入同一局，证明该错峰不会只让菜单各自前进。
- 对战 FPS **24.44 / 25.78 / 23.59 / 23.85**；对应稳定 footprint 最大 **4,713 / 3,744 / 3,710 / 3,712 MiB**、
  RSS 最大 **2,262 / 2,266 / 2,267 / 2,270 MiB**。
  全阶段 footprint 合计峰值 **15,933 MiB**、RSS 峰值 **9,192 MiB**；全机 GPU 利用率阶段平均 **90.31%**。
  系统压力始终 normal，新增 swapout **0**，swap used 净增长 **0**。
- 大厅项目文件 clean 页映射合计 **546.875 MiB**，唯一页 **150.3125 MiB**、重复 **396.5625 MiB**；
  入图为 **551.171875 / 153.71875 / 397.453125 MiB**。本版已将实际 runtime pipeline archive backing 文件计入限定的项目文件页查询。
  依旧不把此数字称为所有 GPU / guest / 系统库的全局 PSS。
- 该四端二进制尚未包含后补的逐 shader pool / private Empty 退役；对应最终版本单端剖析正在单独进行，八端将使用最终版本。

### 最终资源版本：单端冷峰复测通过，八端正式开始

- `work/tests/m5-1p-20261018-103512-700324/`，武器 8001；正式 wrapper 退出 **0**，native 到 6,000 帧，`phase_passed: true / errors: []`，优雅退出 0。
  逐秒 memstat footprint 峰值 **3,835 MiB**（两秒协调器采样峰值为 3,810 MiB），大厅稳定最大 **3,692 MiB**、RSS 最大约 **2,070 MiB**、**49.78 fps**。
  压力始终 normal、新增 swapout **0**。本次采用与四端房主同一请求武器，包含 shader 逐次 pool、private 退役 Empty 和资源 inventory 去重。
- **物理占用和“已分配”分离得到实测支持**：该次 Metal `currentAllocatedSize` 峰值仍 **8,215 MiB**；
  第 27 秒 footprint 峰值样本为 3,835 MiB、Metal 分配 7,536 MiB、GPU ledger 2,037 MiB、guest 常驻 1,625 MiB。
  不能再把 Metal / AGX allocation 字节直接当成全部仍占用的不可回收物理页。
  fence 完成后丢弃已退役 private backing，保留活跃游戏状态；仍没有从公开 API 精确拆出驱动每类内部对象。
  shader 编译原来已在 submission pool 内，本次是进一步将单个冷 submission 内可能聚集的临时对象限定到一次 library / reflection 创建，不能误称旧实现完全没有 pool。
- 四端共享页还证明运行时归档确实有跨进程 clean backing 页：大厅 `.metalar` 映射合计 **162 MiB**、唯一 **54.09375 MiB**、重复 **107.90625 MiB**。
  代码部分为 **352.25 / 88.0625 / 264.1875 MiB**，其它项目文件为 **32.625 / 8.15625 / 24.46875 MiB**。
  这是实际 inode + offset 的 resident / clean 页查询，配合严格 GPU archive hit，未把每端私有 pipeline 对象本身称为同一个对象。
- 最终八端入口已启动：
  `bash tests/run_all.sh --milestone m5 --players 8 --mode 0 --stage-id 1 --weapons 8001,2040,10,3000,0,1000,6000,7010 --timeout 4000`。
  产物 **`work/tests/m5-8p-20261018-103801-878129/`**，总日志 **`work/m5/final-eight.log`**。
  普通渲染 **134** / headless **138**、NVN **79**、HID **73**、LDN frontend **10**、host options **32**、文件系统 **74**、虚拟 LDN **59**、资源停止规则检查全过。
  宿主二进制 / harness / resource sampler / 入口 / 补丁 SHA256 固定在 `work/m5/final-code.sha256`，运行中不修改它们。
  资源停止先同时 SIGTERM 全部本轮宿主，统一最多等 12 秒后回收剩余者；清理后另采系统 Swapouts，防止漏报停止期间的换出。
  **八端最终结论待后续实测，当前仍不签收 M5。**

## 2026-10-18：M5 签收 PASS，八端离线 4v4 自然结算

**M5 PASS。** 本节覆盖前文的进行中 / warning 停止结论；所有先前失败记录保留。M6 尚未开始。

### 正式结果与停止规则

- `work/m5/final-eight.log` wrapper 退出 **0**；`work/tests/m5-8p-20261018-103801-878129/result.json` 的 `passed: true / phase_passed: true / errors: []`。
- 八端同房 **`2e2bd31b711a5c9eb0f45926f52b29a8`**，原生 UI 明确 **RL-0..3 Alpha / RL-4..7 Bravo**，Turf War / Scorch Gorge（stage ID 1）。每端 UID 唯一、GetNickname 输出正确、native kit 均与八把指定武器一致。
- 八端均实际经过 InGame → ResultJudge → ResultWinners；入图到判定 **194.70–195.51 秒**，未改计时 / 判定 / 结算 / PIA 消息。实际 PIA 接收下界为 131,072 / 131,072 / 131,072 / 65,536 / 65,536 / 65,536 / 65,536 / 65,536 帧。
- 所有进程 `DM_HEADLESS=1 / DM_OPMODE=0`，有效 crop 1280×720；内部 pass / draw 持续增加，真实 host `screen_submits=0 / composite=0`。显式原始截图仅用于本地诊断，未上屏、未入库。
- 八端都优雅退出 **0**，最后逻辑帧 **55,200 / 50,160 / 45,420 / 39,000 / 32,940 / 27,180 / 22,080 / 17,280**。无 CRASH / FATAL / GPU 执行错误，原件及只读参考档前后 SHA256 不变；清理后未留本轮 dmhost / air。
- 资源采样最高 **pressure=2 / warning**，按新规则继续；**新增 Swapouts 从启动到清理后均为 0**（计数 6,864,757 不变，page size 16,384）。swap used 从 13,675.5 降到 13,523.5 MiB，没有用新增磁盘换出撑过比赛。清理后压力恢复 normal。

### 同时运行时的逐端数据

八端共同大厅窗口 **43.04 秒**，在设置输入前且全部至少 5,000 帧；共同对战窗口 **169.42 秒**，从所有端 InGame 后约 20 秒到首端判定之前。
单端参考是本节前最终资源版本的 **49.78 fps / 低资源大厅**。人数、场景与武器负载不同，比例仅供资源比较，不称为同场景并行加速比。下表 footprint / RSS / compressed 为该共同对战窗口的采样最大值。

| 玩家 | 武器 ID | 八端大厅 fps | 八端对战 fps | 单端大厅参考比例 | footprint MiB | RSS MiB | compressed MiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| RL-0 | 8001 | 18.27 | 13.45 | 27.02% | 4454 | 1320 | 1103 |
| RL-1 | 2040 | 18.67 | 13.98 | 28.08% | 3693 | 587 | 1778 |
| RL-2 | 10 | 18.61 | 13.82 | 27.76% | 3690 | 1253 | 1152 |
| RL-3 | 3000 | 18.55 | 13.78 | 27.68% | 3598 | 594 | 1778 |
| RL-4 | 0 | 18.44 | 13.50 | 27.13% | 3404 | 1210 | 1095 |
| RL-5 | 1000 | 18.36 | 13.44 | 27.01% | 3440 | 1202 | 1174 |
| RL-6 | 6000 | 18.30 | 13.43 | 26.98% | 3383 | 1243 | 1164 |
| RL-7 | 7010 | 18.59 | 13.73 | 27.59% | 3436 | 1255 | 1169 |

- **所有八端全程逐秒 footprint 峰值均 <6 GiB**：4,509 / 3,723 / 3,723 / 3,636 / 3,480 / 3,468 / 3,463 / 3,468 MiB；不是只把压缩后的低 RSS 当作达标。
- 两秒协调器全阶段 footprint 合计峰值 **29,060 MiB（28.38 GiB）**，RSS 合计峰值 **11,065 MiB（10.81 GiB）**；两者可能出现在不同时间。共同对战窗口 footprint / RSS 合计峰值为 **28,967 / 8,664 MiB**。
- 单端 RSS 低至约 0.6 GiB 是有压缩页及 GPU owned/unmapped 的结果。系统 compressor 从 **9,833.78 MiB** 升到最高 **20,773.89 MiB**。`footprint --swapped` 的列还包含 compressed，不能将它当成新增磁盘换出；本次以 vm_stat 的累计 Swapouts 实证为 0。
- GPU 全机利用率：共同对战窗口已采样点平均 **98.62%**，全阶段已采样点平均 **94.34%**。当前主要性能约束是 GPU 工作量。每两秒系统采样在 VM / footprint 快照时有暂停，最大相邻间隔约 **15.19 秒**；逐端 memstat 仍由各自线程逐秒记录。

### 共享页、驱动分配和冷峰解释

- 入图快照：项目 clean file 页映射合计 **1,116.8125 MiB**，按 backing inode + offset 去重后 **158.328125 MiB**，重复 **958.484375 MiB**；大厅分别为 **1,105.703125 / 161.25 / 944.453125 MiB**。
- 入图共享页组成：代码 **704.5 / 88.0625 / 616.4375 MiB**；GPU runtime `.metalar` 归档 **392.0625 / 67.734375 / 324.328125 MiB**；其它项目文件 **20.25 / 2.53125 / 17.71875 MiB**（依次为映射 / 唯一 / 重复）。该查询只含实际 resident、clean、external 且非 DIRTY / COPIED 的项目页；不是所有 guest / GPU / 系统库的 PSS。不能把不同时间的共享快照从全阶段 RSS 峰值直接相减。
- 归档严格 hit 使用 FailOnBinaryArchiveMiss；八端最后已打印的 hit / miss / write / error 下界分别为：`1796/5/5/0, 1795/6/6/0, 1793/8/8/0, 1787/14/14/0, 1794/7/7/0, 1874/27/27/0, 1794/7/7/0, 1793/8/8/0`。按键 flock 避免多个进程同时编译同一个 GPU pipeline，写临时文件后原子替换，实际 readonly backing 页可跨端共享。
- MSL source-to-IR 仍经 Metal 系统缓存；没有声称 8 个 MTLLibrary / pipeline 宿主对象是同一对象，也没有声称再无 newLibraryWithSource 调用。归档复用 GPU 编译结果，逐 library / reflection / pipeline pool 限制临时对象积聚。
- **AGX allocation 并未被伪装降低**：全机 `Alloc system memory` 峰值 **43,193,090,048 bytes（40.23 GiB）**，`In use system memory` 峰值 **23,939,760,128 bytes（22.30 GiB）**，不一定同一时刻。它们与任务 footprint / RSS 有重叠，不能相加。
- 可控的峰值处置是：冷启动依次准入；开局两端一批、前批分配安静稳定后放行；64 MiB 上传批次上限与三组 fenced upload allocator；上传暂存在自己的 GPU completion 回收；已退役独立 private backing 标记 Empty。对仍有效的游戏贴图、guest no-copy shared buffer、texture view / heap 不这样处理。Metal 内部各类保留 / 编译对象的精确字节仍不可由公开 API 独立拆开，不能给差额编造唯一来源。
- 原先约 9.8–11 GiB 的单端冷峰不是全部由活跃贴图 / 命令 / 上传暂存构成。最终同武器单端 footprint 峰值约 **3.75 GiB**，但 Metal 分配仍曾达到约 **8 GiB**，说明允许丢弃已退役 backing 后，分配口径和不可回收物理记账能够分离。未将累计 discard 请求字节当作释放物理字节。

### 验收边界与交付

- 通过的是本次指定武器、Turf War / Scorch Gorge 的全自动 4v4 自然结算与资源门槛；沿用 M4 已验证的五模式 / 25 地图可选接口，没有声称全部组合逐一完成八端整局。控制脚本负责建房 / 设置 / 分队 / 准备，比赛期间没有策略训练动作；M6 的随机策略与同步 RL 接口尚未开始。
- 原始截图、NSO / RomFS / shader 数据、存档、日志和采样全部保留 work/ 且不入库。最终测试结束后冻结 SHA256 校验仍全通过；源码补丁将按规则再次检查正向 / 反向应用，仅提交 splatoon3-native。

### M5 交付后的定向错误路径收口

- 八端完整验收版本为已推送的 **2006a98**；阶段提交 **81a2edf** 同样已推送。八端结束时的二进制 / 入口 / 资源采样器 / 补丁冻结校验全通过。
- 收尾审查发现新增 scoped pool 的错误返回需要额外持有：C 函数中的 `NSError **` 在 ARC 下推导为 `__autoreleasing`，
  直接把错误写入外层调用者的 writeback temporary 后就销毁内层 pool，可能在调用者保留错误前释放它。
  library loader 与 pipeline builder 现在在内层 pool 之外用 strong 局部变量保留错误，再交给调用者。
- 定向用例覆盖缺失 library 文件的真实 POSIX 错误，以及模拟设备返回的 pipeline 创建错误；都验证错误对象越过 pool 后的 domain / code / description。
  最新普通渲染 **136** / headless **140**、NVN **79** 检查通过，宿主重新编译成功。
  本后续修复的验证层为错误路径 / GPU 组件及编译；未重新跑八端整局。完整八端签收证据仍明确归属于 **2006a98**。
- 八端 player 0 最后一个 InGame GPU inventory 样本：unique texture backing **2,201,457,536 bytes（约 2.05 GiB）**，
  buffer **908,951,712 bytes（约 866.84 MiB）**、命令 allocator **174,784,576 bytes（约 166.69 MiB）**，
  733 个 shader、1,772 个渲染 PSO / 6 个计算 PSO、C1 **4,325,376 bytes（4.125 MiB）**；
  shader 源文件累计读入 **25,667,401 bytes（约 24.48 MiB）**，不是编译库实际物理字节。
  当时 Metal allocated **3,949,215,744 bytes（约 3.68 GiB）**、upload live 为 0、upload peak 96 MiB。
  buffer 包含 guest no-copy，以上口径不相加。此样本再次说明命令内存 / 暂存不是主要常驻大头，GPU 贴图与 guest 工作集仍是主体。

## 2026-10-18：M6 卡点（停止，未签收）

### 范围和当前结论

- 本轮按指示先读 GOAL.md、M5 最终签收及 tests/README.md；工作基线为 `b0b590c`。
  尚未修改宿主生产代码、补丁、M5 harness 或回归入口；没有创建可供训练使用的 `rl/` 包或 `tests/test_m6.py`。
- **卡点是内部观测的语义映射和对象归属没有闭环**。目前只有候选类 / 函数 / 字段，不能据此输出自身和可见队友 / 敌人的可信观测。
  本轮没有证明移动后位置变化、射击后墨量下降、固定帧跳同步或 reset 重开。
- 按用户本轮“卡住时把现象和假设写进 PROGRESS.md 卡点一节然后停下”的要求，到此停止；未请求其它模型，未启动八端，未 commit / push。
  这不是 M6 PASS，也不是对 M5 已签收结果的否定。

### 已确认的现象和定位证据

- 本地 `work/data/v720896/ExeFS/main` 的 build ID 确认为 `28c4287aee36f7499da60f3e68b54c70`。
  按 NSO 段解压并读取动态符号表，得到 82 个已定义导出符号，其中没有包含 Player / Paint / Versus / GameTime 的条目。
  `../splatoon3-decomp/symbols/` 提供类名和参数表名，不提供可直接使用的玩家状态字段布局；其当前文档也明确游戏自身代码无 C++ 函数符号。
- 对实际 main 的 ADRP + ADD 类名引用进行了静态定位，结果仅保存在 `work/m6/`：

  | 类 | 类名字符串返回入口 | 静态可确认内容 |
  |---|---|---|
  | `spl::PlayerDamage` | `main+0x2920748` | 分配大小 0xf08；vtable `main+0x5d32218`；`main+0x2920834` 的初始化将 +0x34、+0x88 写为 1000 |
  | `spl::PlayerRemote` | `main+0x2aaba50` | 分配大小 0x58；vtable `main+0x5d3da38`；初始化完成点可探测，但尚未绑定玩家 |
  | `spl::PlayerPipeline` | `main+0x2aa7c60` | 分配大小 0x1d0；尚未确认可作为完整游戏逻辑帧采样点 |
  | `spl::PlayerKinematics` | `main+0x2a76a8c` | 分配大小 0x40；并不直接给出可安全导出的坐标布局 |
  | `game::ActiveTimeCounter` | `main+0x14af2c4` | +0x30 有清零 / 加一函数，不能据此认定为比赛剩余时间 |

- 进一步追到 `main+0x2748390`：代码从传入对象 +0x208 的数组取组件，做类型检查，成功后将指针写入 PlayerDamage +0xf00。
  `PlayerRemote` 初始化后续函数也读取 owner +0x208。它们提供继续追对象图的线索，但尚未确认实际局内 local / remote 索引、队伍、生命周期及可见性语义。
  `PlayerNetState` 的构造 / 类型注册也已定位，尚未恢复各序列化字段的含义，不能把其裸字段当作训练状态。
- 现有 `hle_hid.c` 的 `DM_HID_FIFO` 已有双摇杆、16 位按钮和六轴角速度通道；按钮 RS 对应右摇杆按下，B / ZR / ZL / R 的位定义已存在。
  但 FIFO 线程用 `usleep(hold_seconds)` 执行动作，既没有逐 step 确认，也没有 8 端共同帧屏障。
  `dm_guest_frame()` 在 NVN present 边界增加；它本身没有证明游戏逻辑帧 / 网络同步帧与这个计数一一对应。
  M5 使用墙钟，不能把按墙钟发 FIFO 后等待帧日志的方式称为固定帧跳的同步 RL step。

### 双端诊断（主动中止，不是里程碑回归）

- 复用 M5 的启动、独立参考档副本和本次 Unix socket air，在 `work/m6/probe_m5.py` 中复制 harness，
  只调整产物前缀并追加只读诊断探针：
  `main:2920850@x0+88,main:2aaba44@x0+28,main:2aa7c58@x0+28`。
  原始 `tests/test_m5.py` 没有修改；诊断使用现有宿主，没有改游戏计时、队伍或状态。
- 命令：`.venv/bin/python work/m6/probe_m5.py --players 2 --mode 0 --stage-id 1 --weapons 0,0 --timeout 1200`。
  总日志为 `work/m6/two-player-probe.log`；产物为 `work/tests/m6-probe-2p-20261018-112736-404123/`。
  静态记录为 `work/m6/defined-symbols.json`、`class-xrefs.json`、`class-xrefs.txt`、`state-name-xrefs.txt` 和各反汇编文本；解压镜像只在 `work/m6/main.img`。
- 两端各命中三个新增探针各两次，且每个入口各出现两个不同 x0 对象地址；发生在进入对战之前。
  两端 `PlayerDamage+0x88` 初始化读回均为 `e8030000`（小端 1000），`PlayerRemote+0x28` 在构造完成点均为 0。
  **这只证明候选组件初始化，不证明该字段就是应导出的局内 HP，也不证明哪个对象是自身。**
  构造时抓一次指针然后永久复用，已有对象重建 / 尚未绑定的反证，不能作为接口实现。
- 记录卡点后，向本轮唯一 harness PID 57846 发 SIGINT，让其 finish 同时终止所属两端并回收 air；
  两端优雅退出 0，最后资源帧为 8040 / 3480，无运行时失败标记。主动停止时尚未观察到完整双端同房和 InGame，未跑完整对局。
  诊断复制的 harness 仍将原始 result.json 标为 `milestone: M5`，并据实记录 `interrupted`、缺少完整对局及完整同房，wrapper 退出 1；未改写该结果，不将它当作新的 M5 / M6 验收。
- 清理后核对 harness / air / 两个 dmhost 的 PID 均已不存在；本轮累计新增 swapout 为 0，清理后 pressure=normal。
  原存档及只读参考档 SHA256 均仍为 `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。
  宿主 SHA256 为 `9ef87325ff36670d217e88995798f5c1f5cada24ba49009515c616ee42db445a`；诊断脚本 SHA256 为 `867b7cace642d72b87317578da42d1d6d7e37c26c33d66ec4fac18e83f942f61`。

### 待验证假设与恢复工作的切入点

1. `PlayerDamage+0x88` 可能是当前 HP、+0x34 可能是上限，但必须用局内受伤 / 恢复 / 死亡对照确认，不能仅按初值 1000 命名。
2. 可以从组件绑定的 owner 图恢复玩家对象和身份；需要在绑定后读取，并确认场景切换 / 死亡重生时指针有效性以及每进程自身与网络玩家的索引关系。
3. `PlayerNetState` / 玩家主对象可能提供位置、方向、墨量和特殊量；相关字段、单位及更新阶段尚未确认。
   比分 / 涂地、剩余时间、击杀累计和对端可见性也均缺少可信来源，不能用宿主时间或假定所有远端可见来补齐。
4. 状态来源确定后，再选实际逻辑更新边界实现 POSIX Unix socket 或共享内存通道与共同 step 屏障；
   需要证明暂停采样期间不会继续推进另一条逻辑 / PIA 更新线程。单独阻塞 present 尚无正确性证据。

**停止状态：仅更新此进度文档；诊断材料和所有游戏相关数据留在忽略目录 work/，未加入版本控制。**

## 2026-10-18：M6 分层恢复，A 双端验收进行中

- 用户后续指示覆盖上一节的停止安排：A 先完成按帧动作、像素观测、ParallelEnv、整局及 reset，通过后先提交；B 再逐字段恢复；C 最后八端随机策略验收。
- 新增 `hle_rl.c` / `dm_rl.h`：POSIX Unix stream socket，帧首输入屏障、严格 sequence / 帧增量确认；等待 Python 时冻结 guest clock。
  运行时要求受控输入边界在同一游戏线程，且相邻边界恰好跨一个 present；不满足立即失败。
  这是输入 / 渲染迭代的固定帧跳，尚未声称 60 Hz 物理 tick 或 PIA 包调度确定性。
- NVN 在提交线程读回游戏有效 crop，经 GPU completion 后区域平均下采样为 128×72 RGB；不调用最终合成、不创建窗口、不将 RL 图像写盘。
  比赛阶段来自 11.3.0 原生 InGame / ResultJudge / ResultWinners 的只读 OBS gate。
  gate 放在 prologue 的第二条指令，保留 M4 / M5 原先第一条指令的 DM_PROBE 入口；构建号、原指令和安全插入位置都做校验。
- `rl/` 为真正的 PettingZoo ParallelEnv，向所有端发送动作后再逐端收 ACK；观测先只有像素、帧号、原生阶段，未伪造剩余时间和内部字段。
  `reset` 关闭上一房间并用独立参考档副本重启 / 重建房间，可选模式 / 地图 / 每人武器；本层不承诺复用原 PID 操作原生再战菜单。
  `tools/private_battle.py` 提取 M5 已验证的宿主配置、模式地图 / 分队 / 准备控制器路线，M5 与 M6 共用；本地 BYML reader 同样提取到 tools 并保留 tests 的兼容导入。
- 单端真实游戏接口冒烟：`work/m6/socket-smoke/result.json` 为 `passed: true / returncode: 0`。
  附着帧 601，各步前故意延迟 0.2 秒，`step(1/7/31/2)` 返回 602 / 609 / 640 / 642；有效像素来源均为 1280×720。
  只覆盖大厅输入 / 渲染接口，不作为对局或 M6-A 验收。
- 传输组件测试 4 项通过，包含延迟策略仍精确推进、非法动作、乱序 sequence 和漏输入帧拒绝。
  初次测试发现 BSD accept 继承 O_NONBLOCK，导致接收下一动作时遇到 EAGAIN 提前释放；已显式将已连接 socket 设为阻塞并复测通过。
  新 GPU 用例覆盖 RGBA / BGRA、crop、下采样、上下原点及 screen / composite 计数不增加；普通渲染 **148** / headless **152** 检查通过。
- 正式入口：`bash tests/run_all.sh --milestone m6 --players 2 --timeout 2400`，总日志 `work/m6/two-player-acceptance.log`。
  前置 NVN **79**、HID **73**、LDN frontend **10**、host options **32**、文件系统、虚拟 LDN **59**、资源停止规则及上述新组件检查均通过。
  首局产物 `work/tests/m6-2p-20261018-114459-299748/`；源码 / 二进制哈希固定于 `work/m6/acceptance-code.sha256`，运行中不修改这些文件。
  **随机整局、像素动作相关性和 reset 结论待本轮实测；尚不签收、尚未提交推送。**

### M6-A 签收 PASS（双端，像素 / 控制层）

- 正式入口 `bash tests/run_all.sh --milestone m6 --players 2 --timeout 2400` 退出 **0**。
  `work/tests/m6-check-2p-20261018-114459-277403/result.json` 为 `passed: true / errors: [] / pixel_control_layer_passed: true`。
- 首局为 `work/tests/m6-2p-20261018-114459-299748/`，Turf War / Scorch Gorge、武器 0 / 0。
  同房会话 `eab0f1ead919cbf983ad5267f436d929`；双方均实际进入 InGame → ResultJudge → ResultWinners。
  InGame 到 Judge 的墙钟时间为 **211.5792 / 211.5423 秒**，包括策略屏障等待，未改倒计时或结算。
  首局 **448 次**同步 step；初始帧 **14562 / 9972**，终止帧 **21276 / 16686**，两端均实际推进 **6714 帧**，终止阶段均为 3。
  政策延迟以及 1 / 7 / 31 帧跳用例均通过严格 ACK；没有按墙钟时间推算已完成帧数。
- 移动 / 视角像素 MAD 样本为 **50.68 / 53.66 / 58.17 / 79.62 / 54.71 / 49.51**；
  静止样本约 **0.93–1.25**，门槛 **3**，相关性通过。原始六个静止 / 移动数值在 result.json 中；图像仅在本次 work 产物中。
  每端像素尺寸 / uint8 范围 / 画面方差 / 阶段范围及来源 1280×720 crop 均通过。
- 第二次 reset 完整回收首局后，创建 `work/tests/m6-2p-20261018-115504-398945/`，会话为 `3ea2fd867a0d9652531d5da01fdc160d`。
  使用另一批 PID **44624 / 60497**，独立存档新副本，通过同一设置 / 分队路线，再实际进入 InGame 并继续 **10 次**同步 step，仍为 InGame。
  合计 **458 次**同步 step；仅要求第二局可运行，未声称第二局也结算或复用了原 PID 的再战 UI。
- 四个宿主均优雅退出 **0**，本轮无剩余 dmhost / air；运行前后参考档与原档 hash 通过。
  首局资源监测最大 pressure=normal、新增 Swapouts **0**，footprint 合计采样峰值 **7,336 MiB**。
  源码 / 宿主冻结清单 `work/m6/acceptance-code.sha256` 结束后复核仍全部一致。
- 共用设置路线与原 M5 源码的控制器调用序列比较：2 / 8 人 × 5 模式 × 25 地图共 **250** 项严格一致，记录 `work/m6/shared-route-equivalence.json`。
  该比较只证明代码提取后的序列一致；不把它当作 250 种配置的真实游戏验收。
- 提交前补充 `tools/prepare_rl.py` 的入口检查和复现说明；当前派生产物检查无需重写即通过。
  依指示先提交 / 推送 **M6 部分完成**。本层 reward=0，内部状态未实现，完整 M6 和八端随机策略仍未签收。

### M6-A 已交付，M6-B 实时字段诊断进行中

- **`64e7466` 已提交并推送**；独立 `git ls-remote origin refs/heads/main` 确认远端为 `64e74666bb466554939dc8072623d79625c69867`。
  提交仅含 splatoon3-native 的 18 个源码 / 文档文件，无 work / upstream 目录或游戏素材。
  补丁已重新生成，在原始 upstream 文件副本上正向检查、在当前 upstream 上反向检查均通过。
- A 结束后的系统 Swapouts 仍为 **6,864,757**、page size 16,384、pressure=normal，见 `work/m6/a-system-after-cleanup.json`。
- B 按后续指示改查实时更新 / HUD / 本地状态序列化，而非构造时固定对象归属。
  只读诊断脚本位于 `work/m6/fields/`，复用已交付环境，在独立运行副本中依次安排静止、本端移动、本端射击、恢复、仅对端射击及仅对端移动。
  当前产物 `work/tests/m6-2p-20261018-120526-166038/`；总日志 `work/m6/fields/live-probe.log`。
  候选包括 PlayerNetState 编码入口、墨量相关显示更新、PlayerDamage 实时更新及若干 HUD 计数入口；尚未新增训练字段或签收其语义。

### M6-B 实时采样路径与逐字段证据

- 放弃构造时判断归属，改钩 `PlayerNetState` 实时编码函数 `main+0x27fca10` 的安全第二条 prologue 指令 `+0x27fca14`。
  仅在 InGame 的调用中复制 x0 指向对象 +0x20 的三个坐标；不保存对象指针。编码器静态路径把三个量作为有符号绝对坐标压缩，范围 ±256。
  先前双端诊断只出现每进程一个编码源：仅 0 号移动时其坐标从约 (-23.90,10.50,71.43) 到 (-23.90,7.50,54.19)，1 号不变；仅 1 号移动时反过来。
- 位置接口新增独立有效位及原生采样帧；非 InGame、非有限量、越界或超过 120 输入帧未更新时，输出零值并清有效位。
  **这是本地玩家原生网络快照的最近采样，不声称每个输入帧都有新的物理状态。** 当前不输出远端玩家，避免将已知对象误称为可见玩家。
- `bash tests/run_all.sh --milestone m6 --players 2 --state-dump --timeout 2400` 正在验证位置接口。
  总日志 `work/m6/fields/two-player-acceptance.log`，验收目录 `work/tests/m6-check-2p-20261018-121822-156621/`，
  首局 `work/tests/m6-2p-20261018-121822-176702/`。运行版本固定在 `work/m6/fields/acceptance-code.sha256`，结束前不修改。
  无游戏传输组件已由 4 增至 **5** 项，覆盖实时坐标复制及 NaN 有效位屏蔽，全部通过。
- 开发选项 `--state-dump` 只把调用时的 0x1f0 字节原生包写入本轮忽略目录中的日志，用于字段对照；默认关闭，不作为未命名训练字段返回，也不提交这些字节。
  正式测试保留静止 / 0 号射击 / 0 号下潜恢复 / 仅 1 号射击 / 仅 0 号转视角的日志范围和帧号。
  `work/m6/fields/packet-survey.json` 已给出 +0x84 浮点值的强相关证据：
  0 号射击 **0.993286 → 0.758284**、下潜等待 **0.758284 → 1.0**；仅 1 号射击时 0 号保持 1.0，1 号 **0.993286 → 0.758284**。
  该量静态编码为 [0,1] 的 11 位归一化数，拟作为下一字段墨量加入并单独验证。
- 原 HUD 候选 `main+0x287d79c` 的 x21+0x53c 在所有动作窗口都为约 0.65，已反证，**不导出为墨量**。
  包 +0x70 虽初值 1000 且编码 10 位整数，本轮尚无受伤 / 死亡变化证据；不据此签收 HP。
  包 +0x44 的单位向量响应自身移动 / 射击，+0x5c 的单位向量响应自身右摇杆转视角，静止对端均不变；方向语义仍需接口层动作对照。
  `SplUITimerCtrl` 的实时虚函数 `main+0x3ef6930` 已定位，显示路径读取对象 +0x140 浮点量、+0x14c 比例；尚未现场确认哪一实例属于比赛倒计时，不伪造剩余时间。

### M6 当前卡点：结算阶段输入 / present 非一一对应（停止，B / C 未签收）

**本轮到此停止，未启动八端、未提交 / 推送 B。** A 的已推送提交和那次 PASS 证据保留；本次更长动作对照暴露了同一帧屏障在阶段切换中的覆盖缺口，不能把 A 单次通过扩大为所有结算路径已可靠。

- 上述双端 B 入口已结束，wrapper **退出 1**；验收 `work/tests/m6-check-2p-20261018-121822-156621/result.json` 为 `passed: false / full_m6_passed: false`。
  完成 **560** 次同步 ACK，尚未开始第二次 reset。0 号已经实际经过 InGame → Judge → Winners，1 号只观察到 InGame。
  最后成功 ACK 为 **23002 / 18379**，phase **3 / 1**；下一步 0 号拒绝继续，错误为：
  `FATAL RL input/present boundary mismatch previous=23014 frame=23016`。
  Python 随后收到 `native RL connection closed or invalid observation header`，清理另报告 `player-0: unclean exit -6`。
  不放松 / 删除此保护来伪造精确 k 帧承诺，不把已结算端跳过等待当作八端同步完成。
- 证据链：首局 session `3554159c41267fe842aa9847c152f03e`；0 号原生阶段探针时间为 **350.5091 / 571.3474 / 582.6419 秒**（从其进程启动算），1 号仅有 **252.7272 秒**的 InGame 探针。
  完整 fatal 在首局 `player-0/host.log` 末尾；最后 ACK 在验收目录 `steps.jsonl`，完整 Python 栈在 `exception.txt`。
  1 号末尾 air 状态先退房；是否为通信中断界面、两端 guest clock / 原生计时差异或其它阶段切换导致，**尚未确证**。
- 失败前的局部检查：像素静止 MAD 约 **0.98–1.17**，移动 / 转视角 **48.01–79.91**，门槛 3，通过。
  0 号最大位移 **7.171254**、静止 1 号漂移 **0**，位置归属对照通过；源码 / 宿主冻结清单结束后全部一致。
  包 +0x84 的墨量对照和两个方向向量证据见上节，但尚未导出这些字段或宣称其整局 / reset 回归通过。
- 已试假设：构造时抓对象不能判归属，已改成实时本地编码调用且动作对照成功；原 HUD 0.65 候选已用射击对照排除。
  当前停止原因是更基础的帧屏障边界反例，**不是让未齐的内部字段阻塞已完成 A 的交付**。
- 待恢复的假设 / 切入点：
  1. 某些结算、退房或 UI 过渡允许没有 HID 读取的 present；需把帧首动作锁存 / 计数绑定到实际游戏更新边界，或在每次 present 前设置可验证屏障，而不能继续依赖“每次 present 必有 HID read”。
  2. 两端不同步进入结算，可能有原生计时 / guest clock 局部冻结、PIA 推进或掉线阶段的差异。需先现场验证真实 timer HUD 和退房事件与输入 / present 序列，再确定终止语义；不能用累计 step 数代替原生比赛时间。
  3. 恢复后应先重跑本次包含射击 / 恢复 / 视角窗口的双端完整局与 reset，再加已验证的墨量 / 朝向字段，最后才上八端。HP / 存活、特殊、比分 / 涂地、剩余时间、可见同伴和击杀仍无完整接口证据。
- 清理已完成：0 号保护性 abort **-6**，1 号 SIGTERM 优雅退出 **0**；本轮两个 PID **41395 / 55194** 与 air 均不存在，没有遗留本轮游戏进程。
  清理后 pressure=normal，Swapouts 仍 **6,864,757**，相对启动新增换出 **0**；原件及参考档 SHA256 均保持 `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。
  资源采样 footprint 合计峰值 **8,198 MiB**，不是资源停止；清理核对记录在 `work/m6/fields/after-cleanup.json`。
- B 的位置 OBS gate、有效位、Python 观测与测试草稿保留在工作区；upstream 修改已重新捕获进 `patches/0001-splatoon3.diff`，游戏数据和诊断原始字节仍仅在忽略的 work/。
  本次失败不满足 B / C 提交条件，因此没有额外 commit / push；未调用其它模型。

## 2026-10-18：M6 按指挥方决定恢复，present 屏障与逐 agent 结算

- 本轮指示覆盖上一节停止线：present 才是 step 帧计数；允许无 HID 帧并在 info 中记录 `frames_without_input`；HID 仅拒绝错误帧号 / 同帧重复读取。
- 屏障移到原生 `nvnQueuePresentTexture` 的尾部，已计完 present、更新时钟和帧号并离开图形锁之后。
  每次 present 都递减剩余帧数；下一动作在该边界锁存，不依赖后续有无 HID。内部纹理仍在该帧 present 时同步读回并以同一完成帧号返回。
- 原生 ResultJudge 即清空控制器，后续 STEP 始终中立；Python 对每个进入 Judge 的 agent 单独返回 terminated 并从 `agents` 移除，仍向所有宿主发送帧推进请求。
  在其余端运行时，已结算端继续推进结果动画；所有 agent 均结算或超时前禁止 reset，显式 close 仍可取消会话。
  `process_infos` 保留所有端的最近 ACK，`advance_settlement()` 可在全部 agent 终止后中立推进到 ResultWinners，以保留完整原生结果序列验收。
- 位置与已完成射击 / 恢复 / 仅对端动作对照的包 +0x84 墨量加入正式观测，各有独立有效位；非 InGame / 非有限 / 越界 / 陈旧采样输出零值和无效位。
- 无游戏组件 **9 项通过**：策略延迟下精确 k 帧、非法动作与乱序拒绝、非有限状态屏蔽、连续无 HID 帧计数、提前 / 重复 HID 拒绝、Judge 后动作被忽略，以及逐 agent 终止后所有宿主仍同步推进。
- 正式双端入口已启动：`bash tests/run_all.sh --milestone m6 --players 2 --state-dump --timeout 2400`。
  总日志 `work/m6/present-barrier/two-player-acceptance.log`，首局 `work/tests/m6-2p-20261018-123456-881315/`。
  源码 / 宿主冻结清单 `work/m6/present-barrier/acceptance-code.sha256`；本轮运行结束前不改动这些文件。
  另加开发态 `SplUITimerCtrl` 实时更新探针，只记录候选原生计数，尚不导出未验证的剩余时间。
  **真实双端整局、位置 / 墨量动作对照、结算阶段无输入帧与 reset 的结论待测试结束，尚未签收或提交。**

### M6 当前卡点：结算后同一 present 帧重复读取 HID（按指示停止）

**本轮双端回归退出 1，未签收 / 未提交 / 未推送，未启动八端。** 已完成本轮授权的 present 计数实现、逐 agent 结算和位置 / 墨量接入；新的实际反例命中了指挥方本轮明确保留的“同帧重复输入读取报错”，因此不自行放宽规则，记录后停止。

- 正式结果：`work/tests/m6-check-2p-20261018-123456-859883/result.json` 为 `passed: false / full_m6_passed: false`。
  首局会话为 `88b8ab295f6fcd10c2c5f4f8a320340f`；完成 **533 次**同步 ACK，下一步发生断连；第二次 reset 尚未开始。
  最后完整 ACK 的两端帧号为 **22588 / 17975**，阶段 **3 / 1**，每端 `advanced=15`。
  0 号宿主最后错误：`FATAL RL input frame mismatch expected=22591 actual=22591 previous=22591`。
  本次不再因缺少 HID 的 present 跳变失败；实际错误是 **同一当前帧号第二次进入了 HID 读取检查**。
  Python 后续报 socket header closed，0 号退出 **-6**，1 号收到清理 SIGTERM 后优雅退出 **0**。
- 已通过的局部动作验证（实际生产观测）：静止像素 MAD **0.845–0.927**，移动 / 视角 MAD **48.16–80.54**（门槛 3）；
  自身位移 **7.220886**、中立对端漂移 **0**。0 号射击墨量 **1.0 → 0.758284**，下潜等待 **0.758284 → 1.0**；
  对端墨量均保持 1.0。仅 1 号射击时其墨量 **1.0 → 0.758284**，0 号保持 1.0。三个墨量窗口和位置 / 像素对照均 passed。
  这些是字段局部证据，不扩大为整局及 reset PASS。
- 逐 agent 结算实际发生：0 号第 **461** 步进入 ResultJudge 并从动作集合移除，第 **491** 步进入 ResultWinners；之后仍持续推进到第 **533** 步。
  已结算端 ACK 的 `action_ignored=1`，真实 HID 日志为 axes 全零 / buttons=0；没有继续把随机策略按钮交给它。
  1 号尚未观察到 Judge / Winners gate，`phase=1` 仅代表最近命中的阶段，**不能据此确认其末尾画面仍在战斗**。
  本轮成功 ACK 的 `frames_without_input` 合计两端均为 0；无 HID 帧的完整计数目前只有原生组件实验的证据，不能写成已在本次真实过渡中命中过。
- 额外倒计时诊断已区分准备阶段 5400 / 60 和局内独立实例 10800 / 60：两端的局内原生浮点计数都从 **10800 降到 0**，缓存显示秒数从 **180 降到 0**。
  汇总为 `work/m6/present-barrier/timer-survey.json`；0 号局内值结束于其启动后 554.3064 秒，1 号结束于其启动后 472.4552 秒。
  此字段尚未加入正式观测，准备阶段实例也不能拿来充当比赛时间。朝向 / HP / 存活 / 特殊 / 比分涂地等仍待逐字段验证。
- 已试假设与当前结论：将剩余帧计数从 HID 移到每次 present 后，精确 ACK 已持续通过 533 步；将已结算端设为中立，也已有实际日志证据。
  但“同一 present 间隔内最多调用一次已连接 Npad 的读取函数”又出现反例。现有错误没有记录重复调用的 guest LR / 线程 / API，因此不能直接断言这是错误采样、SDK 正常多次查询还是阶段切换中的两条路径。
  0 号已中立仍有该反例，说明不能仅归因于随机 B / R 在结果界面误操作。
- 待恢复切入点：先记录重复 HID 查询两次调用的 guest LR、线程和 API，区分“读取同一个已锁存手柄状态”与“同一帧重新取 / 应用一条动作”。
  若原生正常 UI 会重复查询，应缓存该帧已锁存输入；不能未经指示把重复查询错误悄悄改成去重。
  同时核对已归零但未进入 Judge 的 1 号实际原生阶段 / 结果等待或通信界面，避免只凭旧 `phase=1` 推断仍在对局。
  恢复后先重跑本轮双端整局 + reset，通过才提交，再继续其它字段和八端验收。
- 清理 / 保留：本轮两个宿主 PID **29542 / 51604** 和 air 均已不存在；源码 / 宿主冻结清单结束后全部一致。
  清理后 pressure=normal、Swapouts **6,864,757**（新增 **0**），本轮 footprint 合计采样峰值 **8,111 MiB**；原件 / 参考档 hash 均仍为既定值。
  见 `work/m6/present-barrier/after-cleanup.json`、首局 `resources-summary.json`。游戏数据、原生内存字节、截图和诊断输出只留在忽略的 work/。
  实现及测试草稿保留工作区，原生改动已重新生成补丁且正向 / 反向 apply 检查通过；未请求其它模型。

## 2026-10-18：M6 恢复，按 present 帧锁存输入

- 指挥方本轮明确覆盖上一节重复 HID 停止线：同帧多次 SDK 查询正常，复用同一动作；仅帧号倒退或超出 step 预算视为错误。
- 原生 transport 在每帧第一次查询锁存按钮 / 四轴 / 三轴角速度；同帧后续查询直接返回锁存动作，不重新应用控制器、不重复计帧。
  SDK Npad 的查询采样序号继续使用其原有记账；动作负载保持不变。六轴状态历史在同帧内保持同一快照。
  真实 HID 直接读取 RL 锁存动作，键盘 / 其它手柄或菜单 FIFO 不能覆盖受控动作。
- 为避免跨线程查询拿到锁外旧帧号，真实 HID 在输入锁内读取当前 present 计数。恰好在暂停预算端点到达的查询等待下一条 STEP，越过端点及帧号倒退仍拒绝。
  每个输入帧有独立 generation 标记，允许下个帧的查询与 present 尾部交错而不把前一帧误计为无输入。
  info 新增 `input_repeats`，保留每步 `frames_without_input`；已经结算的端仍按现行规则中立推进。
- 原生传输 / 生命周期检查 **11 项通过**，包括同帧动作只应用一次、预算端点并发查询等待下一条 STEP，以及预算越界 / 倒退拒绝。
  新的真实 HID 接口检查 **11 项通过**（经实际 HLE 注册表调用）：同帧键盘 / 外部手柄变化不覆盖动作，六轴快照不重复积分；原 HID **73** 项仍通过。
- 第一轮锁存实机启动 `work/tests/m6-2p-20261018-125224-212640/` 在入房阶段主动回收，**0 step / KeyboardInterrupt，不算失败卡点或验收**。
  回收是为了在正式对局前补齐跨线程预算端点的组件用例；原冻结清单全部一致，两个宿主已退出。
- 完整修订正式入口：`bash tests/run_all.sh --milestone m6 --players 2 --state-dump --timeout 2400`。
  总日志 `work/m6/frame-latch/final-two-player.log`；首局 `work/tests/m6-2p-20261018-125627-004534/`。
  冻结清单 `work/m6/frame-latch/final-acceptance-code.sha256`；本轮运行中不再修改源码 / 二进制 / 测试。
  失败时保留各端最后一帧像素，避免仅凭最后命中的阶段 gate 猜测末尾界面。
  **双端完整结算、重复查询实机覆盖、位置 / 墨量动作相关性和 reset 结果待本轮结束；通过后按指示先提交推送 M6-B。**

### 同帧锁存后的整局诊断：SDK 读取正常，发现客体时钟分离

- `final-two-player.log` 本轮锁存已越过先前 533 步重复 HID 停止位置，持续到 **679 步**，没有 FATAL / 重复查询中止；成功 ACK 的 `advanced` 始终精确。
  每个 15 帧 step 可见 `input_repeats=30`，来自已连接 Npad / 六轴等多次查询，按新规则正常返回同帧动作。
- 但 0 号实际走到 Winners 后返回私房房间，1 号未进入 Judge，随后原生调用 DisconnectNetwork / CloseStation。
  最后像素 `work/tests/m6-check-2p-20261018-125626-983796/player_1-last.png` 确认为通信错误提示；0 号最后像素为房间列表。
  这次已用实际像素区分了陈旧 `phase=1` 与真实界面，没有把通信错误当结算。
  本局会话 `1609f30c5c602014c5041e93b0dfd68f`，原生退房调用为 `main+0x9554f4 / 0x955558`；空气服务没有队列丢包。
- 确认对端已退房且本局无法再到 Judge 后，主动 SIGINT harness 回收，结果保存为 KeyboardInterrupt / 退出 1，并保留首局失败证据；未开始 reset，未宣称通过。
- 待验证根因：此前仅在每端等待策略时冻结各自客体墙钟；按相同 present 数推进，渲染耗时不同的端会累计不同的有效运行时间。
  HUD 双端从 10800 到 0 的墙钟时长、近似帧位置汇总在 `work/m6/frame-latch/clock-drift-evidence.json`。对端正常读取 / 没有丢包仍不能保证原生结束握手赶上不同步的计时。
- 修订在 RL 附着后才启用每个 present **16,666,667 ns** 的客体时钟；启动 / 入房仍沿用 M5 原行为。
  复用原生宿主已有帧时钟推进及唤醒，不改游戏比赛时限、计分或结束判定，不把 socket 断开 / UI 错误伪造成终止。
  此开关只改变 RL 会话的时钟，不启用 DM_DETCLOCK 关联的确定熵 / 测试场景时间对齐。
  info 新增 `guest_time_ns / frame_time_ns`，Python 对每个 ACK 同时校验客体时间增量等于请求帧数 × 固定帧长。
- 生产时钟组件 **11** 项、原有手动帧时钟模式 **5** 项通过，传输 / 生命周期 **11** 项和真实 HID **11** 项仍通过。
  新入口仍为 `bash tests/run_all.sh --milestone m6 --players 2 --state-dump --timeout 2400`；日志 `work/m6/frame-latch/clock-two-player.log`，
  运行冻结清单 `work/m6/frame-latch/clock-acceptance-code.sha256`。**正在实机验证该时钟修订；当前不提交、不签收。**

### 时钟修订试验：固定帧时钟回退，改为全端共享策略暂停

- 固定 16,666,667 ns / present 的实机试验 `work/m6/frame-latch/clock-two-player.log`：正常开局且 step(1) 返回，随后 step(7) 超过 60 秒，未继续返回 ACK。首局 `work/tests/m6-2p-20261018-131215-852423/`，检查目录 `work/tests/m6-check-2p-20261018-131215-831650/`；两个宿主均优雅退出 0。**该方案未通过，已移除，不作为可用功能交付。** 假设是局内原生计时等待依赖墙钟继续推进，纯 present 时钟可能形成下一帧前的等待循环。
- 新方案保持推进期间墙钟运行，使用同一个 POSIX mmap 文件中的 C11 lock-free 64 位原子时钟；所有端读取相同的暂停累计量。协调器先收齐全部 ACK，再统一暂停；下一批 STEP 发出前统一恢复。快端等待慢端期间也继续运行同一时钟，避免每端分别扣除不同耗时。启动 / 入房仍沿用原有时钟。
- 游戏帧预算仍由 present 屏障精确计数；共享时钟不承诺固定物理 dt 或确定性。`guest_time_ns` 是诊断值，撤掉错误的固定帧时长断言；info 的 `barrier_guest_time_ns` 为收齐本轮 ACK 后的公共暂停时间。
- 原生生产时钟检查 **13 项通过**，覆盖运行时时间前进、暂停期间 present 计数独立、跨进程同一暂停值 / 恢复和单调性；原有手动帧时钟模式 **5 项通过**。传输 / 生命周期 **11 项**、ctypes 共享文件烟测通过。正准备实机双端整局 + reset，尚未签收 / 提交。

### M6-B 签收：帧锁存 + 位置 / 墨量，双端整局及 reset PASS

- 正式入口 `bash tests/run_all.sh --milestone m6 --players 2 --state-dump --timeout 2400` **退出 0**。
  结果 `work/tests/m6-check-2p-20261018-132711-458355/result.json`：passed=true，errors=[]，full_m6_passed=false。
  总日志 `work/m6/frame-latch/shared-two-player.log`。首局 `work/tests/m6-2p-20261018-132711-480659/`，重开 `work/tests/m6-2p-20261018-133648-871495/`。
- 首局 **447** 次同步 ACK 到双方 ResultWinners；双方本轮均在第 **416** 步进入 Judge，各自 terminated 后仍中立推进。第二次 reset 使用新 PID / 新房间 / 新存档副本进入 InGame，并再执行 **10** 步；总计 **457** 步。1 / 7 / 31 帧跳和策略延迟下的精确帧数检查通过。
- 原生同帧重复 HID 正常返回锁存动作，15 帧常见 repeats=30（31 帧最大62），未重复应用或报 FATAL。真实本局每端 frames_without_input 合计0；无输入帧的正常推进由原生组件夹具验证，不将其写为本局实机命中过。
- 像素：静止 MAD **0.944–1.090**，移动 / 视角 MAD **48.775–80.238**（门槛3），headless 内部720p→128×72 RGB且无屏幕提交。
  正式位置观测自身位移 **7.221553**、中立对端漂移 **0**。0号射击墨量 **1 → 0.758284**，下潜等待恢复 **1**；仅1号射击同样降至 **0.758284**，0号保持1。各项动作相关性均 passed。
- 共享时钟实机效果：第300步双方原生 HUD 原始计数都为 **2670 / 60 = 44.5秒**；原先逐端冻结同一步为2828 / 3335。双方现均完整走完结果序列，未再命中旧的通信错误。该次对照支持各端分别扣除策略等待时间导致计时分离的根因判断；不宣称固定物理dt / 确定性网络调度。
- 基础回归：RL 传输 / 生命周期11项，真实HID11项，共享生产时钟13项 / 原有手动帧时钟5项，GPU148 / headless152，NVN79，HID73，LDN frontend10 / air59，host options32及资源停止规则等通过。
- 四个宿主均优雅退出0；两局 pressure最大1、footprint合计峰值 **7575 / 8020 MiB**，新增swapout均0。原件与参考档hash仍为既定值。运行冻结清单 `work/m6/frame-latch/shared-acceptance-code.sha256` 全部匹配；补丁正 / 反向检查通过。仅源码 / 文档 / 补丁入库，游戏数据与像素等证据保留在忽略的work/。
- 按本轮指示先提交推送 M6-B，再逐字段补朝向、HP / 存活、特殊量、比分 / 涂地比例、剩余时间；可见队友 / 敌人及击杀计数也尚未验证。完整 M6 / 八端随机策略未签收；没有调用其它模型。

### 继续逐字段：朝向正式观测 / 其余字段调用时诊断（待验）

- M6-B 已提交并推送 **db4376e21644430cb42316eac6640854431f6651**，已独立核对远端 main 同 SHA。
- 自身包 +0x44 的 forward 单位向量已在 B 实机日志中验证归属：转向移动窗口自身转约1.99弧度、中立对端0；全局样本长度约1±1.2e-7。+0x5c 是另外的相机 / 瞄准方向，不混为身体朝向。
  接入 `heading=atan2(forward.x,forward.z)`（弧度，0朝+Z、正向转向+X）及独立有效位，沿用采样帧 / 过期屏蔽；非法 / 非单位向量无效。正式传输夹具有限 / 非有限检查及全部11项回归通过。
- 新增短实机 `tests/test_m6_fields.py`，分别对两个控制器做转向对照；控制权切换前安排中立窗口，防止上一段动作收尾 / 10Hz包采样滞后污染中立对端基线。其 `--survey` 只把候选原生字节写入忽略日志，不加入训练观测。
- 一次入房阶段0 step的预备启动 `work/tests/m6-2p-20261018-134821-772343/` 主动回收，以补齐上述中立间隔；这是测试基线修订，不是实机字段失败或新卡点。两端场景尚未开始，仅启动了0号宿主，已优雅退出。
- 继续运行 `tests/test_m6_fields.py --survey`，总日志 `work/m6/next-fields/heading-and-survey.log`；冻结清单 `work/m6/next-fields/heading-acceptance-code.sha256`。朝向真实输出通过后单独提交；当前朝向及调用探针修订尚未提交。
- 开发探针改为实时调用取参：PlayerDamage更新（HP候选）、SplUISuperGaugeCtrl更新（特殊HUD候选）、SplUIResultStats00Ctrl绑定PaintPoint（结算计分候选），以及本地包所属控制器的现场参数；结合涂地 / 特殊输入 / 跌落窗口。构造默认值1000或未变化的数值不作为HP验证。

### 朝向字段签收：双端各自转向对照 PASS

- `tests/test_m6_fields.py --survey` **退出0**，`work/tests/m6-fields-20261018-134951-255711/result.json`：passed=true、heading_passed=true、errors=[]，共251步（短字段检查，未宣称整局 / reset）。会话 `work/tests/m6-2p-20261018-134951-277078/`。
- 正式 `heading / heading_valid` 输出：仅操作0号，自身最大转向 **1.992044 rad**、中立1号 **0**；中立收尾后仅操作1号，自身 **1.945975 rad**、中立0号 **0**。空间 / 有效位 / 非有限屏蔽与11项传输回归通过。主整局测试已加入同样的朝向动作对照，八端主入口仍待运行。
- 两宿主均优雅退出0，运行冻结清单全部匹配，无新增swapout，pressure正常；未改存档原件，未提交游戏数据。按指示单独提交推送朝向。
- 其余候选事实：局内 PlayerDamage 更新各端仅见一个持续对象，但本轮原生 +0x88 始终1000，仍缺少真实受伤 / 死亡变化；不能认定为已验证HP。
  `SplUISuperGaugeCtrl` 有微小增长，与包+0x80的整数候选继续比对中；RS输入未证明成功释放特殊。
  包+0x88会频繁归零，已排除累计涂地点数解释。另一个假设也被证伪：编码现场x21的vptr为main+0x5c38170，不是PlayerNetControl的main+0x5d3d270；source-x21虽为0x478，不能沿该猜测读取控制器owner。开发探针使用vm_read安全取样，正式观测没有这些越界猜测读取。
- 下一步用已验证位置 / 朝向导航出出生区域，并校准六轴俯仰以涂到地面；本轮长段移动被出生区域墙体限制，仅获得极少涂地，未构造有效受伤反例。继续可验证的计时 / 特殊量与受伤场景，不把常量命名为HP。

### 剩余时间字段签收：正式观测下降 / 两端一致，双端自然结算 PASS

- 朝向提交已推送 **2b9c59eba7c99b6ad331b4adf398e1d56643bfb4**，远端同SHA。继续按“验证一个、提交一个”推进，本次先提交计时。
- 新增构建 / 原指令双校验的 OBS25：`SplUITimerCtrl` 每帧更新的第二条 prologue main+0x3ef6934（a9027bfd），从现场x0读+0x140倒计数、+0x14c比例60和+0x148单字节启用位，InGame之外不接收准备阶段90秒HUD。没有保留并在调用外解引用对象指针。
- 正式观测 `remaining_time`（秒，float32）、`time_valid`，info `time_sample_frame`；越界 / 非有限 / 陈旧 / 非InGame时屏蔽。传输11项含有效计时与非法值屏蔽通过，原生宿主构建与补丁正 / 反向检查通过。
- 实机 `work/tests/m6-fields-20261018-140411-532662/result.json` **passed=true / errors=[]**；会话 `work/tests/m6-2p-20261018-140411-554141/`。正式观测0/1号分别 **166.433334 / 166.449997 → 155.850006 / 155.866669秒**，双方下降且差0.016667秒；朝向双端对照也通过。
  同次继续诊断到双方原生Winners：393步由字段脚本记录，另中立推进结算至Winners；未宣称重跑reset。总日志 `work/m6/next-fields/time-and-battle.log`。
- 六轴俯仰动作实机生效：正X角速度.08使独立俯仰候选从接近0变到-0.986647，水平视向基本不变；由此校准地面射击。位置 / 视向闭环带0号离开出生区至场地内部，再令1号接近并交火。
- 新的后续字段证据（尚未在本次计时提交中导出）：仅0号涂地窗口，包+0x80从0增49，1号仍0；与特殊HUD float+0x4c ×100/75逐样本比对。
  交火后0号包+0x70 / PlayerDamage现场+0x88均见570..1000，1号均见0..1000，且有恢复；每端InGame期间唯一更新Damage对象 / owner指针。详见 `work/m6/next-fields/field-correlations.json`。该证据支持下一步接入HP与特殊量，仍不将HP>0直接命名为权威存活状态。
- 两宿主均优雅退出0，pressure最大1、footprint合计峰值7985 MiB、新增swapout0；原件 / 参考档hash不变。冻结清单 `work/m6/next-fields/time-battle-code.sha256` 全匹配。
- 暂不宣称全模式计时 / 加时已覆盖。计分探针此次尚未命中，后续改查结果meter设值调用；存活与可见队友 / 敌人仍未签收。完整M6及八端随机策略未签收，未调用其它模型。

### HP字段接入：真实交火映射 + 正式传输检查

- 剩余时间已提交推送 **4c3afa9a1f4d06c57e8162520e824ce6dab2b859**，远端一致。
- 前述实机交火为独立证据：自身编码包+0x70与实时PlayerDamage+0x88同时下降 / 恢复；0号范围570..1000，1号0..1000。
  0/1号分别有2057 / 2025个包，使用最近的独立Damage样本直接比对，精确相等占 **95.916% / 99.852%**；其余为更新 / 10Hz编码时序差异，未当作同物理帧样本。
  局内每端各唯一Damage对象和owner指针，不再依赖被证伪的网络容器→PlayerNetControl猜测。全部88 / 6次包HP变化保存在 `work/m6/next-fields/field-correlations.json`。
- 加入正式 `hp`（原生1000归一化为1）及`hp_valid`，沿用本地包采样帧 / 有效期 / 阶段屏蔽；非法>1000值输出无效，不把其它装甲池猜测为自身HP。
  生产原生callback→socket→Python传输检查 **12项通过**，新用例按实机值检查 **1 → 0.57 → 0 → 1** 与有效位；宿主构建、补丁正 / 反向检查通过。
- 验证边界：映射的动作相关性来自上一局真实PvP，新增传输字段由生产夹具验证；接线后的完整实机HP动作测试还将用新增 `tests/test_m6_combat.py` 重跑，当前不宣称这项新长测试已经通过。
- 权威存活仍未接入：不直接把`hp>0`导出为alive。跌落 / 重生阶段有独立原生流程，不能只凭未变化的HP或缓存Jump/Respawn子对象vptr判断。继续查实际状态标签 / 更新调用。

### 特殊量字段接入：自身涂地与独立HUD比对

- HP已提交推送 **9163a51488eb9994479fb80f87ce45f7b28b958f**，远端一致。继续单独提交特殊量。
- `paint-route-0` 真实窗口仅操作0号向地面射击 / 移动，原生包+0x80 **0 → 49**，中立1号始终0；与 `SplUISuperGaugeCtrl` 现场float+0x4c按75满格换成百分数比对，HUD范围0..49.633672%，逐包与最近HUD样本最大差 **1.052532个百分点**（含不同更新时序）。中立对端HUD亦始终0。归属和动作相关性均由独立实时调用与包数据证实，见field-correlations.json。
- 正式导出 `special`（0..1，原生整数百分数，1%精度）和独立有效位，沿用本地包采样帧 / 陈旧 / 非InGame屏蔽；>100的数值无效。
  生产callback→socket→Python **13项通过**，新序列0→0.49→1→0及非法101屏蔽通过；宿主构建通过。
- 映射的动作 / HUD证据来自前一真实对局，新的正式输出由生产传输检查验证；下一轮 `tests/test_m6_combat.py` 会同时重跑正式HP受伤 / 恢复及正式特殊量自身涂地对照。尚未将该新增长测试写为已通过。
- 不把49%时的RS输入写成成功释放特殊，满槽后释放的实际效果仍需后续覆盖。存活、比分 / 涂地比例、可见其它玩家和击杀计数未全部验证；完整M6与八端尚未签收。

### 正式HP / 特殊量实机回归 PASS，继续 HUD / 结果参数

- 特殊量已推送 **7d8de7cad2acc71d4739d54f6ca7941032aa8a2b**，远端一致。`tests/test_m6_combat.py --inspect-results` 正式读取已接线HP / 特殊量，**退出0**；`work/tests/m6-fields-20261018-142435-279913/result.json`：passed=true、errors=[]、hp_passed=true、special_passed=true、time_passed=true，425次step记录，另中立推进双方Winners。
- 会话 `work/tests/m6-2p-20261018-142435-310915/`；日志 `work/m6/next-fields/official-combat.log`；源码 / 宿主冻结清单 official-combat-code.sha256 全匹配。
  正式HP0号0..1、1号0.225..1；额外离线核对“HP保持正值且无>10单位位置跳变”的连续区间，1号恢复 **0.775**，不靠0→1重生当普通回血。正式特殊量仅0号涂地 **0 → 0.44**、静止1号0；两端时间166.133 /166.167 →155.533 /155.567秒。
- 本次周期性松开ZR以验证输入边沿 / 重生流程；两端均完整到Winners。全部agent终止后先统一恢复时钟并RELEASE，再用M5菜单FIFO查看后续结算UI，遵守已终止STEP只推进不施加动作；此操作单独标为 post_result_menu_inspection，未冒充训练step / reset。
- 四类新结果调用已捕获：ResultMeter原生设值0号参数89/37/42/18，对端37/89/18/42；统计控件绑定PaintPoint时分别显示个人点数134 /68。不能将89/(89+37)误报为覆盖全地图的涂地比例：回查PaintPercent文本formatter，它将第三 /第四参数按10拆分整数与小数，实际显示 **4.2% /1.8%**（观察者自身在前）。后续从该formatter现场参数导出，单位和顺序明确。
- 后续存活 / 公开状态已找到具体入口：VS_MainTV_00布局实际引用TGPlayerIcon_00，包含Down/Special动画；`SplUITGPlayerIconCtrl` 的现场更新从玩家弱引用取得 live Player，再设置缓存状态（正常 /倒下 /不可用）。继续用该HUD数据验证存活和其它玩家公开基本状态，避免HP或缓存子类型代理。游戏布局原件及诊断输出仍仅在忽略work/。
- 两宿主均优雅退出0；pressure最大1、footprint合计峰值8072 MiB、新增swapout0、参考档hash不变。本轮没有reset新一局；后续HUD/比分接好后再跑双端整局+reset及八端随机策略。未调用其它模型。

### 比分 / 涂地比例接线：原生结果文本formatter，单位已核对

- 正式HP/特殊量实机测试与菜单诊断提交 **c8ee2a85529bc3faa92f04c5cbfdee911e183749** 已推送。
- 新比分OBS位于原生文本formatter安全prologue：Turf `main+0x3f6d6a4`、规则计数 `main+0x3f6df34`，原指令均a9016ffc；构建号及原指令双校验。
  Turf函数绑定 `T_PlayerPercent_00` / `PaintPercent` 并将第三、第四参数除10分成整数与小数。前一局实际设值经+0x184/+0x188原样传给该formatter为 **42 /18**（自身 /对方），对端18 /42；所以结果为 **4.2% /1.8%**，不是89/(89+37)。89/37参与bar长度，不能当全地图分母。
- 导出 `score[2]`、`score_valid`、`score_units`（1百分数、2规则计数），Turf另有`turf_ratio[2]`及有效位，info含采样帧。只在Judge接收结果formatter值，保留到Winners，下一InGame清空；没有局内实时涂地比例时明确无效。协议头上限扩大到4096字节，为后续HUD数组留空间。
- 生产传输 **17项通过**，覆盖42/18→4.2/1.8及.042/.018、100/30规则计数、非法值、阶段过滤和新一局清空；原生宿主构建与补丁正 / 反向检查通过。新结果gate的真实socket输出将与下一轮HUD一起验证，当前映射证据为实机设值+原生formatter数据流，正式通道为生产组件检查。
- 非Turf规则计数路径目前有原生KO==100/0显示逻辑及组件证据，尚未另跑真实非Turf对局；不宣称全模式已签收。剩余时间与其它里程碑状态不变。

### 存活 / 公开玩家HUD接线与双端集成回归（运行中）

- 比分接线提交 `edb742fcd3113659198774c5cd323d6c41f61c6c` 已推送。新增OBS28取本地PlayerDamage每帧更新的owner现场，OBS29在原生RTTI已确认live Player后关联HUD节点，OBS30在TGPlayerIcon更新epilogue复制缓存状态；对应main偏移2920760/4011c64/4011e28，均有构建号与原指令校验。PlayerInfo+7e8原生槽位范围0..7；不从构造期猜归属，训练侧不保留可供异步解引用的对象指针。
- `alive`独立取自身HUD Normal/Down，不能用HP>0代替。每个观察者只导出其自身顶部公共HUD的各槽位状态、特殊就绪指示和Normal→Down事件；配置好的公开分队/武器按各端原生self_slot合并。未提供视野外敌方位置或HP，缺失/陈旧信息用有效位屏蔽。槽位碰撞会中止验证，不能默默填猜测。
- reward示例接入默认环境：特殊充能正增量作为涂地塑形，敌队公共HUD倒下事件作为团队消灭信号（包含环境死亡，无最后一击归属）；未将其命名为真实paint_points或个人kills。可关闭/自定义。
- 帧锁存补充并发边界：在预算端点等待下一STEP的自动帧号HID查询，唤醒后重新读取当前帧号；明确帧号调用仍检查倒退/预算。原生夹具覆盖端点等待与同帧锁存、独立HP/HUD生死、缺席状态、公开特殊就绪与元数据归属。
- 当前 `.venv/bin/python tests/test_m6_combat.py --inspect-results --reset-check`，日志 `work/m6/next-fields/hud-score-two-player.log`，首局 `work/tests/m6-2p-20261018-151321-623112/`。冻结清单hud-score-code.sha256；宿主/测试运行期间未改动。新增门槛包括正式alive倒下、真实HUD事件、双方结果百分比顺序，以及新进程第二局十步。尚未把运行中的测试算作通过；八端仍待双端通过后执行。

### 存活 / 公开HUD / 结果比分集成签收：双端整局 + reset PASS

- `tests/test_m6_combat.py --inspect-results --reset-check` 完整结束，`work/tests/m6-fields-20261018-151321-599465/result.json` **passed=true / errors=[]**，heading/time/HP/special/public_hud/alive/score/reset各项为true。首局426次step，reset后第二局10次，共 **436**；结算动画另由中立advance_settlement推进至双方Winners。首局及reset会话分别为151321-623112 /152305-922392。
- 两端自有原生slot分别0/1，双方HUD都映射到同样两个槽；每个玩家均有一次Normal→Down→Normal。0号63次ACK观察为Down，其中29次HP仍正；1号30次Down ACK全部HP正，进一步实证alive不能用HP>0代理。两个观察者各自的原生HUD均记录[1,1,0,0,0,0,0,0]倒下事件，没有合并对方隐藏内部状态。
- 正式HP0号0..1，1号0.754..1，1号在正HP、无位置大跳的连续区间回血。仅0号涂地特殊量 **0→0.44**、1号0；自身heading分别转1.946rad、中立对端0；倒计时双方166.58/166.57→156.03/156.00秒。
- 正式socket在Winners输出比分 **[4.0,2.0] /[2.0,4.0]**，Turf比例[.04,.02]及反序；与真实ResultMeter参数第三/第四40/20及20/40相符。结果formatter接线已获实机验证。非Turf比分仍只有静态/组件覆盖，未另跑非Turf完整局。
- reward累计1.062 /1.031，均有限，来自公开敌方倒下事件各1次加充能塑形；其中包含环境死亡，不能称为个人kills。生产传输/生命周期/reward **24项通过**，独立HUD/HP、缺席、就绪位、原生slot元数据映射均有组件覆盖。
- 四宿主均优雅退出0，无FATAL；两局footprint合计峰值 **8226 /7943 MiB**，pressure最大1，新swapout均0；原件/参考档hash不变。hud-score-code.sha256全部匹配；源码/门控构建与补丁正反向检查通过。游戏数据和画面仅在忽略work/。
- 本次提交公开HUD/存活与reward集成，下一步正式入口八端随机策略整局；**完整M6尚未签收**。没有新的卡点，没有调用其它模型。

### M6-C 八端正式验收启动（待结果）

- HUD/存活集成已提交推送 **c422fb9bfe60b0eeffb997cced538a257c743c5e**，已核对远端同SHA。
- 正式命令 `bash tests/run_all.sh --milestone m6 --players 8 --timeout 7200`；日志 `work/m6/eight-player/acceptance.log`，会话 `work/tests/m6-8p-20261018-153022-915232/`，冻结清单acceptance-code.sha256。资源准入/停止规则沿用M5，warning继续，critical或新增swapout超门槛停止，不用额外磁盘换出硬撑。
- 入口组件GPU148/headless152、NVN79、HID73/真实RL11、RL传输生命周期reward24、共享时钟13/手动模式5、LDN frontend10/air59全部通过，正在逐端加载入房。
- 主测试补齐当前HUD采样的槽位检查（使用warmup后的infos），八端中立归属对照取对方队伍玩家以避开出生点友方身体碰撞，逐步检查reward有限并记录累计，最终要求同队比分一致、对队比分反序。八端单局PASS后才设置full_m6_passed；双端字段动作相关性和reset证据由前述独立集成回归提供。
- 运行中的测试不计为已通过；完整M6仍待真实八端自然结算与清理结果。

## 2026-10-18：M6 最终签收 PASS，双端字段 / reset + 八端随机策略自然结算

**M6 PASS。** 本节覆盖前文“八端待验 / 完整M6尚未签收”的状态，保留所有历史失败及已移除的试验。没有新卡点，没有调用其它模型。

- 正式命令 `bash tests/run_all.sh --milestone m6 --players 8 --timeout 7200` **退出0**；`work/tests/m6-check-8p-20261018-153022-895155/result.json`：passed=true、full_m6_passed=true、eight_player_layer_passed=true、errors=[]。会话 `work/tests/m6-8p-20261018-153022-915232/`；总日志 `work/m6/eight-player/acceptance.log`；额外ACK/资源核对evidence-summary.json与各步原始steps.jsonl均留在work/。
- **186** 次同步step，八端均第 **156** 步Judge、**186** 步Winners；各agent独立terminated后，中立推进到所有Winners。实际本轮恰好同一步结算，不宣称实机命中异步终止；异步情形由生产生命周期夹具覆盖。没有把时间到 / socket关闭 / 通信错误当结算。
- 1 /7 /31帧跳、策略等待和常规15帧跳，**所有端ACK帧差错误0**；每端同帧重复HID最多62次正常锁存，未重复施加或FATAL。每端本次frames_without_input合计0；缺读present正常计帧由原生组件夹具覆盖。采用全端公共策略暂停时钟，不是固定物理dt，也不宣称确定性。
- 八端own native slot唯一 **0..7**，每个观察者都读到八个有效公共HUD槽位；配置队伍/武器按这些真实slot关联。自身位置/heading/HP/ink/special、HUD存活、时间和final score均符合空间/有效位范围。公开HUD数据来自各端本地HUD，不合并视野外敌方位置/HP。
- 八端实机动作对照：静止像素MAD **3.107–3.266**，推杆/视角MAD **44.335–64.979**（阈值4.764）；0号自身位移 **7.230554**，中立敌方0；自身转向 **1.991809rad**，中立敌方0。0号射击墨量 **1→.926142**、下潜恢复1；1号独立射击 **1→.758284**，0号保持1。低帧率/运行时间不同会改变固定present预算内的耗墨幅度，本测试只断言实际动作相关性，不假定固定physics tick。
- 倒计时所有端约 **148.03–148.12→134.52–134.60秒**；比分在结果为Alpha四端 **[4.4,4.0]**、Bravo四端 **[4.0,4.4]**，对应turf_ratio [.044,.04] /反序，全部score/turf有效。同队一致、对队反序门槛通过。每端reward累计有限；本局只有充能塑形正奖励，没有宣称击杀事件已发生。
- HP损伤/普通回血、特殊量自身涂地对照、独立HUD倒下与正HP共存、正式比分及reset由上一节双端集成实机再次验证：**426+10=436步**、四宿主优雅退出；0号特殊0→.44、静止对端0，两端各一次HUD倒下事件，正式结果4.0%/2.0%及反序。M6-B随机整局+reset、像素/位置/墨量正式入口447+10步证据亦保留。没有把八端随机局未出现的受伤/缺读场景写成该局覆盖。
- 八宿主均优雅退出 **0**，无CRASH/FATAL/GPU执行错误，所有进程最终有headless screen_submits=0/composite=0；内置720p游戏纹理导出128×72RGB，未向屏幕提交。参考档/原件hash未变，临时socket与空气服务由环境清理。
- 970次资源采样：最高pressure **1 / normal**，新增swapout **0**，footprint合计峰值 **28728 MiB（28.05 GiB）**、RSS合计峰值 **11932 MiB**；两者含共享页口径不同，不将RSS/Metal allocated简单叠加。共同InGame采样窗口206.05秒，当前带像素读回/屏障的墙钟帧率约 **10.77–11.07 fps/端**，包括策略/协调开销，不作为同场景M5性能或加速比。
- 组件回归GPU148/headless152、NVN79、HID73/真实RL11、RL传输生命周期reward24、共享时钟13/原手动模式5、LDN frontend10/air59及资源停止规则通过。宿主和全部受测源码acceptance-code.sha256逐项匹配，补丁正/反向检查通过；仅提交splatoon3-native源码/文档/补丁，游戏数据、游戏画面、NSO/RomFS/shader/prod.keys均未入库。

### 可用接口与签收边界

- `rl/`提供PettingZoo ParallelEnv、reset复用M5启动/配置/分队、同步step、正式动作/观测spaces、逐agent终止及结算推进、可关闭/自定义的reward示例。Unix socket + POSIX mmap时钟接口不依赖macOS专有IPC；实际原生游戏仍在当前macOS/Metal宿主验收。
- 自身包字段约10Hz，120 presents过期，HUD/时间也有采样帧/有效位；不把每帧导出等同于每帧物理状态采样。结果比分/涂地比例在Judge/Winners有效，局内不提供实时涂地图。当前实机字段范围为默认Turf War / Scorch Gorge；其它模式/地图/武器可沿M5配置，但非Turf比分及加时未各自实机签收。
- reward示例是“充能增量涂地塑形 + 敌队公共HUD倒下事件”，包括环境死亡，没有个人最后一击归属或真实paint_points/kills计数；这些缺项在文档/结果中明确标记，未用零伪装。目标所需公开队友/敌人基本状态由公共HUD提供，不承诺世界空间FOV可见位置列表。

## 2026-10-18：第二阶段启动，A1 进行中（尚未签收）

- 按 A1 → A2 → A3 → A4 → A5 顺序推进；M6 最终签收保持有效。A1 前置问题是 M6 的共享时钟只扣除了策略等待，执行期间仍跟随墙钟，因此 present 数不等于物理时间。
- 所有 1v1 统一使用本地 `WeaponInfoMain` 的 `Saber_Normal_00` / **8000**（工作刮水刀 / Splatana Stamper）。不使用 8001 的异配装版本或其它刮水刀。
- 首批选择占地地图 **1 / Vss_Yunohana（温泉峡谷）**、**2 / Vss_District00**、**3 / Vss_Yagara**。选择目的分别为中央高差攻防、桥梁及窄路连通、中央遮挡与两侧绕行，形成高差、通道、遮挡三类对照；均已有本地 Versus 目录项，不新增外部数据。这里是实验选图及研究理由，碰撞几何、可行走性、命名区域与实机路线将在 A4 验证后签收，不把目录可选写成已验证寻路。
- A3 必须提供独立的裁判真值接口与经遮挡 / 潜墨裁剪的策略接口；策略进程只能接收后者。A5 基线限定直冲 / 占高台，不开展 T1 策略调强。
- A1 新增 `clock_mode='fixed60'` 实验选项，RL 接管前继续使用原来的启动 / 建房时钟；接管后每个宿主按自身 present 数累计 `floor(N*1e9/60)` ns，并唤醒以客体时间等待的线程。M6 默认仍为 `realtime`，不将实验模式默认启用。
- 原生时钟组件已通过 fixed60 **3604**、原共享时钟 **13**、原手动时钟 **5** 项检查。组件只证明计时实现；实机倒计时、位移、伤害的时间一致性尚未证明。
- 第一轮双端实机诊断：`work/a1/probe-fixed.log`、`work/a1/probe-fixed.json`；会话 `work/tests/m6-2p-20261018-170048-723919/`。所有游戏数据、画面与原始证据仍仅留在忽略的 `work/`。

### A1 当前卡点：fixed60 接管后首个 STEP 无 ACK（停止，未签收）

**A1 未 PASS，按本轮“卡住时记录现象和假设然后停下”的要求停止。A2–A5 未开始；没有请求其它模型，没有 commit / push。**

- 已试方案：保留 M6 原来的启动 / 建房路线与默认 `realtime`；只在 RL_ATTACH 时将显式 `fixed60` 宿主切换到自身 present 计数时钟，同时使原有 `dm_detclock_enabled()` 的定时等待分支生效，由 present 回调唤醒等待线程。不在协调器中替游戏补帧，不让快端推进慢端的时钟。
- 实机配置：两端、占地、stage_id=1 / Vss_Yunohana、武器 `[8000,8000]`、frame_skip=15、STEP socket 超时30秒；命令 `.venv/bin/python work/a1/probe_fixed.py`。诊断脚本、输入、结果与日志均在 `work/a1/`。该临时诊断脚本自身退出0，但 JSON明确 `passed=false`，**不能把外层退出码当成验收通过**。
- 两端成功同房、原生 InGame 后接管；初始 ACK 的 `(frame, phase, remaining_time)` 分别为 **(14523,1,179.933334)** 与 **(9917,1,179.883331)**，公开 native slot 为0 / 1。两个配置文件均确认 `DM_WEAPON=8000`、`DM_RL_CLOCK_MODE=fixed60`、headless=1。
- 首次向两端发送15帧中立 STEP 后，等待 player_0 响应时 `rl/protocol.py` 的 `stream.readline(4097)` 在30秒触发 `TimeoutError('timed out')`；**已完成 STEP 样本数0**，尚无首个 STEP ACK。没有逐present日志，不能断言卡在接管后的第几帧，也没有分别读取 player_1 的响应来断言两端都未 ACK。位置、伤害及与实时模式的脚本对照均未开展。
- 证据：`work/a1/probe-fixed.json`（初始ACK、异常栈、samples=[]）、`work/a1/probe-fixed.log`；原生日志为 `work/tests/m6-2p-20261018-170048-723919/player-{0,1}/host.log`，接管记录 `RL_ATTACH frame=14523` / `9917`。宿主二进制、受测计时源码、Python环境代码与诊断脚本固定在 `work/a1/probe-code.sha256`，结束后逐项复核匹配。
- **假设，尚未证实**：客体时间仅在 present 后推进，而产生下一个 present 的某条 SleepThread / 定时 WaitSynchronization / 游戏内部轮询路径可能先等待客体时间达到下一 deadline，形成“等时间→等present→等时间”的环。接管前已经创建的墙钟等待与接管后的离散时间等待之间也可能有衔接问题。组件测试没有真实客体线程调度，不能排除这些循环；需要后续明确指示后采集线程等待栈，定位第一个阻塞依赖。没有用自动补时间或回退墙钟掩盖失败。
- 已通过的窄证据：fixed60时钟3604项、原共享时钟13项、原手动时钟5项；Python传输 / 生命周期24项、原生HID11项。它们不证明真实游戏60Hz物理，也不替代A1。`tests/run_all.sh --milestone a1` 的完整验收尚未接入，未将时钟组件冒充整个A1。
- 清理：两宿主均 SIGTERM **优雅退出完成**，无 CRASH / FATAL；本轮 dmhost / air / 诊断进程均已退出。190次资源采样 pressure最大1、新增swapout **0**、footprint合计峰值 **7170 MiB**。原件与只读参考档结束后SHA256均仍为 `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。
- 实验代码与说明保留为未提交改动，M6默认仍为realtime；`patches/0001-splatoon3.diff` 已按既有排除规则重新生成并通过反向应用检查。没有将游戏数据或游戏画面加入版本库，没有修改其它实验目录。

## 2026-10-18：按指挥方恢复 A1，先确认 realtime 的游戏时间

- 本节恢复前一节已记录的 fixed60 卡点。先在默认 realtime 模式用两端工作刮水刀测量 present、Timer HUD、客体 / 墙钟时间与位移；只有测量确认漂移后才修改 fixed60 的等待与推进时机。
- 新增 `tests/probe_a1_time.py`：逐step记录1/7/31/15帧预算、策略短暂停顿、原生Timer采样帧、位置与动作。该诊断始终 `full_a1_passed=false`，不能替代位移/伤害对照及正式A1入口。发生异常时，清理前逐宿主执行 `/usr/bin/sample <pid> 1 10 -file ...`，每次采样调用上限10秒，记录成功或失败。
- 新一轮命令 `.venv/bin/python tests/probe_a1_time.py --clock-mode realtime`，日志 `work/a1/realtime-probe.log`，输出 `work/tests/a1-time-realtime-20261018-171043-293516/`，原生会话 `work/tests/m6-2p-20261018-171043-316196/`。受测代码清单 `work/a1/realtime-probe-code.sha256`；运行中不改宿主。当前尚未把进行中的诊断记作通过。
- 原M6八端逐步原始证据补查：`work/tests/m6-check-8p-20261018-153022-895155/steps.jsonl` 的第1/61条记录，0号 native Timer采样帧47846→48754（908 present），剩余时间179.866669→105.416664（74.450005秒），对应60Hz理应15.133333秒。此为历史原始日志佐证；本轮仍按指示补新的双端实时测量。

### A1 realtime 新测量完成：确有漂移，进入 fixed60 等待栈诊断

- 上述新双端诊断退出0，`probe_completed=true, full_a1_passed=false, errors=[]`，完成80个step。计时窗口使用各端原生HUD采样帧，均为 **845 present**，60Hz应为 **14.083333秒**；实测HUD分别减少 **30.216675 / 30.266677秒**（比值 **2.145563 / 2.149113**），墙钟33.218361秒（其中包含显式策略等待）。因此本轮也证实：默认realtime不能按每present=1/60秒直接签收A1。
- 同窗口0号移动最大位移 **11.514735**，中立1号 **0**；逐step原始位置、Timer与动作在该诊断steps.jsonl。这里只证明动作相关性，未证明同脚本的跨模式物理一致或伤害一致。
- 206次资源采样pressure最大1、新swapout0、footprint合计峰值7102MiB；两宿主清理正常，受测源码hash逐项一致。保持完整原始证据。
- 已启动相同宿主的fixed60复现：`.venv/bin/python tests/probe_a1_time.py --clock-mode fixed60`，总日志 `work/a1/fixed60-sample-probe.log`；原生会话 `work/tests/m6-2p-20261018-171807-188371/`。本次先保留原失败实现，超时由脚本在清理前采集两个宿主的macOS sample；尚不改受测时钟或推进点。

### A1 等待栈证据与第一版帧入口修复（实机待验）

- 原失败实现的新复现退出1，`work/tests/a1-time-fixed60-20261018-171807-167045/result.json`：completed_steps=0、TimeoutError。清理前对PID77668 /93143分别运行macOS sample，**两份采样均退出0**，完整线程栈及命令结果保存在该目录的 `sample-player-{0,1}.txt` / `samples.json`。不再仅凭socket超时推断原因。
- 0号sample主线程70/70次采样均在 `svc_thread → block_inner (hle_thread.c:168) → pthread_cond_wait`；多个任务工作线程相同等待，另有工作线程在 `svc_thread → nanosleep`。主线程客体栈包含 `main+0x452cf98`、`main+0x4ad64b8`、`main+0x4ad19b8`、`main+0x4ad1ebc`；反汇编后者可见任务等待循环。另一个工作线程栈包含 `main+0x47ae94c`，其上层属于任务调用；没有把无名称函数猜成已确认的专用vsync函数。
- 第一版修复：fixed60在主线程进入阻塞SVC（睡眠/同步对象/条件变量/地址等待）及NVN纹理acquire入口尝试开始下一帧。按present区间CAS保证只推进一次，并在RL输入锁下检查当前STEP预算；完成present本身不再叠加推进。此方案仍待实机验证，不把组件通过写成循环已经解除。
- fixed60客体阻塞/睡眠增加60秒墙钟硬上限，记录线程、种类、帧号、调用LR及完成/超时；RL输入预算等待与命令socket同样有60秒上限。Python STEP接收30秒先触发sample，每个sample命令最多10秒。realtime原等待语义保留。
- 组件：fixed60 **10804项**（含预算禁止推进、同帧重复推进及3600帧精确累计）、原共享13项 / 手动5项、条件变量顺序1项、Python传输24项通过。条件变量目标此前缺少GAME profile include目录，已在该目标Makefile补充既有GINC；新增API补齐测试stub后重新编译通过。
- 新宿主命令 `.venv/bin/python tests/probe_a1_time.py --clock-mode fixed60`，总日志 `work/a1/frame-begin-probe.log`；原生会话 `work/tests/m6-2p-20261018-172949-616501/`，冻结清单 `work/a1/frame-begin-probe-code.sha256`。运行中不修改受测宿主。

### A1 第一版实机未通过：识别帧内任务轮询，继续修复

- 第一版诊断 `work/tests/a1-time-fixed60-20261018-172949-593871/` 退出1，completed_steps=0，仍未完成15帧预算。与原失败不同，0号已经从RL_ATTACH开始完成约12个present，最后记录 `RL_FRAME_BEGIN present=14532 tick=13`；1号最后tick=10。不能将已开始tick数当成已完成present数。
- 两端再次在清理前sample成功；0号主线程67/67次采样变为 `svc_thread → nanosleep`，客体任务栈包含 `main+0x47ae94c`。新RL_SLEEP日志显示短睡眠 **989ns** 与常规 **15,000,000ns** / **500,000,000ns**。`main+0x4690290` 反汇编可见：调用短睡眠后回到任务状态轮询，而不是完成一个新present。SDK的1000ns请求经19.2MHz tick换算约为989ns；旧固定时钟把这种帧内轮询也挂到未来游戏时间，仍会阻断本帧任务完成。
- 窄修复：仅fixed60下 **0 < SleepThread ns ≤ 1000** 使用宿主nanosleep完成微等待，不推进客体时间；其它正常睡眠/阻塞的固定时间规则保留。没有把整帧/跨帧游戏计时回退墙钟，没有为未完成present额外补tick。
- 新原生 `t_rl_sleep` 通过真实svc_thread调用检查1/989/1000ns：客体时间故意冻结，三次调用均及时返回且不改客体时间；测试自身alarm上限2秒，防止再次挂死。条件变量顺序回归仍通过。该窄证据不代表实机帧内轮询已经恢复。
- 第三轮fixed60实机诊断日志 `work/a1/short-sleep-probe.log`，冻结清单 `work/a1/short-sleep-probe-code.sha256`；仍按30秒STEP→逐端sample→清理的上限执行，结果待定。

### A1 fixed60 计时与原realtime行走对照完成，正式伤害/暂停验收启动

- 第三轮诊断 `work/tests/a1-time-fixed60-20261018-173950-776881/result.json` 退出0：probe_completed=true、errors=[]、80个完整STEP；full_a1_passed仍为false。845个present对应HUD **14.083328 /14.083329秒**，与 **14.083333秒** 的差仅浮点量化；全端、所有ACK相对初始ACK的guest_time_ns均严格等于 `floor(累计帧数*1e9/60)`，错误0。计时窗口墙钟39.385216秒，未把慢帧或策略等待计入游戏时间。
- 相同120帧全推前行输入，等待惯性/采样稳定后的位移：原realtime **11.514733536**、fixed60 **11.514744543**（差0.000011006）；中立对端均0。比较窗口总240 present，fixed60 HUD正好4秒，原realtime约8.233322秒；后者正是已确认的旧计时缺陷，不能谎称旧模式HUD用时已与修复模式一致。此次没有对手受伤，伤害仍待正式实机测量。
- A1正式验收明确分开：原M6 `clock_mode=realtime` 保留为兼容/漂移诊断；修复后的fixed60时钟同时用于连续运行参考（预先排队全部输入，无逐步策略等待）和受控运行（同脚本逐步注入等待）。比较二者原生HUD用时、实际位移及工作刮水刀的真实对手HP损伤，验证暂停不改变修复后的游戏行为；没有把旧墙钟计时错误作为正确用时基准。
- 为真实连续参考增加Client有序待收ACK队列；协议字节格式不变，仍逐条验证request/frame/advanced。预先排队1/7/31/15帧的生产传输夹具通过，现有合计25项通过。
- 已接入 `tests/run_all.sh --milestone a1`（尚未PASS）。正式入口通过共享时钟13/5/10804、短睡眠3、条件变量1、HID73/11、GPU148/headless152、NVN79、LDN10/air59与资源停止规则，进入实机。命令 `bash tests/run_all.sh --milestone a1 --timeout 2400`，总日志 `work/a1/acceptance.log`，原生会话 `work/tests/m6-2p-20261018-175235-778315/`，冻结清单 `work/a1/acceptance-code.sha256`。
- `tests/test_a1.py` 的移动/伤害脚本在相同修复时钟下使用混合帧预算，连续版预先排队、受控版每段等待0.2秒。命中准备是有上限的裁判诊断导航/瞄准，不作为A4技能库或T1策略交付；读取自身原始camera包与双方真值仅在该测试，不向策略接口承诺新字段。正式A1、commit/push及A2–A5仍待实机结果。

### A1 正式入口第1轮：移动/用时一致，新增等待上限误杀空闲线程（已修，重新验收）

- `work/tests/a1-20261018-175235-756433/result.json` **passed=false / full_a1_passed=false**，完成93个STEP。连续与暂停脚本HUD用时均 **1.5秒**，0号位移 **0.360044503683 /0.360044500001**，中立1号位移均0；移动/计时窄证据保留。
- 伤害准备尚未完成时，两端都因我新增的过宽上限退出：`FATAL RL_WAIT wall limit thread=0x1015 kind=3 timeout_ns=-1`。这是正常无期限地址事件等待超过60秒，彼时主对局仍持续推进；不是原来的fixed60首步死锁。两端SIGABRT/-6，Python看到socket关闭；清理因此报告非优雅退出，未将其改判为通过。
- 该轮异常时仍执行sample，但进程已退出，两个sample均255并记录“cannot examine process”错误；未把它当作已抓到线程栈，也未请求sudo。原生日志已有精确FATAL等待种类、线程与帧号。93步末尾0号在(-14.49,3.32,38.37)、1号在(12.88,6,-20.74)，HP均1；没有真实伤害验收。
- 修正：有限客体等待/睡眠保留60秒硬上限；原生请求ns<0的合法空闲等待，宿主每次只等待最多1秒并检查/记录，保持原有“等事件”语义。整体对局停止推进仍由STEP30秒上限触发sample与清理，不再因某个正常空闲线程长时间未收到事件终止健康对局。
- 新原生 `t_rl_idle` 把有限等待硬上限缩至100ms，实际无期限事件等待经历两次有界宿主轮询，在2.1秒后真实SignalEvent才返回，测试alarm上限5秒，已通过；短睡眠3项与其它正式入口组件继续通过。该测试接入A1入口。
- 新正式命令同前，总日志 `work/a1/acceptance-idle-fixed.log`，会话 `work/tests/m6-2p-20261018-180253-871311/`，冻结清单 `work/a1/acceptance-idle-fixed-code.sha256`。A1完整签收仍待真实伤害/清理结果，尚未commit/push。
- 新增idea内 `.gitattributes` 仅对生成的patch关闭文本空白诊断：统一diff的上下文行必须含空格前缀，会被外层git误认为空行尾空白/空格缩进tab。实际upstream源码仍由update-patch.sh的diff --check检查，补丁保持反向应用检查。

### A1 正式入口第2轮：健康越过空闲上限，裁判准备条件过严（修订后重跑）

- `work/tests/a1-20261018-180253-848365/result.json` 退出1、passed=false，完成293个STEP；没有再次发生60秒空闲线程误杀，原生对局仍健康推进。移动位移 **0.360044503280 /0.360044500000**、中立对端0、HUD均1.5秒；这些窄证据再次成立。
- 失败是测试自己附加的平面条件：0号停在约(17.3575,0,17.2752)，1号约(14.1641,3,12.1342)，水平距离约6.05但地面相差3个坐标单位；双方同期跳跃也不满足 `abs(dy)<1`。裁判按既定60游戏秒导航上限报错 `could not establish a flat 6..12 unit ... duel`，尚无伤害对照，不将已有移动证据升级为A1通过。
- 修订只在裁判测试：按真实三维距离选6..12单位的近距准备（限制高差），中立3秒待落地后确认仍在射程，选择地面较高一侧为射击者，另一侧先涂自己的脚下并恢复满HP。增加最多180帧的单帧视角微调，核对自身camera实际yaw误差<0.04rad、pitch误差<0.04，准备阶段不算入连续/暂停脚本比较。没有改游戏位置/HP/配装，也没有伪造命中或越过A4签收。
- 新正式命令 `bash tests/run_all.sh --milestone a1 --timeout 2400`，总日志 `work/a1/acceptance-3d-duel.log`；原生会话 `work/tests/m6-2p-20261018-181442-679357/`，冻结清单 `work/a1/acceptance-3d-duel-code.sha256`。组件再次通过，实机结果待定。
- 只读核对本地Params.pack中的WeaponSaberNormal：普通横挥弹体伤害350（HP总量1000）、弱挥弹体生成在动画第9帧；该弹体GoStraight状态5帧、初速度2.82、BurstFrame6。它们帮助确认60帧采样足够覆盖动作延迟，**不替代实机伤害验证**。提取的原始参数JSON仅在忽略的 `work/a1/stamper-gameparams.json`，未加入版本库；没有将UI Range值直接认作测得的物理射程。

### A1 当前新卡点：实际横挥未命中，伤害对照无法验收（停止，未签收）

**按本轮“真正的新卡点才停下”的规则，停止在此。原fixed60首步等待环已跨过并取得80步计时证据；当前新卡点是真实命中校准，不能把计时/移动一致当作完整A1。A2–A5未开始；没有commit/push，没有请求其它模型。**

- 正式入口 `bash tests/run_all.sh --milestone a1 --timeout 2400` 第3轮 **退出1**，`work/tests/a1-20261018-181442-654524/result.json`：passed=false、full_a1_passed=false、steps=205，错误 `Stamper pulse did not produce measurable partial opponent damage`。命令总日志 `work/a1/acceptance-3d-duel.log`，原生会话181442-679357。原始逐STEP、主机日志、两份sample和命令结果均保留；整理证据 `work/a1/3d-duel-evidence.json`。
- 已通过的本轮窄证据：连续参考 / 暂停脚本均 **1.5秒HUD时间**，自身位移 **0.360044503403 /0.360044500001**，中立对端均0；所有已记录ACK严格满足客体纳秒=累计present/60。此前短诊断845present→14.083328秒、80步通过的原始证据仍保留。没有再次发生首步死锁或空闲等待误杀。
- 裁判准备在有界导航后完成落地：0号约 **(17.362408,0,17.268560)**，1号约 **(11.928095,3.000002,8.402325)**。选择高处1号为射击者，低处0号为目标；两端都先恢复HP=1且存活。按目前相机字段解释，yaw误差 **0.01757336rad**、pitch模型误差 **1.17e-8**；这些只是观测包与自写几何模型的一致性，**尚未独立验证该pitch标量到世界射线的转换，也没有验证发射点/弹体射线对齐目标**。
- 实际脚本向1号发送 **1帧ZR +7/7/15/15/15帧中立**，共60present；连续参考全部命令先排队，再按顺序读取每个ACK，没有逐步策略停顿。1号墨量 **1→0.956356585**，随后恢复到 **0.979689896**，说明射击输入确有消耗响应；未将耗墨本身当作命中。0号所有六次ACK **HP=1**，其position_sample_frame持续更新，位置保持静止，观测不是整段陈旧缓存。HUD时间双方均走过约1秒。
- 因连续参考未产生真实部分损伤，测试在第一次命中验证就失败，**未执行暂停版伤害脚本**，不能比较伤害一致性，不能报告“伤害相同=0”并签收。没有放宽损伤门槛、改写HP或位置、增加任意隐式攻击来改判通过。
- **假设，均未证实**：①高差/台沿或其它地图几何遮挡了实际弹体；②包内pitch标量的世界角转换、相机原点与枪口原点之间的几何尚未标定，当前模型“对准”不能代表游戏实际射线对准；③单次横挥弹体/网络命中时序尚未用独立弹体或伤害事件探针闭环。局部Params中HitDamage=350与动画第9帧出弹是静态事实，无法排除上述问题。下一步需要独立可视/原生射线或伤害事件校准证据，不能继续仅按自写模型误差调参猜命中。
- 两个宿主在失败时仍存活，清理前macOS sample均 **退出0**，随后均 **优雅退出完成**，无CRASH/FATAL；所属dmhost/air/test_a1进程已退出。247次资源采样pressure最大1、新swapout **0**、footprint合计峰值 **7289MiB**。原件/参考档SHA256均仍为 `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。
- `work/a1/acceptance-3d-duel-code.sha256` 在结束后逐项复核一致。A1已接入自动入口但当前真实失败，源码、测试、文档与生成补丁保持未提交；游戏原始数据/参数JSON/画面/原始栈均只在忽略的work。M6默认仍为realtime，本轮新增预排队协议回归25项通过；未声称本轮重新完成了M6整局验收。

## 2026-10-18：指挥方修订 A1 签收范围，恢复推进

- 本节覆盖上一节“命中阻塞 A1”的状态：伤害打不中归属 A4 的 `aim_at`，不再阻塞 A1。A1 按 fixed60 精确计时 + 连续/暂停移动一致验收；受控默认改为 fixed60，realtime 作为可选旧模式保留。
- GOAL / README / 自动测试同步该范围；原未命中的瞄准诊断保留在 `tests/diagnose_stamper_aim.py`，不作为 A1 门槛。**待办：A4 完成 aim_at 后补测 A1 伤害一致性，双方放平地近距离正对，排除台沿遮挡。** 未声称伤害已通过。
- A2 按新的两项实测要求推进：同距离潜游用时、满罐原地对空挥刀次数；A3 可见性仍须裁判真值/策略裁剪两个接口，策略进程只接策略版；A5 示例仅直冲/占高台。
- 新默认的正式入口即将重跑；只有正式结果与清理均通过后才记录 A1 PASS 并 commit/push。

### A1 最终签收 PASS（指挥方修订范围）

**A1 PASS：fixed60 已成为受控默认；伤害一致性明确待 A4 的 aim_at 完成后补测。** 本节覆盖此前“A1 未签收/停止”的状态，不更改历史失败产物。

- 正式命令 `bash tests/run_all.sh --milestone a1 --timeout 2400` **退出0**。新结果 `work/tests/a1-20261018-183019-181472/result.json`：passed=true、full_a1_passed=true、errors=[]、50步；damage_passed=null、damage_status=deferred_to_a4_aim_at。总日志 `work/a1/acceptance-final-scope.log`，双端会话 `work/tests/m6-2p-20261018-183019-203310/`。
- 测试未显式传 clock_mode，断言 Python 环境与宿主会话默认均为fixed60。所有端、所有ACK的客体时间差严格等于 `floor(累计present*1e9/60)`，混合1/7/31/21帧脚本的原生Timer采样换算符合0.04秒容差。
- 相同90帧移动/稳定脚本：连续参考位移 **0.360044503683226**，逐步暂停位移 **0.3600445000013895**（差约3.68e-9）；两者HUD均 **1.5秒**，中立对端位移均 **0**。连续参考预先排队全部命令；暂停版每段有0.2秒真实策略等待。旧realtime仍有已记录的HUD漂移，保留可选但不宣称它是60Hz。
- 时钟组件fixed60 **10804**、旧共享 **13** / 手动 **5**、短睡眠 **3**、空闲事件有界轮询 / 条件变量回归、传输 **25**、GPU **148** / headless **152**、NVN **79**、HID **73** / RL **11**、LDN frontend **10** / air **59** 与资源规则全部通过。
- 两宿主均 **优雅退出0**，无CRASH/FATAL。206次资源采样pressure最大 **1**，新增swapout **0**，footprint合计峰值 **7313MiB**；原件及参考档SHA256仍为 `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。受测宿主/Python/入口冻结清单 `work/a1/acceptance-final-scope-code.sha256` 复核全通过。
- 待办保留在GOAL的A1/A4：平地、近距离正对目标，用公共aim_at排除瞄准/台沿问题后，对比连续/暂停真实伤害；本次签收不包含该证据。只提交本项目源码、测试、文档和可重放补丁；游戏数据/画面/参数原件/运行栈不入库。下一步A2。

## 2026-10-18：A1 已推送，A2 配装进行中（未签收）

- A1 commit `9cdf157f7b698a8860d33244c0a1b6e976cc9658` 已 push；`git ls-remote origin refs/heads/main` 与本地HEAD相同。
- A2 新增每端独立 `loadouts`（头/衣/鞋各主技能+3副技能）、合法技能名称与专属槽位校验。宿主在本地玩家装备参数构造返回点覆写运行时字段，不改存档、目录或对端参数；挂点受已验证build ID及原指令签名约束。
- 原生候选布局来自本地反汇编：每件装备主技能+0x84，副技能环形容器+0x88/+0x90/+0x94/+0x98，元素步长0x78、枚举字段+0x70；需要接下来真实构造读回与效果测试闭环，组件成功不能代替实机效果。
- `tests/test_a2_components.py` 通过3组测试（含12种原生进程场景）：格式/专属槽位、无覆写/只读survey、完整参数及相邻字段、未知build/缺挂点/容器异常/非法输入拒绝。正式入口 `tests/run_all.sh --milestone a2` 已接入，尚未实机签收。
- 实测方案：双端均8000，基线全none；实验配装头19AP游速、衣鞋38AP主武器墨效。原地抬头按节奏对空横挥统计真实墨量下降次数；涂前方通道后潜游同样3个坐标单位、按present计时，随后交换两端配装再测。均不依赖命中瞄准；测量原始记录只保留work。

### A2 当前新卡点：配装构造读回成功，但准备完成后原生主动断房（停止，未签收）

**按“真正的新卡点才停下”规则，停止在此。A1 已 PASS 并推送；A2 未 PASS，A3–A5 未开始。没有请求其它模型；A2 代码/测试/文档保留未提交改动。**

- 正式入口 `bash tests/run_all.sh --milestone a2 --timeout 2400` 的组件部分全部通过；实机会话 `work/tests/m6-2p-20261018-184218-537200/`。两端正常创建/加入同一房间，空气服务session `87e892a037e207628b83220613561849`；先前A1相同建房/准备路线成功，新的区别是本轮启用了独立配装及其构造挂点，尚未做禁用配装的消融复现，因此不把相关性写成已定位根因。
- 构造读回：0号三件装备ID **2013/5023/2004**，主技能/三个副技能均0；1号头主副均5（游速）、衣鞋主副均1（主武器墨效）。两端每件count=3、override=1；读取的是活体本地kit字段，不是Python配置回显。两端均8000/fixed60；**此证据仅证明构造字段读回，不证明实际技能效果或最终战斗参数。**
- 新现象：air在约370秒仍state3/5、nodes2，双向传输无丢包；随后1号从 `main+0x9554f4` 调用 `h_ldn_Disc`（reason=1），再CloseSta；0号看到nodes1，从 `main+0x9553c4` 调用Destroy（reason=3），再CloseAp。断开前最近资源帧约主机13800/客机9300；断开后两端继续正常出帧，**均没有InGame PROBE或RL_ATTACH，0个STEP**。无CRASH/FATAL；不是fixed60接管后的等待环，因为本轮根本未接管。
- 可能原因尚未验证：①全none主技能基线/补满副槽是否违反游戏原生kit校验；②枚举字段/槽位数量覆写后是否还需同步派生元数据或网络序列化状态；③原有准备路线对新增构造耗时/时序是否敏感。尚不能把它归因于瞄准、技能曲线或本地网络数据丢失。未用修改速度/耗墨倍率绕过原生技能，未把构造读回冒充效果。
- 确认已经断房、宿主仍在运行后，在清理前对PID **37124 /51416** 分别执行macOS sample（1秒采样、10秒调用上限），**均退出0**。原始栈、断开上下文、配置/读回摘要在 `work/a2/startup-blocker/`，其中 `evidence.json` / `samples.json` 可复查。
- 给本轮唯一harness发SIGINT使其保存失败结果并清理，不等待2400秒空转。正式入口退出 **1**，`work/tests/a2-20261018-184218-503410/result.json`：passed=false/full_a2_passed=false、rounds=[]、KeyboardInterrupt；traceback停在 `Session.start()` 等待全端InGame。**这是发现原生断房后的主动停止，不是将KeyboardInterrupt当原始故障，也不是STEP超时。** 该结果脚本的事后sample发生在reset已清理之后，诊断证据以之前成功采集的startup-blocker样本为准。
- 两宿主随后均优雅退出 **0**，本轮harness/dmhost已退出、air已由close回收。244次资源采样pressure最大 **1**，新增swapout **0**，footprint合计峰值 **6670MiB**。宿主/覆写源码/Python/正式入口冻结清单 `work/a2/acceptance-code.sha256` 复核全部一致；原件与参考档SHA256仍为 `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。
- 因未进入对局，**满罐挥刀次数、同距离潜游用时、交换配装的第二轮均未测量**。A2效果没有通过，不进入A3。新源码和重放补丁留供下一步排查；所有原始产物、游戏数据/画面/参数/线程栈只在忽略的work，无新commit/push。

## 2026-10-18：按指挥方恢复 A2，先做开局二分对照

- 按 a) 双端关闭覆写（连续两次新会话）、b) 分别仅主机/仅客机启用、c) 双端原技能原样写回的顺序定位。均保持fixed60默认、8000、相同建房/地图/分队/准备流程，不先改网络校验或战斗倍率。
- 新增 `tests/probe_a2_startup.py`，每次到InGame后用1/7/31/15/60/120/300帧STEP检查固定时间；开局流程中若原生房间关闭立即失败、清理前逐端sample，不再断房后一直等待总超时。该诊断始终full_a2_passed=false，不能替代效果验收。
- c) 的 `DM_GEAR=original` 诊断模式只把每件原主技能、当前有效副技能写回原值，保留原ID、rarity、count、begin、锁槽及未激活元素；对整个0x208字节对象做前后逐字节比较。不是把主/副技能复制后仍强行补满槽位的伪原样对照。组件已补上原样写回测试通过。
- 核对代码：fixed60在 `dm_guest_clock_share()` 才激活，该调用发生在Python连接RL socket之后；协调器只在全端InGame后连接。因此现有实现已经把fixed60接管置于InGame之后，仍需a)实机重复排除回归。
- a) 命令 `.venv/bin/python tests/probe_a2_startup.py --case off --repeats 2`，总日志 `work/a2/bisection/off.log`；首个会话 `work/tests/m6-2p-20261018-185449-811159/`，结果待定。所有原始记录、线程栈和游戏产物仍只留work。

### A2 对照 a) 完成：双端关闭覆写，连续两次开局通过

- `work/tests/a2-startup-off-20261018-185449-775877/result.json`：probe_completed=true、errors=[]，两次独立会话均InGame并完成7个STEP（1/7/31/15/60/120/300），所有端客体时间与累计帧预算精确匹配。
- 两个会话分别 `m6-2p-20261018-185449-811159` / `m6-2p-20261018-190145-399948`。两端均无DM_GEAR、无SPL3_GEAR callback；保留新重写挂点但不注册覆写处理。日志顺序均为InGame PROBE → RL_ATTACH → RL_FRAME_BEGIN，固定时钟没有提前作用于大厅/加载阶段。
- 四宿主均优雅退出，无新增swapout、pressure最大1。a) 在本轮重复两次稳定成功；没有据此宣称消除了所有偶发时序问题。已继续 b) 仅主机启用旧覆写，之后仅客机、双端原样写回。
- 另一次只读核对：副技能native setter main+0x357780c只有LDR/STR/RET，未发现额外缓存更新；此前“绕过setter导致缓存不同”的假设不作为已确认根因。

### A2 对照 b-host) 完成：仅主机旧覆写也会断房

- `work/tests/a2-startup-host_only-20261018-190827-384381/result.json`：probe_completed=false、InGame=false、0 STEP；运行时监控捕获原生房间关闭，立即sample和清理，不是总超时后人为中断。会话 `m6-2p-20261018-190827-407780`，日志 `work/a2/bisection/host_only.log`。
- 主机按上一轮基线覆写全none、三副槽；客机完全未启用配装覆写。准备时再次发生客机Disconnect/主机Destroy；因此不是必须双端同时覆写才触发。关闭覆写的两个成功对照保持有效。
- 已查看本轮本地截图：分队/地图仍为Scorch Gorge，准备阶段主机显示工作刮水刀、客机尚为问号；未把截图当作技能生效证明。截图与原始线程栈均只留work。
- 尚需仅客机实验配装、双端原技能原样写回对照，不能提前判定是全none主技能、槽位元数据还是其它一致性校验。已继续这两组，受测宿主保持冻结。

### A2 对照 b-guest) 完成：仅客机游速/墨效配装成功开局

- `work/tests/a2-startup-guest_only-20261018-191432-046563/result.json`：probe_completed=true、errors=[]、InGame=true、7个STEP精确计时通过。会话 `m6-2p-20261018-191432-073251`，总日志 `work/a2/bisection/guest_only.log`。
- 主机未覆写；客机头主副均5、衣鞋主副均1，三件count=3。实际成功说明“任意技能组合变化都必然被网络拒绝”不成立；尚未测到实际游速/耗墨效果，也不能只凭这组就确定全none是唯一原因。已继续双端原技能逐字节不变写回的c)对照。

### A2 对照 c) 完成：双端原样写回开局成功

- `work/tests/a2-startup-original-20261018-192031-080856/result.json`：probe_completed=true、errors=[]、双端InGame、7个STEP精确计时通过。会话 `m6-2p-20261018-192031-101982`，总日志 `work/a2/bisection/original.log`。
- 两端原装备ID2013/5023/2004；头主10、副6/6/12，衣主22、副1/1/1，鞋主25、副5/1/5，原来count已是3。主/有效副技能原值写回后整个装备对象0x208字节严格不变。不是“挂点存在/写内存本身就必定断线”。
- 三组指定对照已完成。为分离主技能None与空副槽的影响，追加旧后端最小对照：主机只把三个主技能由0改为合法10，九个副技能仍0，rarity/count和其它旧覆写行为不变；客机不覆写。会话 `m6-2p-20261018-192652-110590`，日志 `work/a2/bisection/host_main_valid.log`，结果待定。
- 在指定对照完成后开始准备修复候选，暂存 `work/a2/fix-candidate/`，不更换正在追加对照中使用的冻结宿主。生产路线计划：原生选中ID已经在拥有表查找成功后，给装备构造函数提供该合法拥有条目的技能读取视图，由游戏正常构造完整装备参数；拒绝主技能None。技能名称None仅可留作空副槽，不再用作非法空主技能基线。尚未实机验收候选。

### A2 追加最小对照完成：只替换空主技能仍失败，继续修复原生构造路径

- `work/tests/a2-startup-host_main_valid-20261018-192652-086900/result.json`：InGame=false、0 STEP，原生主动断房，sample与清理完成。只有三个主技能由0改为10，其余九个副槽仍0，旧后端rarity/count不变。因此**不能把根因简化为“主技能None是唯一问题”**，尚有空副槽/装备完整性和构造后改值时序等可能性。
- 指定三组对照和该追加对照均已结束；旧宿主、旧覆写源码和旧main重写文件归档在忽略目录 `work/a2/bisection/before-fix/`。补丁/源码修复开始后不再声称其源码哈希仍与旧对照相同；旧二进制及原始证据可复核。
- 修复采用原生拥有条目读取视图：在成功查到该已拥有装备、调用装备参数复制之前，提供线程局部的只读条目副本和三个技能，由游戏的完整复制/枚举setter正常构造。实际拥有表/存档对象、装备ID和经验保持原样，构造后只读回校验，不再用旧后写字段路径作为生产默认。旧路径仅留显式DM_GEAR_LEGACY诊断复现开关。
- 本阶段配置要求所有声明的主/副槽均填合法技能，None仅保留诊断枚举。验效基线改为完整快速超级跳跃配装（测试不跳跃/不死亡），游速及墨效相关AP均为0；实验仍头19AP游速、衣鞋38AP主武器墨效。没有再用全none或空副槽作为合法装备基线。
- 验效脚本补上出生点落差后的平坦通道准备，测量潜游前进3→9单位的同距离6单位，用原生位置采样帧插值，并检查直线/高度及实际潜游速度；挥刀计数在首次缺墨触发时停止，避免自然回墨之后再挥造成虚增。候选尚待实机运行。

### A2 最终签收 PASS：正常原生装备构造、完整耗墨次数与潜游用时，交换配装闭环

**A2 PASS。** 本节覆盖此前“A2未签收/停止”的状态；A1签收不变，下一步A3。没有请求其它模型。

- 正式命令 `bash tests/run_all.sh --milestone a2 --timeout 2400` **退出0**；`work/tests/a2-20261018-193938-145424/result.json`：passed=true/full_a2_passed=true、errors=[]、两轮各 **167 STEP**。会话为 `m6-2p-20261018-193938-187652` / `m6-2p-20261018-194646-809032`；总日志 `work/a2/acceptance-owned-read.log`。
- 两端均8000、fixed60默认。每件装备12个技能槽按进程独立声明并经原生复制/setter正常构造，所有主副技能读回吻合，均为 `backend=owned_read`。ID保留真实已拥有的2013/5023/2004，读取视图不改拥有表/存档对象、经验或对端kit；线程局部副本仅供已验证的同步原生复制函数读取。没有注入速度/耗墨倍率。
- **墨效：** 两轮完整耗墨横挥均为基线 **19**、实验 **31**，换边后由另一端取得同样结果；挥刀段四端位置漂移均 **0**。正常单次耗墨中位数 **0.051999986 → 0.031779587**；完整扣墨累计 **0.987999812 /0.985167235**，余墨分别 **0.012000188 /0.014832765**，不足再完成一次普通耗墨。
- **计数口径透明修订：** 正式实测原始结果的counts=21/33是正扣墨触发数，含罐底两次小额扣墨，原始JSON没有改写。签收完整耗墨次数以 `work/a2/acceptance-owned-read-metrics-final.json` 自动复核的19/31为准。实测完成并核对冻结清单后，仅收紧测试的统计/断言，不改变动作、帧预算、配装或宿主；新增 `tests/a2_metrics.py` 对同一冻结原始history重算，双轮通过。未来a2入口默认使用该严格口径，另留positive_deductions记录尾段；增加了“余墨不足/之后回墨不得增加满罐次数”的回归。没有把旧JSON的21/33伪改成19/31，也没有声称统计修订后重新开过新局。
- **游速：** 在出生点落差后平坦通道，测前进3→9的同距离 **6单位**；按位置包自身采样帧插值。首轮基线 **31.860587帧 /0.531010秒**，实验 **28.085449帧 /0.468091秒**（快11.85%）；换边后基线 **32.217042帧 /0.536951秒**，实验 **27.948629帧 /0.465810秒**（快13.25%）。平坦/直线及实际潜游速度门槛通过，优势随配装而非出生侧变化。测试不跳跃/不死亡，完整快速超级跳跃基线的相关游速/墨效AP为0；实验游速19AP、墨效38AP。
- 四宿主全部 **优雅退出0**，无CRASH/FATAL/GPU错误；两轮资源采样 **201/205** 次，pressure最大 **1**，新增swapout均 **0**，footprint合计峰值 **8723/8793MiB**。参考档/原件SHA256仍为 `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。`work/a2/acceptance-owned-read-code.sha256` 在统计修订前逐项核对一致；原受测driver另存 `work/a2/acceptance-owned-read-tested-driver.py`，用于区分随后纯统计变化。
- 入口组件时钟10804/13/5、短睡眠/空闲轮询/条件变量、传输25、GPU148/headless152、NVN79、HID73/RL11、LDN frontend10/air59与资源规则通过；统计修订后配装组件 **4组**（含原生拥有读取隔离/构造读回/拒绝非法配置及回墨计数回归）、同一原生双轮数据的严格复核、传输25再次通过。补丁反向应用和源码空白检查通过。
- **根因证据边界：** a)关闭覆写连续两次成功、b-host旧路径全none失败、b-guest完整游速/墨效组合成功、c)原样写回成功，追加“主合法/九副槽none”仍失败，已排除fixed60大厅接管回归及“单纯挂点/相同值写回必断线”。具体原生拒绝分支尚未逐条指认，不能归结为单一空主技能；修复同时约束完整合法配装并改为拥有条目读取→原生正常构造，两轮正式验效闭环。旧后写字段只留显式LEGACY诊断复现，不作为生产默认。
- 本次仅提交本项目源码、测试、文档和补丁；原始记录、NSO/RomFS/shader、参数表、画面、线程栈、旧二进制均只在忽略的work。伤害一致性仍按GOAL留待A4 aim_at，不挪进A2。

## 2026-10-18：A2 已推送，A3 原生状态与信息边界诊断（未签收）

- A2 commit `42e9fab42d3c80955a14b952ca2bca418badb0f6` 已 push；推送后远端main与本地HEAD核对相同。A1/A2已完成；当前只推进A3，A4/A5尚未开始。以下A3组件与诊断均不能替代正式里程碑验收，也没有新commit/push。
- `arena/referee.py` 与 `arena/policy.py` 分别定义私有裁判快照和独立策略记录；后者没有referee导入或原始socket访问器。`encode_policy`只接受确切的PolicyObservation类型，并重建固定白名单，拒绝直接序列化裁判快照/任意dict。`arena/visibility.py`只在观察者、目标、比赛、当前帧、目标采样帧一致，且FOV/射线无遮挡为已确认真、目标已确认未潜墨时给坐标；未知/过期全部隐藏。隐藏时不提供当前朝向/采样时间/隐藏原因，HP/墨量/私有墨图/击倒归属不进敌方策略记录；只保留此前真正可见时的最后位置与目击帧。
- `.venv/bin/python tests/test_a3_components.py` 最终 **8项通过**，含100组隐藏敌人位置/HP/墨量/私有存活/墨图/归属变异的逐字节输出不变检查、缺失/过期/错端/错局视线证据、潜墨未知、最后目击隔离及拒绝传裁判对象。`arena/native_referee.py`私有合并各端已验证own字段，并换算不同启动帧偏移；策略公共存活只读观察者本端HUD，不使用对端可能提前更新的私有alive。**它们只是接口/适配组件；尚无原生visibility witness后端和实际策略子进程接入，不能声称“策略进程隔离已完成”或A3通过。** 私有实时墨图/击倒事件尚未知时为None，不填0/空列表冒充实测。
- 原生潜墨对照：`tests/probe_a3_fields.py`，结果 `work/tests/a3-fields-20261018-201431-758170/result.json`（44步、只测0号）与 `work/tests/a3-fields-20261018-202458-140416/result.json`（58步、分别控制双方），均probe_completed=true/errors=[]/full_a3_passed=false。全程fixed60、两端8000、完整quick_super_jump控制配装；对照未涂地按ZL→涂前方并走入墨带→按ZL→起跳→落地。原始状态包/128×72截图仅留work，逐字段汇总 `work/a3/fields-evidence.json` / `fields-both-evidence.json`。
- **已证伪的简化：** 包+0xf8的0/1形态标签在“未涂地鱿鱼、墨内鱿鱼、空中鱿鱼”都是0；Squid子状态+0xe8/+0xec也没有区分这三个场景。不能将form==0当潜墨。包+0x94在双方未涂地均4、走入各自墨带均0、起跳均5；双方都为0，排除“0=固定绝对队伍色”的直接解释，仍需敌墨/墙面与原生写入语义校验后才能推广。当前不把这些候选字节作为策略字段发布。
- 两轮有效字段诊断的四宿主均经Session.close检查优雅退出，未出现CRASH/FATAL；资源采样178/188次，pressure最大1、新swapout均0，footprint合计峰值8298/7694MiB；close检查原件/参考档hash仍未变。此前一次201021诊断在0 STEP、未开始测量时主动停止以补上“走进墨带”的必要动作；原KeyboardInterrupt结果未改写，说明在 `work/a3/probe-preparation-revision.json`，不计游戏故障或有效测量。
- 碰撞来源取得新实证：本机 `Pack/Actor/Fld_Yunohana.pack.zs` / `Fld_District00.pack.zs` / `Fld_Yagara.pack.zs` 内各有 `Phive/Shape/Dcc/*.bphsh`。用忽略目录内的公开PhiveConverter固定提交 `03faf4be678a42d18b1786bef6321b52dfbcd10b` 转成三角面及材质组；代码只补macOS编译所需_BitScanReverse兼容头，没有重建/改写游戏碰撞。原bphsh、OBJ、材质JSON与克隆工具都只在 `work/a3/`。
- 与本机11.3.0 `Phive/Config/PhiveConfig.byml.zs` 新鲜核对：39个material名和60个entity+sublayer碰撞层顺序与转换器一致，Sight为bit41。材质标签两处命名/保留位差异（bit34及Asplalt/Asphalt拼写）单独记录，未把外部表整体不加核对视为原生真值；`work/a3/collision-config-check.json`。Yunohana主地形竖直射线在(-23.9,63.916)命中y=7.5，在(-23.9,71.433)命中y=10.5，与实机平地/出生落差吻合。**仍未组合Scene/Banc全部道具、变换和动态物体，主地形射线不等于完整遮挡验收。**
- 本轮另行定位原生相机世界原点/朝向/投影：包内身体forward与平面camera向量不足以证明遮挡射线。已找到PlayerCamera类型/构造/vtable和一个读取eye/at/FOV候选的函数main+0x28f9e8c；新增 `--camera-probe` 对三个原指令签名逐字节核对后，仅用既有DM_PROBE诊断读取，叶函数确认不用x16，避免破坏探针借用寄存器。相机诊断结果见下一节；未猜相机高度/FOV生产visibility witness。

### A3 当前新卡点：相机候选路径局内不调用，实时视线证据不可用（停止，未签收）

**按“真正的新卡点才停下”规则，在此停止。A2已PASS、commit/push并核对远端；A3未PASS，A4/A5未开始，没有请求其它模型。A3源码、接口测试和文档保留未提交，不创建未完成里程碑的签收commit。**

- 复现命令 `.venv/bin/python tests/probe_a3_fields.py --owners player_0 --camera-probe` **退出0仅表示诊断完成**；`work/tests/a3-fields-20261018-203610-696597/result.json`：probe_completed=true/errors=[]，**full_a3_passed=false**、44步。原生会话 `work/tests/m6-2p-20261018-203610-718141`，日志 `work/a3/fields-camera-probe.log`；结束后 `work/a3/fields-camera-code.sha256` 的宿主、诊断driver、rewritten main逐项一致。
- 两端均正常触发InGame，完成暖机、离开出生台、俯视、涂地、走入墨带、潜墨、起跳/落地。own包分别 **338/339** 次，原有位置/HP/墨量有持续采样；各端日志明确记录三个探针已安装，原指令为 `f9403008/2d4e0c02/bd407804`。但 **main+0x28f9e8c /0x28f9e90 /0x28f9e94 全程（包括局内）均0命中**，没有取得一份可标定的相机世界原点、at或FOV样本。原始零命中没有用默认值、身体forward或自拟眼高替代。
- 这是新的A3原生可见性读取问题；不是A2再次断房，也不是A1旧伤害瞄准卡点。仅有三张主地形和own packet位置，无法证明“敌人处于玩家真实相机画面内且射线无遮挡”，尤其第三人称相机与玩家脚点在台沿/掩体旁可能位于不同遮挡侧。因此当前投影器在未知证据下隐藏全部敌人，**这能避免泄漏，但不能当作A3正确显示/遮挡/潜墨验收。**
- 自动整理 `.venv/bin/python tests/analyze_a3_fields.py work/tests/a3-fields-20261018-203610-696597/result.json`，完整证据 `.../candidate-fields.json`、摘要 `work/a3/camera-candidate-summary.json`；其中installed=true、ingame_seen=true与total=0同时记录，区别于前两轮未启用相机探针的0命中。另用 `tests/probe_a3_replay.py` 重放双方字段诊断58个真实屏障：114份有效私有位置、114份HP、228条观察者本端HUD记录，生成116份策略白名单输出；visible敌人数0、full_a3_passed=false，未把安全隐藏误报成功。真实相机诊断44步亦完成适配重放，原结果未改写。
- **假设，均未证实：** ①main+0x28f9e8c属于特殊视图/预览/其它UI相机读取，通常占地局内不走该分支；静态只找到main+0x3e6f6c4一处直接调用，不能据类型邻近就认定为每帧战斗相机。②真实view/projection可能在PlayerCamera另一更新回调或渲染常量提交点消费，需要从“本帧实际用于画面”的矩阵反向校验，而不是保存构造时指针后任意解引用。③Scene/Banc道具/变换/动态碰撞尚未完整组合，即便主地形射线命中高度正确，也不足以宣称完整LOS。这些是假设/后续定位方向，不是已经修复或测试通过的事实。
- A3其余签收义务仍明确保留：潜墨候选需敌墨/墙面/原生语义验证；实时墨图需原生采样而非累计射击轨迹/最终比分推算；击倒归属需真实victim/attacker/weapon/time事件而非HUD Down计数。已定位PaintTextureData/ColPaintMgr及TroubleDie/PlayerDeadReason若干静态候选，但未形成实机读回，不给策略或裁判填伪数据。实际策略子进程的通道/隔离和原生“可见→遮挡→再见/潜墨”场景均未验收；a3正式run_all门槛尚未接入，接口组件通过不构成里程碑完成。
- 本次两宿主优雅退出0，无CRASH/FATAL；175次资源采样pressure最大1、新swapout0、footprint合计峰值8402MiB。Session.close核对原件/参考档hash仍为既定值；额外SHA256核对均为 `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。没有修改A2已签收的宿主源码/二进制或重新生成游戏数据；所有原生内存字节、游戏画面、碰撞资产、栈与转换器均只留忽略的work。

## 2026-10-18：按指挥方恢复 A3，采用几何近似可见性

- 本节覆盖上一节相机读取停止线：指挥方明确放弃游戏相机探针，允许固定人形/乌贼眼高、身体朝向水平FOV与距离上限、脚/腰/头线段碰撞测试，任一点无遮挡即可见。静止潜墨隐藏，移动溅墨/跳起可见；以几类实机截图判断“大致像人眼”，无需像素级投影。已同步GOAL。旧相机探针driver冻结保留在忽略的 `work/a3/camera-probe-tested-driver.py`，开发入口删除该路线，不再将其作为A3前置。
- `arena/geometry.py` 参数化近似默认人形眼高1.1、乌贼0.25、身体采样0.12/0.7/1.3、水平半视角60°、距离100、表面epsilon0.015；等待实机截图标定。射线双面、限定线段端点，忽略Sight-disabled材质。`tools/stage_collision.py` 从本地Scene/Banc组合Cmn/Pnt静态地形与道具的SRT，输出只在work；三图6757/4353/4774个Sight三角面、16/11/28实例。District单轨道具和Yagara漂浮装饰未含内嵌Dcc形状，manifest逐项列出；这是已授权静态近似的边界，不声称动态遮挡精确。
- 原生own encoder新增裁判用referee_motion，读取已双端诊断的形态及接触码0/4/5，未知码仍-1；字段只加原始协调器metadata，不进入RL观测space。私有适配器组合形态/接触、样本间位移判断静止潜墨/移动溅墨，支持ninja_squid配置抑制溅墨；空中接触5按跳起例外处理。不是将ZL按钮直接当潜墨。
- `arena/process.py` /独立 `policy_worker.py` 只通过固定白名单JSON交给act(obs)，close_fds、清除DM环境、macOS sandbox禁止读取用户/临时私有状态（仅自身策略、解释器、公共技能例外）、禁止网络含AF_UNIX及fork。实际子进程测试2项通过：拒绝裁判类型；裁判文件/对方策略/原始socket读取连接均拒绝；忙循环在0.1秒上限内终止回收。普通OS运行库可读，未声称防御OS漏洞。
- 几何组件4项、既有边界组件8项通过；原生传输新增motion隔离/读回测试后26项通过。组件不替代实机场景签收。正在运行 `tests/probe_a3_visibility.py`（始终full_a3_passed=false），采用双端8000/fixed60、原生状态+几何判定+128×72及原生720p定帧截图，场景结果待定；冻结清单 `work/a3/geometric-probe-code.sha256`。

### A3 几何可见性与白名单通道：子项实机完成，完整 A3 未签收

- 最后一次场景命令 `.venv/bin/python tests/probe_a3_visibility.py` **退出0**，`work/tests/a3-visibility-20261018-212315-404190/result.json`：probe_completed=true/errors=[]、**356 STEP**，full_a3_passed仍false（该脚本只验证可见性诊断子项）。双端8000、fixed60、完整quick_super_jump配装；会话 `m6-2p-20261018-212317-669707`，总日志 `work/a3/geometric-visibility-third.log`。
- 保持同一套参数：人形眼高1.1、乌贼眼高0.25，脚/腰/头0.12/0.7/1.3，半视角60°、距离100。七个定帧场景 **开阔正对=true、乌贼观察者开阔=true、背对=false、转回=true、静止潜墨=false、隔墙=false、隔高台=false**。全部生成原生截图并逐张查看，结果与本次“大致像人眼”的几何规则一致；没有把它写成游戏相机的像素级还原，也没有声明三图都完成同样的实机标定。截图与SHA256/逐项检查记录只在 `work/a3/geometric-visual-review.json`，是本会话截图检查，不冒称用户人工签字。
- 额外跳起/移动溅墨均判为可见，并查看了直接来自该帧观测的截图。跳起目标位置y约3.5743、form_squid=true、submerged=false；移动时y=3、submerged=true、motion_visible=true。静止潜墨时只见墨带，不提供目标坐标；截图、状态原件和策略输出分别保留。归一化时刻来自各端独立绝对帧原点，未误把相差4740左右的宿主启动帧直接当共同比赛时间。
- `arena/referee_api.py` 提供私有 `state()` 与独立 `policy_observation(observer)`；只有后者的PolicyObservation能进入PolicyProcess。原始真值保留HP/墨量等，敌方白名单没有这些字段；隐藏时无当前坐标/朝向/采样帧/隐藏原因，仅留曾经可见时最后位置与目击时刻。公共存活仍只读观察者本端HUD，自端或目标采样过期都会隐藏。
- `.venv/bin/python tests/probe_a3_policy_replay.py work/tests/a3-visibility-20261018-212315-404190/result.json`：七个真实场景状态经实际sandbox子进程全部回放符合预期，裁判对象类型拒绝；结果 `.../policy-subprocess-replay.json`。这证明实际原生状态→私有适配→几何过滤→白名单JSON→独立进程链路；**未宣称已运行A5策略控制整局**。子进程文件/对手源码/AF_UNIX拒绝与超时回收由实际生产worker测试覆盖。
- 准备过程保留了两次真实失败：首轮405步在半单位拐角摩擦，A*点位缺少角色余量而到达240步上限；增加抬高邻格净空约束后，第二轮307步走完开阔/背对/隔墙/高台，但先做3单位落差再返回，准备网格无返程路径。随后把单向落差场景放最后，第三轮356步走完全部几何场景。这些是场景准备问题，**不是fixed60等待死锁/原生断线，不作为新的停止原因**。前两轮原JSON/线程栈、受测driver/navigation副本均在work，未篡改为通过。首轮定帧截图起点余数差10帧已在 `geometric-screenshot-map-first.json` 单独记录；最终轮调正起点，七张native_image路径都真实存在。

### A3 当前新卡点：实时涂地图的纹理与地图坐标关系未闭环（停止，未签收）

**按“真正的新卡点才停下”规则，在此停止。旧相机停止线已被新几何方案跨过；本次停止原因是剩余A3状态读取，尤其实时涂地图。A1/A2签收和远端commit不变，A3未签收、不commit/push，A4/A5未开始；没有请求其它模型。**

- 实测一：`.venv/bin/python tests/probe_a3_paint_events.py` 退出0仅表示诊断完成，`work/tests/a3-paint-events-20261018-210443-372117/result.json`，**76 STEP**，会话 `m6-2p-20261018-210443-397072`。已真实涂地、进入己墨，并在第17000个原生present导出本帧 **29** 个颜色绘制目标。存在一个1600×1600的红通道墨迹目标 `player-0/paint-targets/target-2819000.png`，红像素bbox约 **[62,1481]–[89,1553]**，另一个同尺寸目标全零。源图/目标标签/尺寸统计只在work；没有把“红色=哪一队”的假设直接发为已验证网格。
- 当前不能从这些目标可靠给出“地图某格的墨色”：按主碰撞包AABB直接线性对应世界XZ时，已知在x≈-23.9、z≈60–63附近的落墨应落在纹理x≈480附近，实际墨迹x在62–89；简单候选对应不成立。**尚不能确定是UV打包、独立paint bounds/缩放、分面投影还是其它映射**，也没有识别可涂表面有效域。把未解释的零像素一律当中立地面，会混淆域外/未涂/不可涂，不能签收。
- 实测二：没有止步于该纹理候选，新增协调器专用 `Client.send_referee_map_pulse()`，用现有原生X位（mask4）打开公开地图，不改变策略六键空间、不改客体代码。`.venv/bin/python tests/probe_a3_minimap.py` **29 STEP、probe_completed=true/errors=[]**，会话 `m6-2p-20261018-211125-067050`；前后原生图在 `native-15090.png /native-15570.png`，诊断 `work/tests/a3-minimap-20261018-211125-038258/`。截图确认涂地前后地图能正常显示，但其中还有角色图标、方向/光晕等UI叠层；当前尚未分离叠层、校验到世界格子的投影，不能直接按橙/紫像素统计真值。此X输入只用于显式诊断，所有帧均记入STEP；**没有给擂台加入隐式开图/中立推进来冒充无干扰实时采样**。
- **后续假设/定位方向，未证实：** ①用不同X/Z/高度的真实落墨对照，检验是否有独立paint平面范围/缩放，不能仅凭一个墨团认定必为打包UV。②若确实走mesh UV，需要关联原生ColPaintUVMapper/面板到已提取碰撞面，再做格子采样。③公开地图可作为独立参考，但需去掉UI叠层并验证空间映射；不能把世界坐标关系留空后将截图色块直接命名为世界墨图。**目前 `RefereeSnapshot.paint=None`，不是测得零涂地。**
- 击倒归属也仍未接通：上述76步中确有0号坠落，native HUD Down计数0→1、alive=0且HP仍1，确认不是以HP==0代替死亡。但SimpleReplay DeathEvent编码/复制的四个已安装探针均0次调用，不能把静态回放布局当作局内事件。最后几何诊断另装了TroubleDie网络编码候选main+0x27f7f9c/+0x27f7fa0；其近距离ZR诊断没有造成目标Down，计数为0 **不能证明网络候选不工作**。尚需独立实际死亡/击倒闭环。既有伤害瞄准待办继续归A4 aim_at，**不是本次新的停止理由**；未根据双方同为8000配置去伪造“谁用什么击倒谁”，`knockdowns=None`仍表示未知。
- `tests/run_all.sh --milestone a3` 已接入组件及完整A3门槛，默认会启动新原生场景。`--native-evidence <result.json>` 仅作重放诊断，明确永不签收fresh native。入口重放第二轮的总日志 `work/a3/gate-replay.log` 退出1；随后对最终356步原件运行 `tests/test_a3.py --native-evidence ...`，`work/tests/a3-check-20261018-213559-311175/result.json` **passed=false/full_a3_passed=false**：七项geometry_cases全true、policy_process_passed=true，native_paint_samples=0、native_knockdown_samples=0、native_attributed_events=0；错误明确为两项原生字段不可用及重放非fresh。这里计数0表示“可用样本数0”，不是声称真实涂地/击倒均为0。总日志 `work/a3/gate-final-evidence.log`。
- 边界/几何/实际子进程 **9+4+2=15项通过**，原生传输 **27项通过**；入口的固定时钟/等待、GPU/headless、HID、LDN及资源规则组件通过。最终原生场景的七项可见性与过程通道也通过，但它们没有覆盖缺失的paint/attribution，不把部分成功写成完整A3。
- 五个新双端会话共十宿主均优雅退出，无CRASH/FATAL；各会话pressure最大1、新swapout0。最终356步269次资源采样、footprint合计峰值9049MiB。完整汇总 `work/a3/geometric-native-runs-summary.json`，原件/参考档close核对未变，截图/atlas/原始状态/栈/碰撞网格/转换器只在忽略的work。新增源代码及测试、文档、可重放补丁留在工作区供后续继续；没有提交游戏数据或游戏画面。


## 2026-10-18：按指挥方拆分 A3a / A3b，解除 A4/A5 前置阻塞

- 本节覆盖此前“完整A3未签收、停止”的推进顺序：A3a只验几何可见性、裁判/策略独立接口与白名单子进程；A3b（实时墨图、真实击倒归属）移到A5之后，不阻塞A4/A5。A1/A2签收保持有效。GOAL及README同步，正式入口改为 `--milestone a3a`。
- A3a继续要求 `RefereeSnapshot.paint=None`、`knockdowns=None`，不是测得零。新增测试把伪paint、击倒列表、kills、paint_points、HUD Down计数及结算比分混入三次连续原生metadata；私有适配仍输出两个None，策略JSON仍无这两个字段。原生验收也逐屏障检查unknown，不再因A3b不可用阻断A3a。
- 依指示保留A3b研究方向：①墨纹理可能按地图渲染模型第二套UV映射，纹素应关联渲染三角形再回到世界坐标，不能强套碰撞AABB平面映射；②在若干已知X/Z/高度处原地涂墨，测变化纹素，经验标定/拟合映射并留出验证点；③真实击倒归属查局内死亡网络事件。这些是候选方向，尚未验证。
- A5先用已有结算比分判胜负，报告结算涂地率。1v1击倒统计先读观察者本端HUD敌方倒下事件；坠落/出界按位置判为环境死亡并单列，不能写成精确原生最后一击/武器归属，不能用HP==0替代Down。
- 正在从正式入口启动新会话验收，旧356步截图/回放证据保留但不冒充新的原生运行。新日志 `work/a3/a3a-acceptance.log`，结果待定；此段待实测通过后补上签收与提交信息。

- A3a首次新运行保留失败：`a3a-20261018-214821-879316`，新原生场景前五项通过，跳起可见；开始潜游12帧时仅移动约0.36单位，尚未达到固定溅墨速度阈值0.045单位/present，测试提前断言可见。未放宽阈值或改原件；改为最多6×6帧等实际稳定运动，再检查溅墨例外。同时修正同一原生样本在重复step时保留已测运动标记（新采样才重算），补回归。两端已优雅关闭，继续从正式入口重跑。


### A3a 最终签收 PASS：几何可见性、独立接口、白名单策略子进程

**A3a PASS，A3b留到A5之后；下一步A4。** 此节覆盖此前完整A3停止线，A1/A2保持已签收，未请求其它模型。

- 正式命令 `bash tests/run_all.sh --milestone a3a --timeout 2400` **退出0**（第二次新运行），日志 `work/a3/a3a-acceptance-2.log`；结果 `work/tests/a3a-20261018-215718-538694/result.json`：passed=true/full_a3a_passed=true、errors=[]、replay_only=false。
- 原生场景 `work/tests/a3-visibility-20261018-215718-655400/result.json` /会话 `m6-2p-20261018-215720-951701`，**354 STEP**。双端8000/fixed60，七项geometry_cases全true；跳起/稳定潜游溅墨例外均通过。逐张查看本轮七张原生截图，符合既定近似；核对图只在 `work/a3/a3a-native-contact-sheet.png`。本次仍为温泉峡谷实机场景；三图碰撞已提取，不冒称另两图场景也实机标定。
- 原生状态经过独立RefereeAPI真值/策略访问器，再到白名单JSON与实际sandbox策略子进程的七场景回放通过；拒绝直接传RefereeSnapshot。边界 **10项**、几何 **4项**、实际进程 **2项**、生产传输 **27项**通过；公共时钟/等待、GPU/headless、HID、LDN、资源规则组件通过。
- 全部屏障上paint/knockdowns均None，deferred_fields_unknown=true；可用墨图/击倒归属样本数均0，表示未知，不是真实事件为零。伪字段/比分/HUD计数注入回归确认不填假值。A3b方向和A5临时统计口径见拆分决定，A3a通过不依赖它们完成。
- 首次重跑失败原件保留；第二次只修正运动样本重复使用与测试开始潜游的加速期取样，没有改变眼高、FOV、距离或溅墨阈值。`work/a3/a3a-acceptance-code-2.json` 受测宿主、源码和入口冻结核对无差异。
- 两宿主均优雅退出，296次资源采样pressure最大1、新增swapout **0**、footprint合计峰值 **8171MiB**；close存档核对未变。补丁重新生成且反向应用检查、暂存差异检查通过。只暂存本项目A3a源码/测试/文档/补丁；A4准备代码不进本次commit，所有碰撞资产、NSO/RomFS/shader/画面/原始状态仍只在忽略的work。


## 2026-10-18：A3a已推送，开始A4地图与公共技能库（未签收）

- A3a commit `061403c575500e9c49071be346a9f9c8ed9567ca` 已push；远端main核对相同。A3b按指示在A5之后，不作为A4前置。
- `tools/build_arena_maps.py` 从已提取Cmn/Pnt的材料/角色碰撞数据生成保守多层图，区别Sight与SplPlayer/Human/Squid层，记录不可涂/Fence潜游限制；不把可潜游表面当当前己方墨。生成的human.npz、navigation.json仅在work。范围y=0..24、上步0.7/下落3.5、身体半径0.3，动态遗漏沿manifest保留；没有承诺任意高台攀墙或动态物体寻路。
- 三图目前13989/9544/11616节点、97643/66036/77754有向边，均有双方出生发射标记/落点、center/west_lane/east_lane/alpha_base/bravo_base/central_high实验命名区。中心与中央高台从双方出生区可达交集选择，避免桥下孤立面和不可达装饰顶面；命名不是官方玩家报点。离线四类出生→目标路径均存在，仍需原生角色走通。
- 公共 `arena/lib/` 提供MapAtlas/Skills及move_to/aim_at/swim_to/ink_at/objective；只收白名单字典，自身采样过期/死亡/缺瞄准反馈时中立；路线有无进展及总帧上限。swim_to显式涂路、用本机潜墨反馈，不读取私有实时墨图。
- own_view复用M6已诊断own packet的水平视向与pitch，只加入本机own白名单和公共stage_id，不泄露敌方view；与A3几何可见性无关，没有恢复游戏相机探针路线。生产传输29项、A3边界10项、A4控制/图组件及实际public atlas sandbox读取检查通过，原生路线/瞄准/墨迹/潜游/伤害尚待验证。
- 正式入口新增 `--milestone a4`，依次重建三张公共图并新开三局；每张测走向中央高台/平地、aim_at、ink_at、真实潜墨swim_to。温泉峡谷额外平地近距离正对，目标先涂己墨并回血，比较预排队连续与逐步暂停的相同一帧ZR伤害，补A1待办。当前结果待定，日志 `work/a4/acceptance.log`。

- A4首次正式原生运行保留失败：总结果 `work/tests/a4-20261018-221038-628002/result.json`，场景 `a4-stage1-20261018-221231-573764`，**371 STEP**。0号已到[-5.2168,5.8772,-2.6127]中央高台附近，1号停在[10.8465,3,7.7436]，离平地目标[11.5,3,8]约0.702；末段按距离缩小推杆后落入原生左杆死区，180无进展帧检查正确失败。不是网格无路径、fixed60或断房。改为到达容差内之前维持0.85有效幅度，新增近目标仍超过死区的回归，不放宽0.7到达容差；随后从正式入口重跑。原件、截图和sample留work，首轮不计通过。

- 第二次入口在新增组件回归阶段失败，尚未新开游戏：测试先把角色推进到1.25，再错误地用回起点的位置检查无进展，真实控制器按位移正确重置计时。修正测试为停在同一位置再检查超时，非游戏故障。并把右杆有效最小幅度置0.35，瞄准场景采用1帧纠正+10帧中立等待own view新样本，避免10Hz反馈被重复施加；参数仍需原生验证。


### A4 当前新卡点：细粒度STEP仍在推进时，长客体SleepThread触发60秒绝对墙钟上限（停止，未签收）

**按“真正的新卡点才停下”在此停止。A3a已签收并push `061403c575500e9c49071be346a9f9c8ed9567ca`；A4未签收，A1伤害补测未完成。A5只有预备代码，没有启动原生擂台/100局。A3b仍在A5之后，不是本次阻塞项；没有请求其它模型。**

- 第三次入口 `bash tests/run_all.sh --milestone a4 --timeout 2400` **退出1**，日志 `work/a4/acceptance-3.log`，总结果 `work/tests/a4-20261018-222240-126537/result.json`：passed=false/full_a4_passed=false，stage1失败后未启动stage2/3。首轮371步死区失败及第二次纯组件失败均保留，不改原件。
- 本次温泉峡谷场景 `work/tests/a4-stage1-20261018-222430-348016/result.json`，会话 `m6-2p-20261018-222430-385001`，**1035个成功STEP**。走高台/平地完成，0号高台落点[-5.1685,5.9243,-2.7027]、1号平地[11.1270,3,8.1451]；aim_at对目标腰部收敛（39轮纠正），已查看截图；ink_at墨量1→0.883000255；swim_to 14步、8份真实潜墨样本，位置由[7.8061,3,7.9921]到[3.5354,3,6.8094]，随后走回平地。geometry_skills_passed=true只是该图子项，**不是A4签收或三图实机路线通过**。
- 新故障发生在 `target-own-floor-aim` / `-sample`，即准备对端脚下墨色阶段。最后成功样本双方HP均1、剩余约75秒，**尚未执行任何连续/暂停伤害trial，damage不存在**。之后协调器 `Client.receive` 收到不足27648字节的图像，报 `RuntimeError('truncated RL image')`；这只是宿主中止导致的下游表现，不把它当传输格式根因。1号退出 **-6**，close报告unclean exit；0号随后优雅清理。
- 1号 `host.log` 第1200670行：`RL_SLEEP begin ns=5425000000 frame=16036 lr=0x1116f4188`；第1269231行：`FATAL RL_SLEEP wall limit ns=5425000000 frame=16328 lr=0x1116f4188`。中间推进 **292 present≈4.8667秒客体时间**，仍少于请求的5.425秒，附近RL_FRAME_BEGIN仍逐帧输出。资源记录也显示约59.76秒墙钟内1号16020→16260（240 present），不能把该窗口称为“60秒无进展死锁”。
- 当前源码证据：`upstream/dm/host/hle_thread.c:31` 定义DM_RL_WAIT_LIMIT_NS=60000000000；SleepThread分支603–611先取guest_ns截止时间，但607–608按从进入函数起的**绝对宿主墙钟**超过60秒直接die，不区分策略/ACK间暂停，也不因客体时间持续推进而刷新。现有A1已签收的固定每present时间在成功ACK前缀仍精确；本次暴露的是长客体sleep与细粒度慢步进/暂停的超时兼容性，不能据此宣称重新测得游戏时间漂移。
- **假设/待验证修法，未实施：** ①绝对墙钟上限把正常慢步进/策略暂停计入，5.425秒客体sleep在本场景需超过60秒墙钟，因此误触发；应核对暂停状态、基于guest_ns进展的无进展计时，或仅累计受控运行时的等待墙钟，仍保留有界轮询和协调器STEP上限。②还需核对该长sleep的线程/调用上下文和最后不足1秒客体时间是否存在额外依赖，不能仅凭末尾仍有present就断言所有线程均正常。**没有直接删除超时、把fixed60切回realtime，或加快客体时间绕过。**
- 异常后在close前已sample：0号PID439采样1秒退出0，`sample-player-0.txt`；1号PID16624已中止，sample退出255、无法检查，错误原文在samples.json；未取得其成功的全线程采样，也未捕获匹配PID的macOS .ips，不能冒称有1号栈证据。原始日志/截图/最后状态与摘要 `work/a4/blocker/evidence.json` 全留work。没有重开更多原生实验。
- 本轮465次资源采样pressure最大1、新swapout **0**、footprint合计峰值 **7425MiB**，未见资源准入停止信号。门槛冻结的dmhost、公共库Python和场景驱动SHA256复核全部一致。所有宿主/驱动/空气服务已退出；原件/参考档哈希再次均为 `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。
- A4当前组件边界：公共时钟/等待/GPU/HID/LDN及资源规则、传输29、A3边界10/几何4/实际进程2、A4组件6、实际公开atlas进程1均通过；另两图只有提取/网格/离线连通证据。A4完整门槛失败，不提交/推送A4。
- 等待原生期间预备了A5两个弱示例且仅两个：rush/直冲、high-ground/占高台，完整quick-super-jump配装、同为8000；仅用公共库，定期松开ZR避免永远蓄力，不调策略强度。另有config规范、四房进程池、按对交换出生侧/阵营、结算比分胜负、观察者HUD计数/位置环境死亡、精确二项区间、逐present输入及带采样帧状态记录的候选源码。统计/配置/HUD组件3项、两个示例实际sandbox执行1项通过，**未运行任何A5原生对局，未接入run_all的a5签收分支，未验证四房并行或100局**；后续必须在A4通过后再验。
- A4/A5候选源码、测试、文档与更新后的可重放补丁留在本项目工作区，均未暂存/commit/push；A3a远端checkpoint不变。游戏数据、地图网格、参数、画面、原始状态与线程栈仅在忽略的work，未提交。

## 2026-10-18：按指挥方修订恢复 A4，无进展看门狗

- 前节 `RL_SLEEP wall limit` 是错误的墙钟上限：客体 5.425 秒等待只完成 292 presents（约 4.867 秒），并非 present 卡死。移除 fixed60 SleepThread / 条件等待的绝对墙钟截止，以及预算端点输入等待、命令读取的 60 秒截止。
- 新增独立线程看门狗，默认 120 秒（`stall_timeout` / `DM_RL_STALL_SECONDS`），只累计受控模式有未完成 STEP 预算且共享时钟未暂停的墙钟时间。present 增长重置计数；策略暂停和预算耗尽等待下一条命令不累计。真卡死记录 `RL_STALL`，包括 present、活跃停顿时长及剩余预算。策略暂停前后均没有放宽客体 deadline。
- 组件包含纯状态跨天暂停/慢步进/真卡死、生产 5.425 秒客体 SleepThread 在 >60 秒慢步进后正常完成及定时事件等待、65 秒真实策略暂停后继续 STEP、共享暂停期间有预算不误杀及恢复后真停帧中止。测试已接入 A1–A4 入口，结果待本轮完整执行。
- STEP 接收默认改为看门狗阈值 +30 秒（150 秒）；A4/A5 同步采用该默认阈值，避免旧 30 秒传输超时抢先误判。高频逐等待日志改为 `DM_RL_WAIT_TRACE=1` 显式诊断，卡死摘要始终记录。协调器错误扫描改为增量读取并保留失败状态，避免每步反复扫描不断变大的完整宿主日志；不改变动作或客体时间。
- 本节仅恢复执行，A4/A5 尚未签收；接着重新跑三张图实机与平地近距离 A1 伤害补测。A3b 仍在 A5 之后；A5 完成后按本次用户指示停下，不自动启动 T1。

- 新增组件正式入口结果：`work/a4/acceptance-watchdog.log`，看门狗纯状态 **367/367**；生产长等待/定时事件成功；Python 看门狗/默认阈值/增量错误保留 **6/6（68.078 秒，含 65 秒暂停）**，真实停帧夹具触发 `RL_STALL`。另有 RL 传输 **29/29**、fixed60 时钟 **10804/10804**、短睡眠3、idle等待、条件变量、A3 边界10/几何4/进程2、A4组件6全部通过。完整实机入口 `work/tests/a4-20261018-225821-315258/` 正在运行，尚不据此签收 A4。

### A4 看门狗修订后首次完整实机：时钟问题已解，修正验收脚本准备预算

- 入口 `work/tests/a4-20261018-225821-315258/result.json` 仍为失败，不签收。首图 `work/tests/a4-stage1-20261018-230008-209925/result.json` 共 **1804 STEP**，高台/平地/瞄准/涂路/实际潜墨全部通过，越过先前长 SleepThread 失败阶段，无 RL_STALL 或运行时崩溃。连续伤害命中：HP **1→.8→.45**，损失 **.550000012**，HUD **1.0 秒**；目标处于同高平地约 3.53 距离，命中前双方满 HP，目标脚下 ground_contact=0。
- 第二个试验未射击：脚本为双方重复转向背后涂脚下地面，准备动作耗尽原生 180 秒，游戏正常到 Judge，`match ended during A4 scenes`。这是测试场景预算和对照起始条件问题，并非新客体卡死；第一次命中还使目标发生约 .49 单位真实击退，必须复位再对照。
- 修正脚本：攻击者脚下墨仅首轮准备（对端不攻击）；每轮仍让目标涂自身脚下并确认满血。后续轮用短普通手柄输入+新鲜自身位置反馈，将双方复位至首次射击位置（误差 ≤.15），避免把击退导致的距离变化算成伤害差异；不改游戏计时/血量/位置，不把已失败入口改写为通过。接着重跑完整入口。

- 进一步统一执行等待：`step_timeout=150` 只用于连接及初始 ACK；fixed60 握手完成后取消 STEP 读取的绝对墙钟截止，由宿主 `RL_STALL` 关闭连接结束真正卡死。否则单次大帧预算即使始终有 present 进展也可能在 150 秒误杀。realtime/独立连接诊断仍保留显式有界接收。新增“单次 STEP 持续慢呈现，超过接收超时和看门狗区间仍完成”的原生传输夹具回归。

### A4 本轮温泉峡谷通过，另两图实机进行中

- 最终版看门狗组件 `work/a4/watchdog-all-final.log` **7/7（68.650 秒）**；新增长 STEP 测试自身持续 1.424 秒，超过测试接收超时 .05 秒和看门狗 .4 秒仍正常完成，因为每 .1 秒有新 present。传输29/29再次通过。无绝对 STEP 接收截止仅用于 fixed60 完成握手之后。
- 首图结果 `work/tests/a4-stage1-20261018-231611-601829/result.json`：**1429 STEP，probe_completed=true、geometry_skills_passed=true、a1_damage_passed=true、errors=[]**。高台/平地走通；瞄准37轮；涂路墨量1→.883000255；实际潜墨8个自身采样，swim_to 23步、返回15步。
- A1伤害补测：两次平地 Y≈3，距离约3.53 / 3.64，目标起始位置误差约 .113；均满血后射击，同一 ZR 1帧+中立7/7/15/15/15帧脚本。连续/暂停两次 HP 损失均 **.550000012**，HUD均 **1.0 秒**。暂停版每段前等待 .2 秒墙钟；两次部分伤害不是击杀或环境死亡。HP约10Hz包的中间采样不同，不宣称逐帧伤害轨迹相同。已人工查看两次原生截图：平地近距无遮挡、目标和攻击者各在自身墨上，未隔台沿。
- 该会话资源277次采样，最高pressure1、新增swapout0、footprint合计峰值8972MiB；清理无错误，双方正常退出。补充运行时冻结 `work/a4/acceptance-runtime-2.json` 覆盖实际 binary/rl/裁判边界/技能/驱动，当前hash全匹配。整体入口 `work/tests/a4-20261018-231423-522804/` 继续 District00、Yagara；**A4尚未整体签收**。

## 当前卡点：A4 District00 实机高台路线被挡（按指示停止，A4/A5 未签收）

**本节是新的导航/实机通路卡点；不是 fixed60 等待误杀或客体卡死。** 按“真正的新卡点才停下”停止推进，没有启动 Yagara、A5 原生四场/百局或 T1，没有调用其它模型。

### 现象与证据

- 正式入口 `bash tests/run_all.sh --milestone a4 --timeout 3000`：`work/tests/a4-20261018-231423-522804/result.json` 为 `passed=false/full_a4_passed=false`。地图1通过；地图2失败；地图3未启动。不得把首图/组件通过写成 A4 整体验收。
- 地图2：`work/tests/a4-stage2-20261018-232556-373765/result.json`，**424次成功STEP后**下一次 `move_to` 返回 blocked。目标 `central_high=(-15,9,-14)`；实际被挡于约 **(-3.9,8.3838,-27.0483)**。另一端已到平地测试点 **(-4.9719,6,.7558)**。双方满HP、余时约133秒、present和HUD仍推进，失败为技能的位置无进展上限，不是 RL_STALL。
- 原始 `steps.jsonl`、已人工查看的 `failure-player-0.png` 及双端截图留在该目录。失败前逐宿主 macOS sample 均返回0：`samples.json` / `sample-player-0.txt` / `sample-player-1.txt`。清理后无剩余 dmhost、原生驱动或裁判进程。
- 只读重放 `navigation-replay.json`：路径末段 **(-4,8.2499,-27) → (-4,8.7501,-28) → (-5,9,-27)**；控制器已推进到 path_index103 / **(-5,9,-27)**，持续约 .85推杆但实际脚部位置停在低一侧。该重放不更改原始结果。
- 同一角色碰撞网格的只读线段复核：实际位置→目标 waypoint，脚高+.05 / +.15 均 blocked，+.35 / +.65 clear；当前生成器使用较高端高度+.35的横向检查为clear。名义路径边的+.05也blocked、+.15clear。证明高位视线/边检查通过不足以保证实际脚部能走过，不宣称已找到唯一根因。

### 假设与下一次最小验证方向（未执行）

1. `move_to` 用水平 .8 半径提前推进 waypoint，可能在坡道拐点尚未走够高度就切向下一点，切入台沿立面；需用更小拐点容差和高度约束做同一点原生对照。
2. 图的最大上升 .7 与高位平面射线未模拟连续脚部/角色体积，可能把需要跨台阶或跳跃的边误标为可步行。需把贴地/体积扫掠和坡道连续支撑纳入边验证，并核对 native 可跨高度；不能仅为了测试通过另挑高台或把缺失路径当可走。
3. 上述两者可能共同作用。当前没有原生精确 waypoint / 跳跃对照，未修改参数后重复尝试，更没有宣称路线修复。

### 已完成部分与保留状态

- 无进展看门狗改动及组件7/7、纯状态367/367、生产 >60秒慢步进客体等待、65秒策略暂停、长STEP持续present、真停帧中止都已通过并接入入口。fixed60握手后无绝对STEP读取截止；默认120秒阈值可配，策略暂停不计时。
- 温泉峡谷技能与 A1 伤害补测通过：连续/暂停损失均 .550000012，HUD均1.0秒；完整首图证据见上节。
- 地图2会话201次资源采样，pressure最高1，新增swapout0，footprint合计峰值9310MiB；双方无FATAL/RL_STALL且均优雅退出。冻结运行时hash逐项匹配，参考/原件存档SHA256仍为 `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。
- A5仅预备代码、两个弱基线与组件4/实际子进程1通过；**尚无四场并行或100局实机证据，也无实测胜率/置信区间结果**。A3b仍在A5之后。
- A4未满足整体验收，故本轮不新增签收commit/push。改动保留在 `splatoon3-native` 工作区，补丁已更新；游戏数据、截图、原始trace、sample均只在忽略的 `work/`。当前已有HEAD与远端一致为 `eda4b4704007b574e1a1a67aaae260d2a1d292e0`（既有T1参数文档提交，非本轮A4签收）。

## 2026-10-19：按指挥方先保存 A4 partial，再恢复导航修正

- 按最新明确指示提交/推送已验证部分，提交标记 **A4 partial**：无进展看门狗及回归、温泉峡谷技能、A1伤害补测。运行时代码冻结再次核对一致，温泉峡谷原始结果仍为通过；既有 District00 失败证据保留。此提交不是 A4 整体验收，不包含 A5 预备源码。
- 接下来执行脚/膝+角色半径扫掠、高差边约束、严格拐点/减速、一次跳跃与临时封边后最多3次重规划；三张地图各用预设路线，到达率≥90%，失败记录位置。全部通过后才签收 A4，再跑 A5；A5完成后停止，A3b和T1不在本轮启动。

## 2026-10-19：A4 partial 已推送，按新标准恢复三图验收

- partial commit **`7e2ecd7dc86c7c0142ceb75fc83bbad88b19d064`** 已推送，`ls-remote main` 一致。仅本项目已验证源码/测试/文档/补丁入库；A5预备代码未入此提交，游戏资产/画面没有暂存。它不代表完整A4。
- 按指挥方修正导航：每条候选边先按角色碰撞材料取局部三角形，用中心及左右 .3 半径三条通道，按≤.2间隔检查脚 .08、腿 .3、膝 .55、躯干1.0、头1.4高度线段及横向截面。扫掠计入分段端点，薄墙落在端点也会拦截。地面支撑沿坡采样，保守台阶阈值 .2；较大离散高差或低位被挡只有通过独立跳跃弧检查才标为jump，否则无边。连续坡面不当作离散台阶。所有生成数据仍只在work，使用的是多线段胶囊近似，不宣称精确复刻原生物理形状。
- 路径跟随中间点半径 .24、高差≤.3才推进；近点推杆 .55（保持在有效输入区）/远点 .85，避免旧 .8 半径切过弯角。最终到达也检查高度。无进展默认120帧可配，先给一次B跳跃、观察至少60帧；跳起原地上下不算水平进展。仍无前进则当前有向边临时封锁1800帧并重规划；最多3次重规划，耗尽才blocked。事件含实际位置、边和尝试次数。持续前进不受旧总路径3600帧上限误杀。
- 新回归10项通过：包括严格拐点/高度/减速、一次跳跃→封边→替代路线可达、三次重规划失败退出、临时封边过期、20cm阈值与较大台阶jump、三米落差明确jump、连续坡面walk、薄墙和半径内平行墙拦截。
- 离线重建初次发现两出生区被隔离；只读检查确认是3米落差边的线性下降扫掠切入平台立面。改为先越出台沿再下降的独立jump轨迹并新增回归；不改walk检查高度来放行。District00目前9544节点/60628边/762 jump边，双方可达交集恢复，中央高台仍为原定(-15,9,-14)，没有通过换高台绕过原失败点。
- 新入口 `bash tests/run_all.sh --milestone a4 --timeout 3000`，日志 `work/a4/acceptance-recovery.log`。优先District00，然后温泉峡谷、Yagara；每图预设10条路线，按6+4分在两个正常180秒的新局，失败记录实际位置/跳跃/封边/重规划，门槛≥9/10到达。每图另测aim/ink及实际己墨潜游；若对局剩余时间不足，只能正常关闭并新开一局做技能准备，不改客体计时。
- A1伤害补测明确复用已推送partial的原生证据（两次.550000012/1.0秒），总结果标记reused_accepted_partial及原件路径/hash；检查dmhost与rl计时/传输哈希未变，aim_at/ink_at/own_state函数AST与partial commit一致。导航为本轮新的三图实机证据，不把旧首图当作新三图结果。
- 本节仅恢复执行，完整A4未签收，A5四房/百局未启动。

- 首次恢复入口 `work/tests/a4-20261019-000258-946566/` 在District00启动期主动SIGINT中止（尚无受控路线结果）。原因是重建后的离线预检发现Yunohana旧中央点(0,3,0)不在可达图中，生成器中央参考改为(0,3,-5)；若不纠正预设会把已知无静态路径的坐标反复当路线目标。仅在任何实机路线成绩产生之前将中央目标与修正网格对齐，原始高台三图均保持固定。中止保留原件、sample和清理记录，不计签收。新增全部预设端点间、双方出生区到预设目标的静态可达性预检，再冻结源码运行；未改已失败原始结果，也未以改高台绕过District00卡点。

- 进一步离线预检：Yagara原低洼侧路(-18,1.5,0)/(18,1.5,0)从出生区可达，但当前步行/jump图无返回中央的路径；这些单向区域仍完整保留在图中，不能冒称已支持墙面潜墨攀爬。修正中央命名区选取：取中央节点的正向/反向可达交集，中央侧路和高台从这一可往返区域选取；双方出生初始路线仍按实际原生落点起步。新增单向sink不被误作中央可往返区域、且不删除原始边的回归。组件现11项。
- 预设路线以固定任务序列+静态中央区坐标在实机前生成并冻结，三图原回归高台坐标额外固定断言（未变化）；中央/侧路坐标允许由修正后的步行连通图确定，并记录完整manifest，不能在看到实机成绩后替换。所有目标两两以及双方出生到目标均需离线预检通过，才启动新原生套件。入口重新开始：`work/a4/acceptance-recovery-2.log`；前次主动中止不计成绩。

### A4 恢复入口第二轮：原高台已走通，修正新减速参数的对角线死区

- `work/tests/a4-20261019-001225-018519/` 在首图District00第一局结束附近主动中止，仍不计整体验收。原生 `work/tests/a4-routes-stage2-20261019-001415-398862/result.json` 保留1309 STEP和KeyboardInterrupt记录：已完成前六个任务的4次到达/2次blocked。**客机case3已到(-15.5549,9.0000,-14.2030)，一次jump发生于(-3.9805,9,-28.7875)**，原来高台阻挡有了新的实际到达证据，但不是≥90%验收。
- 两个失败均是0号在中央点附近转向；case2跳一次、临时封边后3次no_route，正常返回blocked，未发生宿主卡死。只读回算当时own_view_yaw=-3.02555、位置约(-1.29,6,1.33)、目标最近点(-1,6,1)，旧 .55圆归一化输出 **(.38615,.39165)**，两个分量均处在原生低效/死区范围；此处是新减速参数退化，不将其当另一个未知客体卡点停止。
- 修正转向幅度：远点主轴.85、向量上限.95；只有拐点邻近或极近点主轴.65、向量上限.85。按主轴标定后再限制圆内幅度，使斜向仍保有有效分量；严格.24点半径/高度条件和跳跃重规划不变。新增对角线分量有效且拐点确实慢于直线的回归，现12项通过。持续直线不再在每个普通网格点前都降到.55。
- 代码变化后重新冻结并从入口重跑，不修改旧result或沿用中止入口的hash签收。新日志 `work/a4/acceptance-recovery-3.log`。

- 继续只读核对上一轮 `route-2-blocked-player_0.png`：中央投影点附近有箱体；因此低输入幅度之外，还存在跟随器强迫进入最近格点精确中心的起点问题。原角色已在目标容差内，重新规划时却再次朝同一箱角中心走，失败后还会封锁它的出边，不能将此都归因为死区。修正：同层且距离最近格点≤.75时，A*仍用该顶点作为锚，实际路径第一个顶点改为实测脚部位置；后续网格拐点继续严格.24/高度.3，不放宽弯点阈值。新增回归验证从(-1.3,6,1.33)直接朝下一点离开，不先走入(-1,6,1)箱角。
- 由于源码变化，第三轮入口 `work/tests/a4-20261019-002853-310544/` 在启动期主动中止并保留记录；未计任何路线成绩。当前导航回归13项通过，下一轮日志 `work/a4/acceptance-recovery-4.log`。上述为同一导航实现的定位/修正，未调用其它模型，未将中止运行计入A4。

### A4 本轮 District00 通过（另两图进行中）

- 新原生 `work/tests/a4-routes-stage2-20261019-004203-392012/result.json`：**passed=true/probe_completed=true、10/10到达、0终止失败、skills_passed=true、errors=[]**。两局证据分别 `m6-2p-20261019-004203-440739`、`m6-2p-20261019-004951-372767`。
- 两次原定高台任务（case3/4）均到达，各执行1次标定jump；其他出生台阶也有规划jump。本轮所有路线均不需要重规划；不冒称已在这一轮观察到成功重规划。替代路线/3次失败/过期等由13项组件覆盖，之前失败轮有真实跳跃→封边→3次no_route记录。
- 本机瞄准53轮纠正后对齐；耗墨1→.883000255；实际己墨swim_to 26步、19次submerged反馈，结束约(-6.6773,6,-.1119)，无恢复事件。初始化/控制逐step fixed60精确检查通过，正常清理无错误。
- 同一入口继续温泉峡谷、Yagara，A4整体未签收；两个已主动中止入口仍为失败，不纳入成功率。

## 2026-10-19：A4 最终签收 PASS，三图30/30路线 + 公共技能 + A1伤害补测

**A4 PASS，覆盖此前所有A4停止/未签收状态；保留原始失败/中止记录。先前A4 partial `7e2ecd7`已推送；本节签收完整A4，下一步A5。A3b和T1未启动，没有调用其它模型。**

- 正式命令 `bash tests/run_all.sh --milestone a4 --timeout 3000` **退出0**，日志 `work/a4/acceptance-recovery-4.log`；总结果 `work/tests/a4-20261019-004014-515336/result.json`：passed=true、full_a4_passed=true、errors=[]、phase_passed=true。源码/公共图冻结逐项匹配。
- 按最新标准三图各10条预设路线（正常两局6+4，不改180秒Timer）：**District00 10/10、温泉峡谷10/10、Yagara10/10，均100%≥90%，终止失败0**。每条实际起终点、采样帧、jump/block/replan事件和到达截图均在原生目录；本轮总4040 STEP。
- District00：`work/tests/a4-routes-stage2-20261019-004203-392012/result.json`，1462步、瞄准53轮、墨量1→.883000255、swim26步/19次真实submerged反馈；规划jump11事件、重规划0。原定高台(-15,9,-14)从两侧任务均到达。
- 温泉峡谷：`work/tests/a4-routes-stage1-20261019-005712-036279/result.json`，1266步、瞄准55轮、同样耗墨、swim17步/10次submerged；jump18事件、**2次真实重规划后到达**。case3在约(-4.1965,3,4.1914)跳后仍受阻，封边6240→6037，换9节点路径后到高台；case8在(4.1945,3,-4.1930)封边7826→7632，换5节点路径后到中央。这些位置保留供后续网格修正，不把动态/小障碍近似写成全图精确。
- Yagara：`work/tests/a4-routes-stage3-20261019-011153-695717/result.json`，1312步、瞄准56轮、同样耗墨、swim19步/17次submerged；jump17事件、**1次真实重规划后到达**。case6在约(-.8305,7.5,51.1211)跳后无进展，封边5684→5683后重规划70节点并到东侧路。单向低洼区域仍在原图，中央命名侧路取可往返分量；没有宣称墙面潜墨攀爬已覆盖。
- 本轮三图aim/ink/swim本机反馈均通过；策略只读静态导航JSON、公共技能只收白名单OwnState的实际sandbox回归通过。裁判/策略接口边界和paint/knockdowns unknown规则继续有效。13项导航组件涵盖脚/膝/半径/薄墙/台阶/坡/跳跃、精确拐点、起点投影、临时封边、替代路线与三次失败退出；公共回归及生产传输29通过。
- A1伤害补测来自已经接受并推送的partial证据，不冒充本轮新射击：两次损失均.550000012、HUD均1.0秒，原件sha256 `c125ab7feb7a7435d6040272a34971c3dd4953147fd25b3f797d95f258dcf6d3`。入口检查原生dmhost/rl计时传输hash未变，以及除Skills导航类外模块AST与partial commit一致，结果明确标记reused_accepted_partial=true。
- 六个双端会话共12宿主均无FATAL且优雅退出，1296次资源采样最高pressure1、新增swapout0、同时两端footprint合计峰值9222MiB。原件/参考档由各会话关闭时核对不变；所有原生进程与空气服务已清理。图数据/游戏画面/原始trace/sample仍只在work，不入库。完整A4提交只含本项目源码/测试/文档；A5预备源仍单独保留，待A4推送后进行四房烟测与100局。

## 2026-10-19：A4 已推送，A5 四房原生烟测出现新卡点（停止，A5 未签收）

**A4 完整提交 `91cd943be7ea5f4eee69097fdc9124d475c472b0` 已 push，故障后再次核对本地 HEAD / 远端 main 相同。A4 partial `7e2ecd7` 和 A1 伤害补测保持有效。本节为新的四房原生运行卡点，按指示记录后停止；100局、A3b、T1 均未启动，没有请求其它模型。**

- 已把 A5 接入正式入口：`bash tests/run_all.sh --milestone a5 --games 4 --parallel 4 --timeout 7200`。日志 `work/a5/smoke-4.log`，入口退出1；完整结果 `work/arena/tournament-20261019-013748-801620/result.json`。这是诊断烟测，`diagnostic_only=true`、`phase_passed=false`、`full_a5_passed=false`，不作为百局验收。前置公共回归、A4导航组件、A3接口边界及 A5组件6项 / 两基线实际sandbox子进程测试1项均通过。
- 四个房间各自独立 air、存档副本、fixed60 时钟、双端工作刮水刀8000，按对交换策略/阵营/出生侧。仅保留直冲、占高台两个弱基线，未调强。八宿主使用 M5 两路加载准入：每房保留自己的 `active` 标记，房内 `slot-0/1` 链到擂台共享的两个 flock 文件，避免全局激活使一次性加载锁提前耗尽。组件验证本地激活隔离、共享inode/真实互斥、过晚配置拒绝和只取消所属进程。
- 逐房实际屏障记录证实八个不同宿主 PID **75319/92426、75318/92427、75316/92428、75317/92429** 同时推进，首个ACK到最后成功ACK的保守公共重叠 **504.5909秒**。这只证明发生了四房并行，不能替代四房全部正常结算；原始签收 `concurrency_windows` 因本批失败未写为通过。补充诊断在同目录 `smoke-diagnostics.json`。

### A5 当前卡点：District00 客端有 STEP 预算但 present 真停滞，120秒看门狗中止

1. round-000 / round-001（温泉峡谷）均正常到原生 Winners，**11508受控帧**，双端互反结算比分分别 **1.1:3.2、3.0:1.1**；换边后占高台示例均胜。两局 HUD down 计数读回均0；`paint` / `knockdowns` 仍为 unknown。只有2个有效样本，不声称百局胜率或策略显著强弱；程序输出的两局区间只是部分统计。
2. round-002（District00）最后完整屏障 **7932帧**，双方Timer HUD **47.5666656 / 47.5499992秒**；会话 `work/tests/m6-2p-20261019-013748-964858/`。客端 PID92428 的 `player-1/host.log:10695` 明确记录：`FATAL RL_STALL no present progress frame=17679 active_stall_ns=120003405084 limit_ns=120000000000 remaining=12`。前一行帧起点为 tick7933；有待执行预算而非策略暂停。随后 SIGABRT / 退出-6，协调器 receive 报 `native RL connection closed or invalid observation header`。这与此前长等待时present持续增长的误杀不同；当前确有120秒无present进展，根因尚未确定。
3. round-003（District00）推进到 **10524帧**，HUD余 **4.36666679 / 4.44999981秒**，被共享取消事件回收，`cancelled=true`；该场没有第二个 RL_STALL，不计为另一次独立原生崩溃。协调器未启动下一批，未将失败/取消当成策略输赢。
4. macOS 已生成故障 PID92428 的 SIGABRT 报告，完整 **52线程**原件复制到忽略目录 `.../round-002/player-1-crash.ips`，SHA256 **`14ae00a7b796da004f5d0e7de3d5e1bfb02b5e88360578b017f388ed583f1b4e`**，摘要 `crash-summary.json`。35线程在 `block_inner`，主线程为 `svc_thread → block_inner → pthread_cond_wait`；`nvn-present` 在 `present_main` 条件等待，4个客体线程在 svc nanosleep，看门狗线程执行 abort。故障时进程已由看门狗退出，因此没有事后伪称抓到了活进程 sample；采用系统崩溃时全部线程栈作证。
5. **待验证假设**：fixed60 的帧内客体事件/条件等待仍有一条需要未来客体时间或另一端推进才能释放的路径，在特定District00状态或并发调度下形成等待环；另一个方向是网络接收/任务唤醒不同步导致present生产者等待。现有栈不能识别具体等待对象/发送方，不据此直接改时钟、提高阈值或调策略掩盖。后续定位应关联当帧等待对象、客体调用栈与对端日志，再做同局流程的单房/四房对照。
6. 四会话共 **2100次**资源采样，最高pressure **2**、新增swapout **0**；每房两端footprint峰值 **7163 / 7045 / 7247 / 7264 MiB**，它们不是同时刻总和。未触发M5 critical阈值，没有证据把此次停滞认定为OOM。原生二进制、arena/rl源码、三图navigation/sight共 **30项冻结hash全部一致**。原件/参考存档仍为 `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。

- 八个所属宿主、四个air、策略子进程和测试协调器均已回收；故障日志、逐present输入、策略白名单观测/动作、原生屏障和截图仅留在忽略的work。A5候选源码/测试与本节文档保留未提交，**没有创建A5签收commit/push**，没有提交游戏资产/画面。至此按真正新卡点停止。

## 2026-10-19：按指挥方恢复 A5，一轮定位 + 单房 void 容错

- 最新签收口径覆盖此前“一场失败即取消全部”的A5预备实现：目标100个有效原生结算局，void/(有效+void)≤10%，默认四房，void率高可降三房并记录比较。void重试保留逻辑局的地图/策略角色/换边位置；只清理自身房间，其他房间继续。未知策略/完整性/加载错误不伪装void。
- 根因定位限定一轮。故障52线程报告结合原生源码与本机main反汇编，主线程栈的 `svc_thread_impl:717` 是 **SVC 0x34 WaitForAddress**（计数器/地址仲裁，可能用于游戏信号量），客体链包含main+4ad6d70 / 4cd68b0 / 4ad1a7c。它并非直接GPU完成等待或LDN socket读；LDN接收是独立 `ldn_reader→recvfrom` 线程。`nvn-present→present_main:6679` 等待 `g_pq_cv`（队列无待取提交或display-link持有），没有栈证据表明卡在GPU完成。主线程已经起了tick7933，不能靠再起一次同帧tick盲目绕过。崩溃报告没有客体堆内存，尚不能恢复该地址等待的对象/生产者；并发调度导致信号量等待链不释放仍是假设，不据此修改时钟或提高阈值。
- 单房对照沿同一District00、8000/相同基线/角色流程启动，`work/a5/one-round-diagnosis/normal/`，在持续STEP时自动对两端执行macOS sample，原始正常栈留在work。此次不开展第二轮根因追踪；能从这一轮确定才修，否则保留证据并用容错擂台继续。
- 独立调度器已实现：原生日志含 `FATAL RL_STALL` 才归类watchdog void；清理中的预期SIGABRT错误仍保留。新尝试独立目录，void不计胜/负/平分母，完成后补开同逻辑局。按实际最后成功ACK计算三/四房重叠，不能把无进展的120秒算成并行进展。超void预算或四房早期比率超限只停止新提交、排空当前房间，四房降三房时全新跑100局，不混算样本。
- 组件测试现11项通过，含真实run_match失败分支的watchdog/任意错误区分、cleanup错误保留、单房void不取消他房、配对补跑、超预算排空、HUD/比分换边汇总、最后成功ACK截止的三房重叠；两弱基线实际sandbox测试1项通过。它们不代表原生百局已通过。正式入口 `bash tests/run_all.sh --milestone a5 --games 100 --parallel 4 --fallback-three` 将先跑全部既有回归，再开始擂台。
- 一轮栈对照结论：正常District00客端在持续推进时也短暂经过相同main+4ad6d70/4cd68b0/4ad1a7c → WaitForAddress链，并可继续构建/提交图形命令；正常sample还包括合法预算边界WaitSynchronization与短暂GPU sync等待。故障报告没有客体堆快照，不能仅凭相同等待栈认定哪个信号生产者缺失。根因未闭环，不修改原生时钟/等待语义；单轮结论与两端正常sample SHA在 `work/a5/one-round-diagnosis/conclusion.json`。按指挥方限定，到此结束根因工作，继续容错百局。
- 单房正常对照最终通过：`work/a5/one-round-diagnosis/normal/result.json`，11508受控帧、双方原生Winners、互反比分1.6:1.7、errors=[]，两个宿主优雅清理。它是本轮定位对照，不混入正式100局。容错正式入口的全部公共回归、导航/接口组件、A5组件11项和实际sandbox1项通过；四房原生正式运行目录 `work/arena/tournament-20261019-021200-165802/`，日志 `work/a5/acceptance-tolerant-100.log`，开始时冻结源码/二进制/三图数据，执行期间不改策略与运行时源码。

### A5 当前真正新卡点：Winners 双端结算涂地比分相差0.1个百分点（停止，未签收）

**本轮没有再发生watchdog卡死；新的停止原因是结算真值一致性。正式100有效局未完成，A5未PASS，不创建签收commit/push。已实现的void容错/测试/文档保留未提交；A4远端 `91cd943be7ea5f4eee69097fdc9124d475c472b0` 不变。按“真正的新卡点才停下”到此停止，没有第二轮死锁定位、没有请求其它模型，没有启动A3b/T1。**

- 命令 `bash tests/run_all.sh --milestone a5 --games 100 --parallel 4 --fallback-three --timeout 7200`，日志 `work/a5/acceptance-tolerant-100.log`，退出1。结果 `work/arena/tournament-20261019-021200-165802/result.json`：**32有效、0 void、1独立完整性失败、3取消**；`phase_passed=false` / `full_a5_passed=false`。void率按授权口径为0/(32+0)=0%，不把其它错误或取消塞入分母。此前首次四房烟测的watchdog不是本轮样本，不混算。未触发四房void率超限，故未启动三房回退。
- round-032-attempt-000（District00，rush在0端 / high-ground在1端）在 **11496受控帧**双方均到原生Winners，`phase=3`、`score_valid=1`、`turf_valid=1`、`score_units=1`。0端原生比分 **[0.699999988,1.29999995]**，1端 **[1.39999998,0.699999988]**；反序差约 **[0,-0.10000003]个百分点**，超过既有0.002容差，抛 `AssertionError('final scores disagree between peers')`。两端胜者方向虽相同，但不能把此局当成已通过互反比分校验。该场会话 `work/tests/m6-2p-20261019-045052-975411/`，两端PID30003/48498。样本帧25811/21167，按本端RL_ATTACH帧14519/9876换算是11292/11291；结算之后仍持续保留差异，不是读取到了局内零默认值。
- 原生屏障JSON保留双方所有阶段/比分/有效位，补充 `.../round-032-attempt-000/score-disagreement.json` 包括首次出现比分帧、最终快照、反序差及原始trace SHA256。该assert在Winners图像单独保存之前失败；保留的38张周期/事件图并不宣称是两端最终Winners的人工截图验证。没有用截图缺口猜比分，也没有修改旧结果或放宽容差。
- round-033/034/035 的 `cancelled=true`，是全局完整性失败后的回收，无独立RL_STALL，不当作另外3次原生崩溃。授权的watchdog void分支不会取消其他房；此次是未授权为void的新完整性错误，按既有错误隔离规则停止。32有效局全部成对换边并覆盖三图；root诊断单房正常局不计入32局。
- **待验证假设**：双端百分比文字正落在舍入边界、双方涂地/结算快照未完全同步，或原生formatter的取值侧/采样归属存在边界差异。当前仅有一例0.1个百分点差异，不能判定为单纯显示误差，更不能据同胜者方向自动认定可靠比分。后续应先对照同局原生formatter参数、结算状态与网络涂地同步；是否采用单一裁判端或容忍显示精度，需要明确口径后再改，当前不自作扩大void定义。

本轮 **32局部分统计，仅用于保留证据，不是百局结论**（95%双侧Clopper-Pearson，本轮无平局）：

| 示例 | 胜/负 | 胜率 | 95%区间 | HUD敌方倒下 / 自身倒下 | 敌方 / 自身环境死亡 | 平均结算涂地百分点 |
|---|---:|---:|---:|---:|---:|---:|
| rush / 直冲 | 4/28 | 12.5% | 3.5131%–28.9948% | 3 / 3 | 0 / 0 | 1.0250 |
| high-ground / 占高台 | 28/4 | 87.5% | 71.0052%–96.4869% | 3 / 3 | 0 / 0 | 1.9719 |

- HUD倒下包含未分类原因；环境子集0表示本轮位置规则没有识别到环境死亡，不能推成所有倒下均有精确击杀归属。A3b实时paint/knockdowns继续unknown。每局两侧实际比分留在各自result，均值不是归一化到双方和100%的比分。rush结算范围0–1.8，high-ground 0–4.6个百分点。
- 正式运行总墙钟 **10743.3051秒（2小时59分3.3秒）**；有效局含加载平均 **1200.9348秒**（1170.1789–1248.2311），受控至Winners平均 **673.3479秒**（617.9818–711.5908）。并行时逐局耗时之和不是整体墙钟。9段实际八宿主ACK公共重叠累计 **5124.3368秒**，不是仅设置四worker。
- 36个会话 / 72个宿主日志末尾均确认优雅退出，所有air/策略子进程/协调器已回收；共 **20008次**资源采样，最高pressure2、新增swapout0。冻结的31项原生二进制、arena/rl源码、三图navigation/sight hash全部一致；原件/参考存档仍为 `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。没有提交游戏资产、画面或原始记录。

## 2026-10-19：按新比分口径保存 A5 partial，准备保留33局续跑

- 本节覆盖上一节比分一致性停止线：双端本地结算比分允许舍入/同步差，**胜者一致即有效**，比分取双端按角色对齐后的算术平均；保存原始两对比分、对齐差值、各端胜者。最大绝对差 **>2个百分点** 标suspect但仍有效；只有胜者不一致（含一端平局另一端有胜者）记比分void，与watchdog void合计。有效局suspect率和有效+void分母的void率分别输出；不再因小比分差取消整批。
- 按用户明确指示先创建 **A5 partial**：容错调度、两个弱基线、规则/断点组件与数值结果入库，仍不标完整A5通过。公开数值检查点 `arena/results/a5-partial-20261019.json` 保存原round-000～031全部32局，并从旧原生屏障重新核验两端Winners，将round-032按新规则计入：双端0.7:1.3 / 1.4:0.7，平均 **0.7:1.35**，差0.1个百分点，suspect=false。round-032 HUD计数从同一完整屏障序列重建，双方敌/自身倒下均0；原失败result/trace保持原样。
- 检查点现 **33有效 / 0 void / 0 suspect**，直冲4胜29负、占高台29胜4负。旧取消的round-033/034/035保留独立审计，不进胜负/void分母。原始结果和各场trace SHA、未变的原生/技能/可见性/地图runtime SHA及策略源码SHA供续跑前验证。只有已授权变更的runner/schedule/statistics不要求与旧协调器源码hash相同；没有更换原生、时钟、策略或地图来迁就旧结果。
- `--resume` 先验证配对地图/角色、比分判定、native Winners、策略/证据/不可变runtime hash，排除已有效逻辑局后再提交。因此只需新增 **67有效局（round-033～099）**，不会重跑原32局或round-032。旧取消的33/34/35以attempt-001补跑。若将来四房void率触发三房回退，也保留所有已有效局，只补剩余局；分段保留并行对比和实际ACK重叠。总耗时累计实际运行段，排除会话间人工等待。
- `.venv/bin/python tests/test_a5_components.py` **15项通过**，含小差取均值/原值保留、>2与恰好2边界、换边胜者、平局分歧void、NaN拒绝、已有33局不重复提交、取消尝试编号、检查点重复/比分篡改/证据变更拒绝；两个实际sandbox基线测试1项通过。原生遗留33局已逐项从证据重判；没有声称新增67局已完成。
- 续跑命令为 `bash tests/run_all.sh --milestone a5 --games 100 --parallel 4 --fallback-three --resume arena/results/a5-partial-20261019.json --timeout 7200`。partial先commit/push核对远端，再执行上述入口。游戏原始状态、地图/资产、画面、线程栈仍只在ignored work；提交的结果只有数值与hash/相对证据引用。
