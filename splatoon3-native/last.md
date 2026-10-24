# run73：方向001定位到错轴/反向，002复测已准备（2026-10-24）

本轮仅离线分析和修Python/profile，不开SDL设备或游戏、不训练；policies/宿主/原存档未改，T1/S1暂停。

- **pitch**：003抬头为SDL x+，001送HID X+却令真实eye→at仰角下降。3个无右摇杆/未到上限窗口，各滞后下方向均为负；需要取反。
- **yaw**：旧profile把SDL y送HID Y，但相同HID实现的独立单轴原生校准主要响应HID Z。001原始y峰7.903rad/s、注入Y峰1.258turns/s，不是信号过小；两段单位转换误差均0，没有gyro软件死区/±8裁剪，日志确认最高20/20且gyro_on=1。
- **比值**：001干净窗口镜头/手柄yaw绝对角速度比0.30–0.35；正确Z轴的+5稳态预计2.393，不额外放大。pitch用真实仰角量得约2.04–2.53的负向比值（墙钟/逻辑和0–8f滞后范围）；不是把控制字段当弧度。
- **修正**：`HID XYZ = [-SDLx, +SDLz, +SDLy]/2π`，物理识别与注入矩阵分开；新profile `work/rl-demo/direction-check-001-audit-r2/profile.json`，仍只限`--direction-check`。终端显示物理方向+HID值，原生pitch字段改标控制量。
- **验证**：32项组件/静态检查；001四份逐帧原件、旧profile、原生host.log和宿主SHA均保留。002未运行，增益预测不冒称用户复测通过。

[可直接复制的002命令](rl/demo/开录清单.md) · [完整分析](notes/rl-demo-gyro-20261024.md) · [汇总JSON](notes/rl-demo-gyro-20261024.json)。用户启动1房完整渲染、.52脚本、主武器only，90秒；Minus/Plus未确认，用Ctrl-C/STOP结束。到此停下等用户。

---

# run72：003复核与游戏内方向短测已备好，等用户启动（2026-10-24）

本轮未打开SDL设备、未启动游戏、未训练。原003四文件SHA一致，全部保留。关键按键/pitch通过；**yaw/roll按首次动作仍有轴向冲突**，不能据后段峰值升级确认。

- 首次越0.35rad/s：yaw_left先x−、yaw_right先x−、roll_left先x−、roll_right先y+。后段y−/z−可与SDL约定相容，但不等于首个动作闭合。
- 临时短测profile：`work/rl-demo/controller-check-003-rechecked/profile.json`。pitch=x+沿用已确认；yaw=y−、roll=z−明确为SDL假设，`complete=false / scope=direction_check_only`，只有显式`--direction-check`可用，普通录制拒绝。
- 引导已锁定首次动作/30ms确认，不被大幅回位改写；首次混轴/错误轴直接记未确认。提示“到位保持，等✓再回正”。支持`--only gyro/buttons --base-profile ...`，保留其余项目证据。
- Minus/Plus/十字上未确认，未回填默认值。短测用Ctrl-C或`touch work/rl-demo/direction-check-001/STOP`；不依赖组合键。
- 29项组件、静态检查、三项CLI帮助通过；用户画面方向实测仍待完成，不冒领物理/性能验收。T1/S1暂停，policies/宿主/原存档未改。

**下一步直接命令见[开录清单顶部](rl/demo/开录清单.md)**：capture完整渲染隔离宿主，1房水刀vs.52脚本，主武器only，最多5400帧（约90秒，不含起机），每0.25秒打印输入方向/原始IMU/原生镜头角度变化。用户独立终端运行，画面出现ZR发射出生后核对左右/抬头低头。

[完整报告](notes/rl-demo-direction-20261024.md) · [003复核数值与SHA](notes/rl-demo-direction-20261024.json)。本轮停下等待用户。

---

# run71：USB Pro 引导自检已修好，等待用户重跑（2026-10-24）

只修手柄工具和录制端校准接入；未读取实时手柄、未启动游戏、未训练，T1/S1暂停。

```sh
.venv/bin/python -m rl.demo.controller --out work/rl-demo/controller-check-002
```

按终端提示逐项操作，约2–3分钟；动作慢可加 `--timeout 20`。先静置，再18个印字按键、8个摇杆方向、6个转动方向；识别或超时自动推进，项目之间松开回中。002已存在则改003，001原件及SHA保留不覆盖。

- **原件复核更正**：完整001 JSONL实际有axis4/5各32767→0事件，旧ZR/ZL输出也曾置1。不是“完全没读到”；10Hz抽样终端不能代替完整原件。左右印字是否对应仍等引导确认，不凭回忆顺序自动交换。
- **读取/映射**：显式保存trigger轴、21项SDL按钮及raw joystick；印字B跳跃/ZL潜墨/ZR开火/R副武器/RS大招。引导生成实际映射，不混用SDL位置名；扩展截图键纳入测试。
- **漂移/方向**：默认0.15径向死区，静置校中心/IMU零偏，原始和处理值都录。陀螺仪逐轴正反验证；歧义、重复绑定和超时标未确认。
- **结果**：终端结论表＋`report.md`、`summary.json`、`profile.json`、原始`samples.jsonl`。仅`complete=true`的profile可显式加载到录制命令；原生画面方向仍需短测。
- **检查**：26项组件全通过，静态检查、两个CLI help通过；无物理自检通过的冒领。

