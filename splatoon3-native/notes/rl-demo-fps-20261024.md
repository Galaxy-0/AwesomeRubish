# 录制实时性续查：本次没有降30Hz，持续超时主要在条件渲染等待

2026-10-24，接用户/Claude的present interval线索继续。**没有达到实时60，也没有新的已确认有效减载方案。** 本轮三次1800-present短测与一次启动失败均保留；短测按max_frames结束，不是完整局/Winners或等价性验收。此前完整录制链路结果仍见[准备报告](rl-demo-20261023.md)。本轮没有训练、真人示范或T1/S1。

数字与来源：[rl-demo-fps-20261024.json](rl-demo-fps-20261024.json)。源码在`rl/demo/`，宿主仅构建到新的`work/rl-demo/profile-host-*`，人玩完整渲染/headless对手A8的边界保留；默认录制宿主r5、正式宿主与原存档均不覆盖。所有输入仍是脚本诊断。

## 1. present interval逐帧时间线

代码核对确认：`hle_nvn.c`的game模式在interval≥2持续一秒后，可由`nvn_game_fps()`令Metal目标降到30；interval回1则回60。**机制存在，但本次夹具没有触发它。**

独立诊断构建在每个present记录原始interval、latched interval、game_fps、Metal target_fps、模式和单调时间戳。三次人玩侧分别记录4733、3408、3518条（含起机到受控段），两侧原始interval全程1，game_fps/target_fps全程60、display_mode=0（game），没有1→2或60→30事件。display link各次只记录0→1，没有模式3。变化时间线因此只有初始化一行；原始逐帧记录完整留在各session的host.log。

详细归因baseline的暖机上屏间隔，33.3ms有714次，16.7ms有440次，另有少量50/66.7ms等间隔。**30fps中位数来自间隔分布，不能据中位数断言display link已钉到30Hz。** 这不排除其他输入、场景、长局或构建会触发自适应，只覆盖本次复现。

本轮没有使用`DM_PRESENT_INTERVAL=display`、`DM_PRESENT_HZ=0`或强制DM_FPS来制造60证据；输入环境清单和逐帧原生读数均保留。

## 2. 超时拆分

先用低开销子阶段计时`pacing-profile-r1`拆begin/index/replay/commit；再用`pacing-profile-r2`对每300个native帧中的12帧记录叶操作墙钟/线程CPU，排除CALL嵌套的重复计时。稀疏GPU encoder timestamp另取两个12帧窗口。它们是诊断，有测量开销，不作无插桩性能认证。

低开销构建人玩侧，受控帧600–1799：

| 计时 | 中位ms | P95 ms |
|---|---:|---:|
| 整帧present调用间隔 | 26.231 | 32.467 |
| NVN录制接口墙钟 | 0.733 | 0.933 |
| present线程CPU（含提交） | 3.999 | 4.487 |
| 全进程CPU合计 | 16.481 | 40.175 |
| Submit墙钟 | 23.660 | 27.223 |
| Submit线程CPU | 3.659 | 4.097 |
| begin | 0.028 | 0.042 |
| index | 0.000 | 0.000 |
| 命令重放 | **23.617** | **27.182** |
| 最终commit | 0.011 | 0.016 |
| GPU反馈活跃时间累计 | 10.185 | 13.912 |

暖机1200帧整帧和Submit/重放全部超过16.667ms；已回填的GPU活跃累计样本全部低于16.667ms。不是仅少数编译尖峰拖低平均，也不是CPU执行指令持续用满约26ms。对手侧重放中位21.584ms、CPU2.840ms、GPU9.069ms，结论相同。

全进程CPU含游戏工作线程、驱动和回调，是多线程CPU时间合计，不能与墙钟相加。整帧减重放的残差还含其他接口/RPC/调度，不能直接冒作纯游戏逻辑耗时；本轮未完成每个游戏工作线程的独立CPU归因。

第二轮48个暖机抽样帧的叶操作：

| 人玩侧操作 | 每帧次数 | 墙钟ms/帧 | CPU ms/帧 | 抽样叶操作墙钟占比 |
|---|---:|---:|---:|---:|
| **OP_RENDER_ENABLE** | **156.54** | **21.621** | **0.938** | **83.60%** |
| OP_DRAW_IDX | 525.29 | 1.969 | 1.979 | 7.61% |
| OP_UPDATE_UB | 451.81 | 0.475 | 0.478 | 1.84% |

线程CPU与墙钟为不同计时器，极短累计可能CPU略高于墙钟，不能逐项相减为负等待。对手侧OP_RENDER_ENABLE为19.275ms/帧、CPU0.800ms、占83.29%。

源码中该操作为读取条件渲染predicate，遇未完成的producer时会提交并等待fence，其他条件也会等待已提交的fence后读CPU内存。独立GPU事件诊断窗口人玩侧记录2161次replay_fence_wait，其中925次阻塞，累计902.87ms；上传队列等待24次、阻塞0。**持续大头是条件渲染的CPU↔GPU往返/等待，而不是最后一条Metal commit调用或单纯CPU翻译计算。** 操作窗口与GPU诊断窗口不是相同帧集合，不将902.87ms除以48拼成逐帧时间。

着色器计数暖机P95为0。第一轮出现少数严重编译尖峰：累计library/pipeline创建时间最大2381.6ms、整帧最大1235.5ms；第二轮创建最大19.6ms。创建计时可能含并行工作，不能直接从整帧扣除。现有缓存降低部分尖峰，但不能解决几乎每帧都存在的约21–24ms条件等待；没有声称完成全图全动作预热。

