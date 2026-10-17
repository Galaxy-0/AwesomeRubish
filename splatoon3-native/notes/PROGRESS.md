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