[中文操作清单](rl/demo/开录清单.md) · [详细报告](notes/rl-demo-controller-20261024.md) · [首次原件审计JSON](notes/rl-demo-controller-20261024.json)。本轮到此停下，等待用户再次自检。

---

# run70：周期墨图与开录准备完成，未训练（2026-10-24）

新宿主：`work/rl-demo/ink-recording-host-r1/dmhost-demo`，用法见[中文开录清单](rl/demo/开录清单.md)。USB手柄物理轴向仍等用户回来确认；本轮没有操作手柄或训练。原生最多1房，全部自建房间与远端检查均已结束，T1/S1保持暂停。

- **墨图**：每30f异步读回1600²目标，逐局验证原生UV表；完整局Winners/11510present，369个快照、738张原始目标图，最大间隔30f，新增swap0。墙/歧义/无帧继续mask。
- **实时性**：同输入短测显示中位均60，关闭/开启读回的均速59.92/59.99、1%low52.94/59.01；软件延迟P50/P95为49.69/50.91→57.79/59.90ms。完整局显示59.65均速、1%low39.74，仍有抖动；软件延迟41.64/52.50ms。不承诺全程锁60，不慢放。
- **完整基线补测**：同实时脚本关闭/开启读回，显示均速59.62/59.65，1%low均39.74；软件延迟41.44/53.09→41.64/52.50ms。低帧抖动两者一致，未见新增读回降速，推荐每30帧。
- **动力学**：三角面支撑、+5右摇杆非线性/9档版本、潜墨跳跃/持枪移动和显式发射重生模型。原r11全自由位置误差19.88/24.28u→6.58/20.93u；原生镜头归因6.37/20.80→6.33/8.90。独立录像也有改善，未按整局轨迹拟合。
- **BC**：5398个脚本候选；359帧原生minimap、324帧射线墨色有效，修复采样相位；观测仍直接同步原生、积分0步。完整墨图/武器/通用弹体与镜头资格继续保留，`ready_for_training=false`。
- **检查**：本机85项（84通过、1CUDA跳过）＋11T1组件；asuka0新配置4096局含完整观测292159环境帧/s，1484MiB allocated/2792MiB reserved；4局随机180秒、4项CUDA地形检查通过。

详细前后对照、边界与原件SHA：[notes/rl-demo-ready-20261024.md](notes/rl-demo-ready-20261024.md) / [JSON](notes/rl-demo-ready-20261024.json)。全部录像/PNG/BC/三角面及远端数据留私有work，不提交；正式宿主、run67宿主与原存档SHA不变。

---

# run69：原生交火真值已接入，完整训练就绪仍未签收（2026-10-24）

本轮不训练、不需手柄；最多同时1房，全部自建原生进程已退出。run67人玩宿主、正式arena/A8宿主、GPU动力学、policies和原存档不改，T1/S1保持暂停。

|缺口|本轮结果|仍保留的边界|
|---|---|---|
|交火正例|两段原生中路控制均有可见敌人、轻挥35/满蓄70、.52两枪倒下、潜墨|直接瞄准测量夹具；非玩家示范、非完整Winners|
|水刀主武器阶段|确认蓄力/轻挥/满蓄/恢复及ZL中断，接入HUD和阶段/动画计时元数据|动画截止不冒充输入锁；.52完整内部阶段未签收|
|墨图|恢复温泉峡谷164原生ColPaint片区及UV变换；V翻转、R/G队伍、地面/高台控制通过|只解除实测133/147片区内唯一向上地面、精确读回帧的部分mask；墙/歧义/中间色/无帧未知|
|弹体|原生reset/tick/release、武器ID所有者、池generation；接入observer0水刀/.52主武器entities|calc前采样、速度因果差分；通用全实体/其他武器/观察端资格未签收|

原全图XZ墨图公式在高台错1467px；原生片区147变换预测误差约1.59px，像素处为R255/G0。四个地面控制归片区133；未将全164片区或包围盒都升级成真值。

最终私有观测候选共**7218**：

- `work/rl-demo/truth-bc-combat-qualified/`：3004样本，594样本看见敌人、18样本看见弹体；6个精确帧解除部分原生minimap/射线墨色mask。
- `work/rl-demo/truth-bc-ink-qualified/`：4214个逐帧诊断样本，11个minimap/10个射线墨色帧。所有直接瞄准动作标签`action_labels_trainable=false`，不能用于模仿人的操作。
- 原生交火：`work/a6/d3-truth-r1-20261024-031423-824512/`、`work/a6/d3-truth-r3-20261024-033500-389230/`。
- 向下涂地：`work/a6/d3-truth-ink-r4-20261024-034156-335379/`；UV派生数据只在`work/rl-demo/truth-ink-mapping-r1/`，不提交。
- 截图/射线/entities/HUD/minimap自查：`work/rl-demo/truth-qa-qualified/light-before.png`、`light-after.png`、`full-before.png`、`full-after.png`、`cancel-before.png`、`cancel-after.png`。

