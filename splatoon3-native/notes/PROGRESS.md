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