GPU encoder边界span分组（人玩侧诊断24帧）：拷贝/更新B类54.28%，1600×1600涂墨目标17.97%，1280×720主3D颜色+深度7.03%。**这是包含调度/干扰的边界跨度占比，不是独占GPU时间或可直接兑现的加速上限。** 不因其尺寸或耗时便删除被samples/readback/涂墨消费的工作。

## 3. 实际减载尝试与边界

只读检索本机构建11.3.0，找到原生`FrameBufferBase3DRenderScale`、`ResolutionModeController`，以及ResolutionFrameBuffer/Resolution3DLayer的console/handheld参数名。字符串候选指向main+0x1466654/0x1466980（参数解析/反射）、0x1497f38（控制器注册），特殊参数类型名位于main+0x4f6b8f4。MiniMap原生SpecialEnvParamHolder确有0.65的FrameBufferBase3DRenderScale。

**这些不是已经定位并验证的普通对战缩放setter/rebuild入口。** 没有套用D2R的地址，没有把MiniMap的设置误认为普通对战已降到0.65；本轮没有接通0.25–0.5的主镜头缩放。可复现只读脚本`rl.demo.render_research`输出私有JSON，不提交NSO解包、参数文件或资源。

第二条路径通过只读RomFS覆盖层，让游戏解析自身已有字段：温泉Day关闭ColorGrading.Enable、Bloom.Intensity设0；Bootup默认DOFGaussian.Level设0。后者在温泉自身Day里原已为0，不能保证减少比赛期DOF工作。**Bloom强度0不等于已关闭bloom pass。** 修改只涉及既存标量，SARC布局/成员长度不变，逐叶读回与其他内容检查通过；只生成到work/，原始资源SHA未变。

首次覆盖层重压缩时，stdin Zstd帧缺少原生分配所需content size，启动0帧SIGSEGV，main+0x46d3600；该原件保留为quality-profile-r1，不能算性能样本。修正为嵌入明确content size后，quality-profile-r2正常跑完1800个受控present，错误0。新增真实Zstd格式回归检查，避免“CLI能解压就认为游戏能加载”。

测量暖机600帧，主镜头/原生输出仍1280×720：

| 配置 | 逻辑中位 / 1% low fps | 有效上屏中位 / 1% low fps | 软件输入→上屏P50 / P95 ms |
|---|---:|---:|---:|
| 低开销阶段归因r1，link1 | 37.92 / 2.01 | 30.00 / 14.12 | 83.61 / 92.09 |
| 详细归因baseline r2，link1 | 37.27 / 14.34 | 30.00 / 14.12 | 84.12 / 92.82 |
| 同构建原生画质参数候选r2，link1 | 37.46 / 13.29 | 30.00 / 13.33 | 84.17 / 93.14 |

1% low为最慢1%帧间隔均值的倒数。第一轮编译尖峰包含在其1% low中，没有删除。上屏只统计相邻有效呈现回调，空/遮挡回调单列；延迟是软件提交→对应drawable呈现，不是物理按钮→光子。详细归因和候选同样开启稀疏计数，仍不是严格多重复无插桩A/B。

候选逻辑平均35.86 vs baseline35.65fps；draw均值538.22 vs538.27、pass均值106.88 vs106.90，GPU中位10.444 vs10.470ms；OP_RENDER_ENABLE仍21.523ms/帧、占83.60%。**没有确认减掉有效pass或获得可靠吞吐收益，不作为优化默认。** 参数已成功通过该覆盖层启动，但其消费/是否仅改变shader常量未逐字段动态读回，不能宣称所有画质项均实际关闭。

仍以此前完整局作为当前最好可完整复测证据：逻辑暖机中位39.11、1% low15.31、平均38.14fps；link0上屏有效样本40.00/14.66、软件呈现延迟45.47/50.27ms。它没有达到稳定60，本轮未找到更好的已确认方案。

## 4. 后续选项与停止

更有针对性的下一方向是验证条件渲染predicate的producer/alias依赖，评估能否保留相同结果而减少CPU读回往返，或改为设备端条件执行。TIMESTAMP payload与SAMPLES结果不能混淆，也不能仅因旧值为0就跳过producer等待。**本轮没有修改条件判定、fence、counter结果或删渲染pass。** 若继续降低内部分辨率，应沿原生FrameBuffer环境参数追到普通对战的应用/重建入口，再实测尺寸和可见性/比分；仅强改显示节奏不能解决该等待瓶颈。

14项demo/格式组件通过（含3项新增：标量隔离、未知/错类型拒绝、原生Zstd content-size），定向ruff/compileall/diff检查通过。原存档、种子、默认宿主、A8宿主、r5宿主和原始两份RomFS archive SHA均一致；profile构建身份核验通过。所有本轮native/录制进程已结束，失败/原件保留，不动其他人的服务。宿主和覆盖层均未激活为默认，无游戏数据/截图/衍生网格/生成页提交，没有网络请求或push。

原件目录：`work/rl-demo/pacing-profile-r1`、`pacing-profile-r2`、`quality-profile-r1`（失败）、`quality-profile-r2`；对应session路径在result或driver日志第一行，含host.log逐帧时间线、nvn.tsv、gpu-pass.tsv及events.tsv。`render-research-r1`和`render-research-source-r2`保留离线分析；`visual-overlay-r1/r2`保留试验资源，仅私有。到此停止，不训练，不恢复T1/S1，真人轴向/原生观测缺口仍沿用准备报告的未闭合状态。