**ready_for_training=false**：连续完整世界墨色、全曲面归属/墙面、通用实体、倒下后的镜头等未闭合；当前片段又是主动截断的理想瞄准夹具。保留逐格/逐通道资格，不把未知占位当中立/空/idle，也不跨帧借用稀疏墨图。57项CPU组件+11项T1组件、静态检查和源SHA审计通过；单房峰值约6211MiB，新增swap0。保护宿主、原存档、两份原始场景/Bootup资源SHA不变。

[完整报告](notes/rl-demo-truth-20261024.md) · [数值与SHA](notes/rl-demo-truth-20261024.json) · [用法](rl/demo/README.md)。源码与文档提交推送；原生数据、截图、派生网格、生成页、宿主均不提交。保留所有原件/中间输出，完成本轮限定接入后停止，不开始训练。

---

# 示范数据：默认状态同步与三局导出完成，完整BC训练就绪未通过（2026-10-24）

默认转换改为只同步原生包位置/朝向/HP/墨量/形态，再计算观测；**不推进GPU物理**。原生eye/at按ACK前一帧因果读取，位置原有1–4帧源年龄保留，不伪称逐帧新测量。timer零后约250帧InGame不再作操作标签，未知墨图/武器/弹体显式mask。

- 三局脚本水刀vs.52均完整Winners、退出0、错误0，原生11511/11509/11510帧；最终**5397/5399/5398，共16194个BC候选样本**，有限值/动作mask/SHA审计通过。样本位置导入残差0仅证明不积分，不证明模拟器等价。
- 原20–24u自由漂移在旧录像复现**19.8779/24.2761u**；原生镜头条件对照**6.3715/20.7996u**。地形/墨色移动/坠落重生仍有明显分岔，未盲调速度或更改GPU动力学。
- 已补原生1600² UV墨目标读回、256²采样、按Player归属的水刀/.52对象与动作快照、弹体阶段候选、逐帧姿态候选。**世界墨图映射、完整武器阶段、弹体活动集合未闭合，ready_for_training仍false**；默认不加allow-approximate仍拒绝导出。
- r2五轴稳态矩阵在r3独立5393窗口yaw/pitch RMSE .0006937/.00020835rad/f；量化均未超档。三局可见敌实体样本均0、HUD倒下0，不是专家交火示范或非空原生实体通过；另有合成可见人/潜墨mask正例。
- **43项组件（29 demo＋14GPU）及11项T1组件通过**；run67/默认/保护宿主、原存档、两原始资源SHA一致。最多1房，全部本轮native已关闭。未训练、未恢复T1/S1、不动policies，数据/BC/截图/网格/生成页/宿主不提交。

[完整报告与动力学校准优先级](notes/rl-demo-data-20261024.md) · [数值/来源SHA](notes/rl-demo-data-20261024.json) · [用法](rl/demo/README.md)。当前最终产物均私有：

- 录制：`work/rl-demo/data-ready/native-survey-full-r1/r2/r3/`。
- BC：`work/rl-demo/data-ready/bc-native-sync-final-r1/r2/r3/`。
- QA：`work/rl-demo/data-ready/qa-native-sync-final-r1/r2/r3/frame-600.png`与`frame-1200.png`。
- 原录像漂移：`work/rl-demo/data-ready/dynamics-original-r11-final/`。

截图/射线大体对应地面、侧墙、远景/天空，保留粗几何与采样时刻限制。所有原生原件和迭代导出保留；源码/聚合说明提交推送后停止。手柄实测等用户回来，当前不需操作。

---

# 人玩实时性收尾：热段约60均速，低延迟43.64ms，全程锁60未签收（2026-10-24）

私有异步条件渲染已消除run66的持续CPU↔GPU predicate等待。同源Submit墙钟中位23.336→2.498ms；原查询/counter/fence回写保留，只改变渲染条件读取。新宿主`work/rl-demo/render-host-r2/dmhost-demo`默认strict，异步必须显式开且正式入口拒绝。正式arena/T1/A8宿主不变。

| 完整局热段 | 原生中位 / 1%low / 平均 fps | 显示中位 / 1%low / 平均 fps | 软件输入→呈现P50 / P95 |
|---|---:|---:|---:|
| 异步、旧6帧追帧上限 | 60.17 / 47.15 / 59.99 | 60.00 / 59.42 / 59.99 | 102.12 / 104.90ms |
| **异步、1帧追帧上限** | **60.43 / 43.29 / 59.95** | **60.00 / 55.64 / 59.95** | **43.64 / 46.13ms** |

热段排前600帧/到10800前，显示1%low只用相邻有效回调；两个完整局均11510帧、全有呈现回调、Winners/错误0。最终capture命令退出0，含strict结算墙钟196.267s/58.645present/s。后台资源采样去掉原2s周期约50ms阻塞，保留原保护阈值/5s超时；1帧墙钟追帧上限降低队列延迟，不改fixed60或复用旧输入。无条件绘制整幅黑屏，已淘汰。

**当前最高完整热段约59.99fps；严格全程60仍未通过**，原生/RPC尾延迟与启动/结算长帧保留。GPU最终中位11.576ms/P95 12.047ms，不再是原21ms条件等待；没有用强制显示/不限帧/慢放冒充60，未继续扩大到内部缩放或GPU回放偏差。

固定1800输入短测：strict vs async双方各405个同源采样帧，位置最大0.004314/0.329906u在原生自身波动包络内，HP/墨量/alive/phase相同。HP全1，没有伤害对照；最终后台采样版相位不重叠，插值保留诊断，不冒作逐帧精确等价。截图中场地/角色/墨色/HUD正常，未宣称所有视角无闪烁。

21项demo组件、11项T1组件和定向静态检查通过；r5/r2身份核验、五保护宿主/两原存档/两原资源SHA不变。最终一房峰值footprint6384MiB，新增swapout0/pressure1；所有自建native/录制进程已结束。没有训练、真人示范或GPU转换，T1/S1暂停，不动policies。游戏数据/截图/录像/生成页/宿主不提交；按新授权提交推送源码与数值报告后停止。

[完整说明](notes/rl-demo-realtime-20261024.md) · [聚合数字/SHA](notes/rl-demo-realtime-20261024.json) · [操作命令](rl/demo/README.md)。原件：`work/rl-demo/async-capture-final-r1`、`async-live-full-r1`；失败/中间项全部保留。截图仅本地：

- `work/rl-demo/async-live-full-r1/screenshots/frame-600.png`
- `work/rl-demo/async-live-full-r1/screenshots/frame-1200.png`
- `work/rl-demo/strict-ref-r1/screenshots/`（对照）
- `work/rl-demo/always-smoke-r1/screenshots/`（淘汰黑屏）

---

# 录制实时性续查：瓶颈定位到条件渲染等待，60fps仍未达标（2026-10-24）

按present interval线索完成三次一房1800-present短测。逐帧记录显示interval全程1，game_fps/Metal target全程60，display link未进30Hz模式；上屏30fps中位数来自16.7/33.3ms等间隔分布。这只覆盖本次夹具，不否定其他场景触发降30Hz。

重放墙钟中位23.62ms，而提交CPU3.66ms、GPU活跃10.19ms；详细叶操作抽样中OP_RENDER_ENABLE占83.6%墙钟、21.62ms/帧、CPU仅0.94ms，事件记录确认大量阻塞fence等待。持续大头是条件渲染CPU↔GPU往返，不是最后commit调用；编译P95为0但会有少数严重尖峰。

原生内部缩放参数名字/解析引用与MiniMap .65示例已找到，普通对战setter/rebuild尚未闭合，未接通0.25–0.5。私有原生颜色分级/bloom强度/默认DOF候选没有有效减掉pass或提速：

| 详细归因短测（link1，稀疏GPU计数） | 逻辑中位 / 1% low fps | 上屏有效样本中位 / 1% low fps | 软件输入→呈现P50 / P95 |
|---|---:|---:|---:|
| baseline | 37.27 / 14.34 | 30.00 / 14.12 | 84.12 / 92.82ms |
| 原生画质参数候选 | 37.46 / 13.29 | 30.00 / 13.33 | 84.17 / 93.14ms |

没有以强制display或不限帧冒充60，没有改条件判定/fence/counter或盲删pass。候选不激活默认；此前完整局仍是当前最好可完整复测证据（逻辑均值38.14、中位39.11fps，link0软件呈现P50 45.47ms），尚非稳定60。真人轴向、物理按钮→光子延迟、原生墨图/武器/弹体真值及BC真实性缺口保留，未训练。

详细报告：[notes/rl-demo-fps-20261024.md](notes/rl-demo-fps-20261024.md)；[数字JSON](notes/rl-demo-fps-20261024.json)；[用法](rl/demo/README.md)。原件`work/rl-demo/pacing-profile-r1/r2`、`quality-profile-r1/r2`及对应session均保留；r1画质覆盖层首次缺Zstd content size启动失败，修复后r2跑完1800帧错误0，失败不混性能。14项demo/格式组件、ruff/compileall/diff检查通过。

保护宿主/存档/原始资源SHA一致，本轮进程结束；不动policies，T1/S1保持暂停，没有网络请求/发布/训练，离线仅本地commit不push。到此停止；更有针对性的后续是分析条件predicate依赖以减少CPU读回往返，并保留相同判定语义。

---

# 示范录制准备：整局链路通过，实时60/BC真实性未达标（2026-10-24）

完成独立USB Pro自检、隔离原生录制夹具、私有trace/输入/状态保存、GPU环境近似回放转换和中文说明；没有训练。已修复摘要字段覆盖、脚本对手出生导航和结算live-agent/API问题，最终一房原生整局双方到Winners，11,511输入区间、错误0，结算0.9%:0.6%。

| 最终完整局 | 结果 |
|---|---:|
| 受控墙钟（含结算） / 总present率 | 309.65秒 / 37.17present/s |
| 暖机逻辑中位 / 1% low | 39.11 / 15.31 fps |
| 有效相邻上屏中位 / 1% low | 40.00 / 14.66 fps |
| 软件输入→对应drawable呈现 P50 / P95 | 45.47 / 50.27ms |
| 近似BC样本 / 分片 | 5316 / 21 |

**当前不适合正式录示范**：未达到实时60，不用慢放替代。降低内部比例/分辨率与阴影后期关闭没有确认适用于当前构建；去冗余CPU诊断、对手headless减绘、present link0已测，RPC分块无收益。计时提示提交/同步仍需定位。USB IMU事件200Hz读通，但物理按键变化和陀螺仪正负未人工确认；软件延迟不是物理按键→光子测量。

转换跑通但ready_for_training=false：原生全图墨色、完整武器阶段/弹体未捕获，minimap/墨色/弹体由模拟近似；自由回放位置均值偏差约19.89u/24.28u，明确不宣称原生一致。动作量化误差见报告，相机拟合秩4/5、未覆盖真人全轴。默认拒绝未合格真人录制及近似转换，诊断需显式选项。

- 中文操作说明：[rl/demo/README.md](rl/demo/README.md)。
- 详细报告：[notes/rl-demo-20261023.md](notes/rl-demo-20261023.md)；数字：[JSON](notes/rl-demo-20261023.json)。
- 最终私有原件：`work/rl-demo/smoke-final-r11/`；近似BC：`work/rl-demo/bc-final-r11/`；手柄：`work/rl-demo/controller-final-r3/`。
- 最终构建：`work/rl-demo/host-r5/dmhost-demo`；摘要/计时/只读传感与trace均随局保存。
- 11新增组件、11既有T1组件、2真实策略worker往返、12帧观测调度物理对照通过；最终原生和BC审计通过。host/存档SHA一致，本轮进程均结束，失败/取消原件保留。

本轮完全离线，只作本地源码/文档commit，不push。没有网络对战、修改policies/原存档或恢复T1/S1，没有训练。到此停止。

---

# RL阶段1恢复：联合能力卡点，已按两轮规则停止（2026-10-23）

阶段1仍未通过，不进入阶段2。按astra-r1与用户追加指示，完成ZR/ZL切换语义、稳定PPO和三种子能力课程。固定21u靶两臂（level/toggle）三个种子sampled/greedy均128/128首次生命KO，均可两满蓄；独立电平也学会，不能把收益归因于toggle单因素。

随机姿态后，25%远靶复习让两个种子恢复远靶，第三个仍失败。随后只延长预算、再只降低复习控制难度，两轮均未改善三种子近/远联合能力，已停止。移动靶、弱攻击、历史/自战训练尚未启动；.52本轮未训练。

正常出生温泉180秒诊断（各角色64局）：

| 种子 | 水刀sampled胜随机 | 水刀greedy胜随机 | 随机对局武器KO / 回血观察 |
|---|---:|---:|---:|
| 101 | 33/64 | 31/64 | 0 / 0 |
| 202 | 30/64 | 0/64 | 0 / 0 |
| 303 | 54/64 | 52/64 | 0 / 0 |

D4近距sampled涂地胜61/64、60/64、61/64，仍0武器KO，不代表对枪通过。202 greedy正常局ZL占比99.926%，最长10,792帧；恢复完整控制后仍未协调。所有自动门false，掩体意图未证实。

本恢复周期24个有效run共150,994,944环境帧，最长单模型谱系20,971,520；run计时合计3590.46秒/59.84分钟（含初探，不含末态资格/全局诊断/开发），峰值allocated2560.30MiB。失败cuDNN eval-mode尝试0更新/32768帧排除，修复后CUDA续训完成，失败原件保留。14项CPU学习组件、14项CPU环境回归、定向ruff/compileall/diff检查通过；旧B模型新终止循环下六类逐局字段完全一致，均10,800帧/180秒。

详细报告：[notes/rl-stage1-restart-20261023.md](notes/rl-stage1-restart-20261023.md)；聚合数值：[JSON](notes/rl-stage1-restart-20261023.json)；用法：[rl/gpu/stage1/README.md](rl/gpu/stage1/README.md)。固定阶段源码/结果分段已推送519f1ec、54680c5；本次另提交复习/审计源码及最终停止报告。私有401文件归档SHA256 `72bb9a7e0f6b46528e529af3dcdc88115d4c1acc1425c38c8de559f9e02251df`，原件和checkpoint保留在asuka0私有根，不提交大型权重或派生数据。

本地回放已实际播放/暂停/seek F1800/Alpha跟随，脚本error 0：

- `work/rl-stage1-restart/preview-normal-r1/index.html`，6,294,765 bytes，明确标注阶段1未通过，未发布。
- 截图`work/rl-stage1-restart/replay-normal-r1.png`。
- 固定靶曲线`work/rl-stage1-restart/fixed-charge-curves-r1.png`。

最终远端无本轮训练/评估进程，tmux无server、GPU compute列表空；状态原件`work/rl-stage1-restart/closeout-remote-r1.json`。自建浏览器标签与8897临时服务关闭。没有启动原生/T1/S1/阶段2，不动policies/原存档/VPT；游戏资源/网格/生成页/截图/checkpoint不进git。FOV轴向仍是假设，实图4.34u粗几何偏差保留。

---

# RL 阶段1：未通过，已按两轮规则停止（2026-10-23）

实现了主武器only的GPU PPO自我对战、158万/163万参数共享GRU、历史池、action mask、CSV/Elo和可播放回放。两轮有效训练各32,047,104环境帧：

| 同种子、每角色64局 | 未训练水刀赢随机 | 训练后水刀赢随机 | 未训练/训练后.52赢随机 |
|---|---:|---:|---:|
| A 基版 | 55/64 | 2/64 | 64/64 → 60/64 |
| B 自身动作反馈＋输入先验 | 34/64 | 12/64 | 64/64 → 64/64 |

两轮均未学出收益，停止续训，不进入阶段2。B的100% .52胜率在初始化已达到，不能算RL成果。D4近距61/64涂地胜但水刀0伤害/0KO；残血潜墨回血观察0，掩体意图未证实。曲线无NaN但行为退化，不能签收基础对枪。错误自落击杀奖励pilot16.06M已修复并排除，原件保留。

有效64,094,208帧是两个独立模型之和，非单模型64M；有效训练墙钟1067.52s（17.79分钟，不含评估/开发），峰值CUDA allocated2805.75MiB。CPU最终9项学习检查、原14项CPU/CUDA环境回归和GPU击杀归因控制通过。阶段0仍按用户验收接受；FOV纵55°/横85.56559°为待原生核验假设，实图4.34u偏差保留。

详细报告：[notes/rl-stage1-20261023.md](notes/rl-stage1-20261023.md)；聚合数值/SHA：[results JSON](notes/rl-stage1-20261023-results.json)；用法：[rl/gpu/stage1/README.md](rl/gpu/stage1/README.md)。源码分段提交推送，checkpoint/地图/日志留`asuka0:~/splatoon3-native-rl-stage0/`私有目录，A/B分别`stage1-credit32-r1`/`stage1-feedback32-r1`。远端driver均exit0，无活动tmux/GPU训练进程；64M续训脚本未启动。

本地私有回放已在showcase实际播放、暂停/跳帧/双侧跟随，无脚本error，未发布：

- 水刀：`work/rl-stage1/preview-feedback-r1/index.html`（6,337,285 bytes）；截图`work/rl-stage1/replay-stamper-r1.png`。
- .52：`work/rl-stage1/preview-feedback52-r1/index.html`（6,378,666 bytes）；截图`work/rl-stage1/replay-52-r1.png`。
- 曲线：`work/rl-stage1/curves-credit32-r1.png`、`work/rl-stage1/curves-feedback32-r1.png`。

未启动原生宿主/T1/S1或阶段2，未动policies/原存档/VPT；未提交游戏资源/派生网格/生成页/截图/checkpoint。

---

# RL 阶段0：环境实现与有界停止（2026-10-23）

独立venv已安装 **torch2.12.1+cu126** 并完成RTX4070Ti真实CUDA运算；原cu128安装PID3407336已核对终止，VPT未使用/修改。源码位于`rl/gpu/`，无训练入口。

- **完整观测吞吐通过**：1024局、2帧决策、每次32×18射线/16实体遮挡/HUD/minimap，三次 **306177 / 306090 / 306124环境帧/s**；413.4MiB allocated / 750MiB reserved。由int64墨图16.7万提升到int8约30.6万，无缩水观测或改20万阈值。
- **数值与稳定性**：14项CUDA单测、8192射线/20步Graph+部分重置、另20步编译离散语义对照通过；S1平地8×120f最大位置1.35e−5u、HP0.20/100；实图粗几何24路线最大4.34u。4局随机策略均180秒、有限值/零和/终止正确，但无交火，不能当战斗质量证明。
- **回放**：GPU trace已在现有showcase本地实际播放到F505、暂停与Alpha跟随；私有页`work/rl-stage0/preview-gpu-r1/index.html`，**5,984,402 bytes**；截图`work/rl-stage0/replay-browser-gpu-r1.png`，未发布。
- **未过项 / 停止原因**：原生+5满推0.0642272rad/f、eye/at已测；两轮只读引用探针未确认55°候选FOV的最终投影轴向，保留accepted=false，按两轮无进展停止房间/地址试探。网络断开未计卡点。另.52仅主武器，副特尚未建模，不能称完整套装。

**阶段0未全门签收，不开始训练，不恢复T1/S1。** 原生测量峰值1房，进程均关闭；远端测试tmux已完成。源码/文档提交推送；游戏参数/派生网格/截图/生成页/wheel均不提交、不删除work。详细证据与后续明确选项见[环境报告](notes/rl-stage0-environment-20261023.md)和[数值/SHA](notes/rl-stage0-environment-20261023.json)。

---

# 历史：RL阶段0早期安装停止（当前状态见上）

阶段0未通过，未开始训练。首次asuka0硬件探测成功（4070Ti 12282MiB、24核、30Gi RAM），私有目录`~/splatoon3-native-rl-stage0`及独立venv已创建。首轮NVIDIA NVRTC依赖4.7/88MB下载超时；第二轮可续传/官方PyPI依赖源已进入889MB torch wheel下载，但SSH再次断开，两次重连均代理握手失败。第二轮安装最终状态及是否仍有有限安装进程**未知**，不能声称CUDA环境就绪或远端已收尾。

按两轮规则停止追加尝试，不改SSH配置/隧道。只有`rl/gpu/`安装脚本、17移动档/双9档镜头/五独立按钮的配置契约；缺少原生+5/FOV标定时拒绝配置。没有GPU模拟器、性能、机制单测、随机局或回放验收。未启动任何游戏房间、未向远端拷贝游戏参数/网格，policies/宿主/原存档/T1/S1均不动。

说明与门状态见[notes/rl-stage0-20261023.md](notes/rl-stage0-20261023.md)，原件`work/rl-stage0/bootstrap-blocker-20261023.json`。远端保留`install-torch.log`、`install-round2.log`，恢复连接后先核查已有进程/日志/可能的`cuda-verify.json`，避免重复安装。契约语法/枚举范围/缺失标定拒绝检查与shell语法通过，不能当GPU环境单测。源码与停止报告提交推送后停下。

---

# D4 自动补算交互（2026-10-23）

只改页面展示/任务调度，未启动游戏。更换敌位、四向朝向或手速后，缺少离线完整结果/内存完成缓存时300ms防抖自动补算；新选择直接终止忙碌Worker并拒绝旧请求。地图上方居中显示百分比、格数和秒数；普通可站点优先、首行和后续分块逐步显示，候选①②③及结论随结果更新，结束后自动选择①并重建路线。保留“重新计算”按钮，反查原入口继续可用。关闭图层/换图/切正反查也取消旧任务。

完整结果按地图/敌位/朝向/手速缓存在本次页面内存，切回来即时显示；中断查询保留已收到行并续算；完整路线另有缓存。刷新页面清空，未写存储文件。预算截断与限定外仍为未知，动态①②③只称已计算候选；既有完整查询/冻结排序优先，未改变研究结论。

浏览器耗时（同一Chrome，无游戏；不能混用不同敌态声称加速倍数）：

- 温泉峡谷#779 / +X / 40f：原版完整1580格约15分24–34秒才刷新，最终①#641。新版首批行0.907s、首个可杀点及①4.491s（含防抖），随后继续渐进计算；本次用于快速切换/取消测试，没有把首批时间当完整完成时间。
- 边缘#0 / +X / 40f：新版普通集合718格12.280s、全1580格37.246s。完成缓存切回UI操作33ms；默认普通集合无确认点时明确提示，未知不当失败。
- 普通可站#95 / +X / 40f：首批0.476s、首个可杀点19.170s、普通集合259.029s、全1580格486.102s；完成后自动选①#121，路线/槽量/回放自动出现。跨地图切回该完成缓存的UI操作243ms，不重新算。

完整精算依敌态仍可能分钟级。当前收益是先显示、可取消、复用已算结果，并非把复杂模型全图压到10秒。

生成页 `showcase/index.html`：5,291,854 bytes，SHA256 `89e92cc33ebb3a689b994955373275bee531a6426f0d32b5104d3f9cdf8a4225`。未提交/未发布；派生网格、截图、游戏资源均未提交。所有原嵌入数值字段逐项不变，只有展示源码哈希更新；数值Worker核心和`d4_safe_worker.js`不改。未动对战代码、policies、宿主、存档；T1/S1暂停。

验证：24,603项原资源/数值审计，整页JS语法和`node showcase/test_d4_worker.cjs`通过（优先次序、增量行、原索引顺序、未知/预算不变、续算、取消后无最终热图）。Chrome实测敌位/朝向/手速自动触发、快速切换取消、部分缓存恢复、完整缓存命中、完成自动刷新、重新计算按钮。亮暗×3D/2D/390px自查，390px内容宽390，无横向溢出；无页面脚本错误，旧three.js弃用提示单列保留。临时视口恢复，自建页关闭；原件不删。

截图（本地自绘展示，均不提交）：

- `work/showcase/d4-auto-light-progress-3d-20261023.jpg`
- `work/showcase/d4-auto-dark-progress-3d-20261023.jpg`
- `work/showcase/d4-auto-light-progress-mobile-20261023.jpg`
- `work/showcase/d4-auto-dark-progress-mobile-20261023.jpg`
- `work/showcase/d4-auto-light-progress-mobile-2d-20261023.jpg`
- `work/showcase/d4-auto-dark-progress-mobile-2d-20261023.jpg`
- `work/showcase/d4-auto-dark-progress-2d-20261023.jpg`
- `work/showcase/d4-auto-light-complete-3d-20261023.jpg`
- `work/showcase/d4-auto-light-complete-mobile-top-20261023.jpg`
- `work/showcase/d4-auto-dark-complete-mobile-top-20261023.jpg`

审计原件：`work/showcase/d4-auto-baseline-20261023.json`、`d4-auto-first-result-20261023.json`、`d4-auto-browser-final-20261023.json`、`d4-auto-data-audit-v4-20261023.json`、`d4-auto-check-v4-20261023.json`。仅展示源码与本报告提交推送，完成后停止。

---

# D4 展示辨识修复（2026-10-23）

仅展示层，未启动游戏。D4开启自动使用中性灰底；绿/琥珀/红结果格、白色偷袭点、未知虚框、不可达不填色。地图左下常驻图例，上方直接显示敌位/朝向/最佳①/剩槽/偷袭或暴露。大号①②③图钉可点，默认温泉#634自动选中并显示路线；敌人具有人形、箭头和180°半圆。手机2D自动纵向排图，首屏可见结论、图钉和图例。空结果明确提示换朝向；关闭D4恢复原底图和控件。

图钉标签只从原有完整查询复制；模型/原始数据/研究结论不改。所有原有payload字段逐项一致，18个冻结top1/top2保持一致，11个已有完整敌态有排序标签；未完整计算只称候选。代表#634仍124f、69.90%、零钩偷袭；完整D4状态沿用下方既有记录，不因视觉修复改变。

`showcase/index.html`已重生，5,283,490 bytes，未提交/未发布。整页JS语法、原字段不变/标签原件/冻结点审计及24,591项页面检查通过。三图默认点、无确认点提示、图层开关恢复、2D/3D俯视、亮暗及390px通过；390px内容宽390，本页无控制台错误（浏览器扩展日志另保留）。临时视口恢复，自建页关闭。未动policies、存档、宿主或对战代码；T1/S1暂停。

最终截图（均在work下，不提交）：

- `work/showcase/d4-visual-final-light-3d-top.jpg`
- `work/showcase/d4-visual-final-dark-3d-top.jpg`
- `work/showcase/d4-visual-final-light-2d.jpg`
- `work/showcase/d4-visual-final-dark-2d.jpg`
- `work/showcase/d4-visual-final-light-mobile-3d.jpg`
- `work/showcase/d4-visual-final-dark-mobile-3d.jpg`
- `work/showcase/d4-visual-final-light-mobile-2d.jpg`
- `work/showcase/d4-visual-final-dark-mobile-2d.jpg`

审计：`work/showcase/d4-visual-data-audit-v7-20261023.json`、`d4-visual-check-v7-20261023.json`、`d4-visual-browser-final-20261023.json`，绑定最终页SHA。详情见showcase/README.md；源码提交推送后停止。

---

# D4c 限定交付 / 停止（2026-10-23）

**新216全部闭合；完整D4未闭合。** 最初被打断两刀result/steps/双方host.log原件与SHA已保全。优先查横5球左右/纵7球上下裁剪，最终物理数组身份、核心共享及接触分半仍未闭合；未把领域知识误写为已否定。四刀机制预算用完后按授权切换接触确定不相交、整波墨刃场地清晰的有限路线。

三图各3敌态×top1/top2/对照×8：216有效（217尝试，1发动前进程失败，原例按规则只重试一次成功），0对战未决，旧12/机制/资格0复用。优选144/144先杀，对照0/72；各敌态8/8、8/8、0/8。原生KO124–128f，剩槽69.074–69.815%；队列墙钟6时28分47秒、峰值3房。原驱动退出0、stop_reason=null；当前无dmhost，143项原件/保护宿主/冻结输入/模块SHA一致。

**边界**：所有27点为零钩满蓄接轻斩40f，不证明飞索切入/连钩。原生.52固定脚本直线枪口跟瞄未补下坠，不是理想防守方/玩家胜率。实际姿态可判136次，16次模型原生不一致、80次未知均保留。接触规则、极限连钩、完整D4及全局最优仍未闭合；不恢复T1/S1，不改策略/原存档/正式默认宿主，不启动下一阶段。

[交付报告](notes/d4c-delivery-20261023.md) · [216数值/逐例原件SHA](notes/d4-blade-only-native-20261022.json) · [两半机制](notes/d4-halves-20261022.md)。原件 `work/d4/restart-v4/chain-preservation-v1.json`；正式批次 `work/d4/restart-v4/blade-native216-v1/batch.json`；最终完整性 `work/d4/restart-v4/integrity-20261023-final.json`。

生成页 `showcase/index.html`，5,259,960 bytes（<10MB）；11完整限定查询/14,771起点行，并非63,328组合全量完成。支持敌位/四向/四手速正反查、3D路线/暴露/槽曲线/步骤回放、旧均匀先验附录和新原生实数表，未知不涂失败。Python/浏览器72单刀/288终结/45查询/3预算恢复通过；最终24,526项格值/trace/来源/资源审计通过。点634复核124f/69.90%/零钩偷袭，控制台无错误，390px内容宽390无横向溢出。页面未发布。

最终截图（本地自绘页面，均不提交）：

- `work/showcase/d4c-final-map-light-20261023.jpg`
- `work/showcase/d4c-final-map-dark-20261023.jpg`
- `work/showcase/d4c-final-native-light-v3-20261023.jpg`
- `work/showcase/d4c-final-native-dark-v3-20261023.jpg`
- `work/showcase/d4c-final-native-mobile-20261023.jpg`

审计 `work/showcase/d4c-final-check-v2-20261023.json`，UI摘要 `work/showcase/d4c-final-browser-20261023.json`，二者绑定最终页SHA。生成页/派生网格/截图/游戏资源不提交；源码和文档分段推送，本轮在最终提交推送后停止。
