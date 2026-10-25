# 人工示范录制准备（只录制，不训练）

2026-10-25（run74）：人工录制的秒级停顿定位为首次shader/pipeline编译和对端帧屏障。`warmup`合并双方与继承清单，可用S-only历史清单补库覆盖，并在初始暂停屏障等待双方原生预热完成。原有NVN计时和每帧日志保留。X现通过demo专属 `observer_buttons` 注入原生bit2，primary_only允许；BC仍六键，记录未表示X。最新003命令见[开录清单](开录清单.md)，证据见[run74报告](../../notes/rl-demo-stalls-20261025.md)。


**最新入口见[开录清单](开录清单.md)**：002方向已由用户确认“正常”；当前Stage1录制用 `work/rl-demo/recording-profile-r1/profile.json`，`scope=primary_only_recording / complete=true`。关键三键/双摇杆/陀螺仪严格校验，Minus/Plus/Up忽略、R/RS屏蔽；full仍需对应scope和R/RS确认。已通过无手柄/无游戏的 `--fixture --dry-run`。控制签收不代表BC训练就绪，不启动训练。

当前为**诊断夹具**：USB Pro Controller摇杆/按键/200Hz IMU已读通；原生1v1、私有输入/状态记录和近似BC转换已实现。2026-10-24的私有异步条件渲染已将热段平均帧率提高到约60；全程锁60、物理陀螺仪方向、原生全图墨色/完整武器阶段仍未签收，暂不开始正式示范或训练。`--allow-unqualified`仍是诊断入口。最新性能与边界见`notes/rl-demo-realtime-20261024.md/.json`，原转换偏差见`notes/rl-demo-20261023.md`。

在项目根运行。完全离线，只用本机已有SDL2和Python环境，不下载依赖，不训练。

## 先验手柄（不启动游戏）

```sh
.venv/bin/python -m rl.demo.controller --out work/rl-demo/controller-check-002
```

USB接好后，按终端逐步提示操作；先平放3秒，逐项检查18个印字按键、8个摇杆方向、6个转动方向。识别/超时自动进入下一项，项目之间等松开回中，不能把一串动作连续提前做完；转到位后保持不动，等✓再回正。SDL负责USB0x80握手、全量报告与IMU子命令。001/003原件保留；输出目录必须全新且位于私有work/。单项重测用 `--only gyro` 或 `--only buttons` 加 `--base-profile`，不会重复其他组的提示。

- SDL IMU为rad/s；宿主为turns/s，除以`2π`。引导锁定首次超过0.35rad/s动作的方向，要求30ms同号、主轴明确；回位/后来的峰值不会改写。混轴/错误轴、反向不一致、无运动均标未确认。旧宿主测试键名不能证明游戏消费轴：本构建单轴数据是X负对应抬头、Z对应水平转动。新profile用独立`gyro_native_matrix`分离SDL物理识别与HID XYZ；游戏画面仍需复测。未载入profile时保留旧的临时换轴，不能当物理校准结论。
- SDL以 `SDL_GAMECONTROLLER_USE_BUTTON_LABELS=1` 按Nintendo印字解释面键；标准映射B=1、A=0、X=2、Y=3。扳机是独立axis4/5（0或32767），不在 `all_buttons` 内。引导实测映射覆盖默认值，包括可能的左右互换；SDL映射/版本变化会拒绝旧profile。完整读取运行时21按钮枚举和raw joystick通道，包含misc1截图键；不把不存在的paddle/touchpad当成实体按键。
- 游戏语义按印字：ZR开火、ZL潜墨、B跳跃、R副武器/出钩、RS大招、Y回正；阶段1仍屏蔽R/RS。
- 传感事件200Hz，“最新值”约66.7Hz，三子样本随一份USB报告到达，不混称轮询频率。
- 默认**0.15径向死区**，profile另含静置中心校正和噪声建议，按方向保留满推；每条记录同时保留raw/processed。摇杆范围±1，陀螺仪独立支持±8turns/s，不截为摇杆±1。
- 终端和 `report.md` 给出结论表，`summary.json` 含逐项证据，普通录制profile仅关键六键/8方向摇杆/三轴通过且 `complete=true` 可加载；可选未确认键不回填默认值，Minus+Plus需两键均确认。人玩命令加 `--controller-profile .../profile.json`；脚本源不受影响。自由实时数值监视另用 `--raw --seconds 40`，该模式不生成校准profile。
- 离线复核工具：`python -m rl.demo.controller_recheck --source work/rl-demo/controller-check-003 --out work/rl-demo/controller-check-003-rechecked`。如果首次动作证据冲突，仅生成 `scope=direction_check_only`、`complete=false` 的SDL约定假设profile；只有 `capture --direction-check` 显式接受，普通录制拒绝。已有003-rechecked旧profile保留原样；当前002应使用新版gyro_audit输出，详见[方向短测命令](开录清单.md)。
- 本轮未遇权限拒绝。若提示设备不可访问：系统设置→隐私与安全性→输入监控，允许启动脚本的终端/App，完全退出重开。不要给无关程序额外权限。

## 开一局、结束、换对手

已构建夹具`work/rl-demo/host-r5/dmhost-demo`及同目录`modules/`。需要重建时，输出到**新目录**：

```sh
.venv/bin/python -m rl.demo.build_host --out work/rl-demo/host-new --peer-elision
```

只影响headless对手的A8减绘；人玩窗口完整渲染，原生720p上屏，不是几何画面。原宿主及存档不覆盖。构建依赖本机私有阶段0诊断产物，不把它们放git。

原strict宿主诊断录制（保留原语义和原性能；最新近60方案见下方）：

```sh
.venv/bin/python -m rl.demo.capture --fixture --allow-unqualified \
  --source controller --opponent 52 --present-link 0 \
  --out work/rl-demo/my-demo-001
```

画面出现后用ZR从出生发射，正常操作即可。水刀8000、温泉峡谷、180秒涂地，默认双方主武器only，R/RS在输入端屏蔽；灵敏度+5/陀螺仪开启，只改进程内临时设置，不改原存档。

- 正常到Winners自动保存、关闭本局进程。下一局重新运行，换一个输出目录，不复用旧文件。
- 提前结束：终端Ctrl-C，或手柄Minus+Plus；也可`touch work/rl-demo/my-demo-001/STOP`。保存部分记录并标取消，不当完整局。启动期间Ctrl-C/STOP也会取消，只收尾本次进程。
- 换T1策略：加`--opponent policy --policy arena/policies/alpha`（或bravo/其版本目录）。策略仍走公开观测与原沙箱，不读写策略目录。**T1策略的原武器是水刀8000**，此选项对手按其原武器，不能冒充.52；源码哈希随局记录。当前GPU转换仅支持水刀vs.52，对策略水刀局明确拒绝转换。
- `--loadout full`只开启原生完整按键供今后录制；GPU .52副特未实现，转换器拒绝把它标成阶段1样本。本轮没有运行全装备对局。
- `--source script`代替人输入，用于链路/性能冒烟，标`scripted_smoke`，不是人的示范。

## 数据与转换

每局留在指定的`work/rl-demo/.../`，包括：

- `usb-inputs.jsonl`：原始SDL摇杆/陀螺仪/按键与传感时间戳（脚本局为空）。
- `inputs-per-present.jsonl`、`native-barriers.jsonl`：沿用S1输入区间/ACK结构；每present一条，保留双方原始`position_sample_frame`/valid标志；状态编码器通常每4帧才有新样本，绝不伪装为逐帧新测量。
- `trace.json`：既有`inklab.trace.v1`三维回放格式；输入边沿、HP变化/倒下是观察边界，个人K无可靠归因时保持未知。
- `result.json`：完整/取消/错误、时长、双方HUD倒下、结算比分/涂地和宿主/源码身份；其`passed`只表示录制到结算链路，不表示60fps或BC真实性已通过。
- 原生日志/资源记录在`result.session`指向的本次私有目录。`telemetry`另将只读相机/弹体候选简化成JSONL，缺测为未知。

```sh
.venv/bin/python -m rl.demo.analyze work/rl-demo/my-demo-001
.venv/bin/python -m rl.demo.telemetry work/rl-demo/my-demo-001
.venv/bin/python -m rl.demo.convert --recording work/rl-demo/my-demo-001 \
  --out work/rl-demo/my-demo-001-bc --allow-approximate \
  --camera work/rl-demo/bc-lean-r4/camera-response.json
```

转换只计算/导出，不训练；M1默认CPU执行同一torch GPU环境代码，也可未来显式`--device cuda`。2026-10-24起默认`--observation-mode sync`只导入原生状态并计算观测，不积分物理；原混合积分仅显式`--observation-mode hybrid`诊断。
输出分片`bc-*.npz`含screen/entities/mask/hud/minimap、17档移动、9档yaw/pitch、ZR/ZL切换标签及上一物理按键；量化与自由回放误差在`report.json`。相机线性响应需有对应标定，未给`--camera`时仅可用有足够激励的脚本局拟合，不能把低秩拟合当完整标定。

新版BC观测用当前/过去原生位置/镜头/HP/墨量直接同步，使用原生eye/at计算射线。未知墨图/弹体/动作阶段不再推进模拟器补造，而以占位＋质量mask表示。自由回放改为独立`dynamics_audit`，不参与BC观测生成。**没有原生全图墨色真值，minimap和射线墨色尚不能作合格BC标签**；明确`ready_for_training=false`，默认不加`--allow-approximate`就拒绝导出。FOV纵55°/横85.56559°仍是已接受的假设，几何近似偏差保留。

所有数据/网格/生成页/截图/权重不提交，正式arena/T1/proficiency拒绝`DM_TEST_DEMO`及demo宿主。T1/S1保持暂停。

## 实时性诊断续查（2026-10-24）

历史run66逐帧证明interval一直为1、game/Metal目标一直60，30fps上屏中位数不代表被钉30Hz。持续超时主要在条件渲染CPU↔GPU等待；原生画质参数覆盖层未确认减掉实际pass。下方为历史归因命令，结果见`notes/rl-demo-fps-20261024.md/.json`；异步条件渲染续查见下一节。

以下仅为脚本短测，不是人的示范，也不是Winners/等价性验收。每次用新输出目录，一次一房；GPU counter诊断有开销。

```sh
.venv/bin/python -m rl.demo.build_profile --out work/rl-demo/profile-host-new
.venv/bin/python -m rl.demo.profile_run \
  --host work/rl-demo/profile-host-new/dmhost-demo \
  --out work/rl-demo/profile-new --gpu-profile
.venv/bin/python -m rl.demo.profile_report work/rl-demo/profile-new
.venv/bin/python -m rl.demo.render_research --out work/rl-demo/render-research-new
```

`render_overlay --out work/rl-demo/overlay-new`只生成私有资源覆盖层，可用`profile_run --overlay ...`测试游戏已有颜色分级/bloom强度/默认DOF字段。它不是已确认有效的降分辨率方案，不修改原RomFS。不要将`DM_PRESENT_INTERVAL=display`或`DM_PRESENT_HZ=0`当作达到60fps的证据。


## 私有近60fps方案：异步条件渲染（2026-10-24）

仅限用户授权的人玩研究夹具。`work/rl-demo/render-host-r2/dmhost-demo`默认仍strict，必须显式选择`--render-predicate async`；正式arena/T1/A8默认宿主不变，仍拒绝demo宿主。首次重建必须用新的输出目录：

```sh
.venv/bin/python -m rl.demo.build_render --out work/rl-demo/render-host-new
```

构建复用本机私有r5基底和原模块，保护旧二进制；不提交/下载私有材料。异步模式不写游戏predicate、counter或fence；原查询照常执行，只让渲染条件消费最近已完成的值，缺测默认绘制。可能短暂多画/晚一帧裁剪，属于本夹具获准的渲染偏差，不是正式对战语义认证。`always`整幅黑屏，已淘汰，不用于录制。

当前低延迟诊断命令（先保留已有成功整局作为shader预热来源；新机器没有该私有产物时，先脚本冒烟一局）：

```sh
.venv/bin/python -m rl.demo.capture --fixture --allow-unqualified \
  --source controller --opponent 52 --present-link 0 \
  --host work/rl-demo/render-host-r2/dmhost-demo \
  --modules work/rl-demo/render-host-r2/modules \
  --render-predicate async --max-catchup-frames 1 \
  --warm-from work/rl-demo/async-live-full-r1 \
  --out work/rl-demo/my-demo-async-001
```

`--warm-from`只复制上一局双方PSO列表并合并原seed清单到本次私有目录，原文件不改；不保证所有地图/动作已预热。`--max-catchup-frames 1`限制墙钟卡顿后的追帧积欠，减少输入在显示队列中排队；底层仍逐帧输入、原fixed60，不改变游戏时间。兼容旧行为的默认值为6。资源采样已移到独立线程，原swap/内存压力阈值保持；异常或采样滞后超过5秒停止本房，不在输入ACK路径等待系统CLI。

以`--source script`替换controller可测试完全相同的录制入口，不需`--allow-unqualified`；这是脚本冒烟，不是人的示范。独立对拍用`profile_run --fixture-inputs ... --predicate async|strict`，用`logic_compare`保留四帧状态采样时钟/差分，不能把插值当逐帧真值。具体完整局和短测的中位/1%low/平均、软件输入→呈现延迟及原件路径见最新报告；一切60数值都同时报告长帧和缺失回调，不以fixed60或强制display/不限帧冒充墙钟60。


## 示范数据：原生同步与原生字段补采（2026-10-24）

三局完整脚本录制已导出16194个BC候选样本；**ready_for_training仍false**。原生世界墨图映射、完整武器阶段和弹体活动集合还未闭合，详见`notes/rl-demo-data-20261024.md/.json`。这是链路/数据QA，不是专家示范，不启动训练。

当前最终私有产物：

- 录制：`work/rl-demo/data-ready/native-survey-full-r1/r2/r3/`。
- BC schema v2：`work/rl-demo/data-ready/bc-native-sync-final-r1/r2/r3/`（5397/5399/5398样本）。
- QA图：`work/rl-demo/data-ready/qa-native-sync-final-r1/r2/r3/`。
- 原录像自由漂移：`work/rl-demo/data-ready/dynamics-original-r11-final/`。

按顺序补采/转换的命令示例（每次用新的输出目录）：

```sh
# 独立诊断构建：不覆盖run67的render-host-r2，也不激活为人玩默认。
.venv/bin/python -m rl.demo.build_capture --out work/rl-demo/data-host-new

# 使用本机已有data-host-r3演示；两次GPU墨图读回会有停顿，不作FPS测量。
.venv/bin/python -m rl.demo.capture --fixture --source script \
  --script-pattern calibration --opponent 52 --native-survey \
  --host work/rl-demo/data-host-r3/dmhost-demo \
  --modules work/rl-demo/data-host-r3/modules \
  --render-predicate async --present-link 0 --max-catchup-frames 1 \
  --warm-from work/rl-demo/data-ready/native-survey-full-r3 \
  --out work/rl-demo/my-native-survey
.venv/bin/python -m rl.demo.native_survey work/rl-demo/my-native-survey
.venv/bin/python -m rl.demo.convert --recording work/rl-demo/my-native-survey \
  --out work/rl-demo/my-bc-sync --observation-mode sync --allow-approximate \
  --camera work/rl-demo/data-ready/bc-native-sync-final-r2/camera-response.json
.venv/bin/python -m rl.demo.visualize_bc --recording work/rl-demo/my-native-survey \
  --bc work/rl-demo/my-bc-sync --out work/rl-demo/my-bc-qa
```

`calibration`脚本在出生后分别激励右摇杆两轴/陀螺仪三轴，再进入既有脚本动作；不能冒称人的示范。省略`--camera`会拟合本局稳态矩阵，rank只说明输入激励，不证明任意幅度/动态响应。r3使用固定r2矩阵的独立窗口误差在报告中，不在r3重拟合。

`native_survey`把只读候选与未知语义留在旁车，原始日志保持不动；不能因地址可读就设qualified。两次1600²读回及256² R通道采样是原生UV数据，尚不具有世界格/队伍/多层映射，未写入BC墨图。全部留私有目录。

BC新增`hud_valid`、`screen_channel_valid`、`minimap_valid`、`native_camera_valid`、`weapon_native_valid`、`projectiles_native_valid`、`entities_complete`及`entity_velocity_native_valid`。**state_valid不代表整个观测有效**，缺测占位不能解释为中立/空/idle。源位置每4帧更新，年龄保留；旁车严格只取当前ACK之前，计时零之后不导出操作标签。完整训练仍需闭合原生世界墨图/武器/弹体，并有非空原生实体/交火对照；消费者还需遵守mask和ready标记。

自由积分仅作sim-to-real指标：

```sh
.venv/bin/python -m rl.demo.dynamics_audit \
  --recording work/rl-demo/smoke-final-r11 \
  --camera work/rl-demo/bc-final-r11/camera-response.json \
  --out work/rl-demo/my-dynamics-audit
```

该诊断一次初始化后不纠正位置/HP；原生镜头和连续摇杆是明确的归因条件，不能当自主RL结果。原20–24u已复现；默认同步位置残差0只证明不再积分，绝不等于动力学修好。脚本无优化器、无训练副作用。

## run69：受控交火真值（开发测量，不是人玩录制入口）

报告：`notes/rl-demo-truth-20261024.md/.json`。原生中路轻挥35、满蓄70、.52两发倒下/潜墨正例已录到。水刀主武器阶段和本组8000/50的observer0弹体可因果导入；墨图用原生ColPaint片区变换和V翻转，**只解除实测片区133/147内唯一向上地面、精确读回帧、无歧义R/G值的mask**。墙/其他片区/缺帧/混合权重保持未知。

仍不训练：直接瞄准片段不是人的动作标签，`action_labels_trainable=false`；完整连续墨图、通用实体/双角色完整武器和倒下镜头门未签收。新旁车是观测真值来源，不能用GPU自由积分补缺测。BC候选仍要求`--allow-approximate`。

专用宿主 `work/rl-demo/truth-host-r2c/dmhost-truth`、`truth-host-panels-r2`、`truth-host-panel-uv-r1` 均保留独立manifest。构建器分步保留失败版本及已冻结父输入；不覆盖run67人玩/arena默认宿主。实验必须同时开启私有DEMO/TRUTH/AIM夹具标志，正常`rl.demo.capture`继续禁止直接瞄准，正式选择器拒绝test_only宿主。

```sh
# 一房，普通导航/回血，只有瞄准写入。自动记原生记录；不需要手柄。
.venv/bin/python -m rl.demo.truth_capture \
  --host work/rl-demo/truth-host-r2c/dmhost-truth --name my-controlled-truth

# <recording> 用上条输出的 work/a6/ 时间戳目录；下列只读原始日志，生成旁车。
.venv/bin/python -m rl.demo.truth_reduce <recording>
.venv/bin/python -m rl.demo.projectile_truth <recording>

# 地面/出生高台涂地专测；可用 --setup-only 单独采集原生片区表。
.venv/bin/python -m rl.demo.truth_capture \
  --host work/rl-demo/truth-host-r2c/dmhost-truth \
  --name my-ink-controls --extended-ink --ink-only
```

UV表恢复/资格验证：

```sh
.venv/bin/python -m rl.demo.native_ink extract <panel-uv-recording> \
  --out work/rl-demo/my-native-ink-map
.venv/bin/python -m rl.demo.ink_mapping_audit <downward-ink-recording>
.venv/bin/python -m rl.demo.native_ink validate <downward-ink-recording> \
  --mapping work/rl-demo/my-native-ink-map
.venv/bin/python -m rl.demo.native_ink attach <recording> \
  --mapping work/rl-demo/my-native-ink-map
```

只有原生控制点验证通过的片区才会进入`qualified_panels`；不能把原生包围盒当完整三角形归属。当前仅同构建固定温泉峡谷夹具验证，不自动对未来人玩录像套用另一局的UV表。1600²图像/映射NPZ/网格/BC全部私有，不能提交。

最终观测候选：`work/rl-demo/truth-bc-combat-qualified/` 与 `truth-bc-ink-qualified/`；QA在`work/rl-demo/truth-qa-qualified/`。`weapon_stage_id`和`weapon_animation_remaining_frames`是独立元数据，后者不等于输入锁；原生弹体位置为calc前相位、速度是因果位置差分，通用速度/实体完整门仍保留。`minimap_valid`和射线墨色通道现在可以部分为true，但`dense_paint_native_valid`仍false，**不能把一次稀疏读回的有效格延续到下一帧**。

## run70：周期墨图与版本化转换

[中文开录清单](开录清单.md)列出新宿主的完整人玩/预热命令。两个独立构建入口（依赖固定的私有父路径），均用从未存在的输出目录：

```sh
# 历史父产物名固定；本机验收构建已在 work/rl-demo/。
.venv/bin/python -m rl.demo.build_periodic --out work/rl-demo/periodic-new
.venv/bin/python -m rl.demo.build_ink_recording --out work/rl-demo/ink-recording-new
```

构建器依赖本机保留的私有父构建，不下载游戏或覆盖已有二进制；正式arena/T1仍拒绝。`--ink-every 30`只在新异步宿主生效；0关闭。读回在下一帧首个GPU指令之前、同一Metal4队列有序复制上一帧原始RG8目标到共享缓冲，GPU完成后串行后台写PNG。最多两张在途，繁忙则丢并记录，绝不阻塞输入来追读回。所有图片带实际来源帧，未读回帧不延续有效mask。

每局通过只读门重读164片区表；与run69控制点校准的所有数值严格相等才沿用133/147资格。`periodic-ink.json`报告实际间隔和范围，`native-ink.json`为精确帧索引。没有将墙、未测片区或混色推成真值。GPU错误/失败录像拒绝资格；PNG/映射/BC继续私有。

`--warm-from`现在沿已有录制祖先合并“继承清单＋新建PSO”，避免下一轮预热丢掉上一轮已加载的管线。原文件不改，循环/过长链拒绝。新性能表同时保留冷构建长帧，未用删长帧或强制display来冒充60。

转换示例（只计算，不训练）：

```sh
.venv/bin/python -m rl.demo.telemetry work/rl-demo/my-demo-001
.venv/bin/python -m rl.demo.convert --recording work/rl-demo/my-demo-001 \
  --out work/rl-demo/my-bc-001 --observation-mode sync --allow-approximate \
  --camera work/rl-demo/run70/camera-nonlinear-r1.json
```

新版镜头模型会显式选择`native_plus5`动作档，报告保存档名/数值。没有该标记的旧矩阵仍用legacy；物理轴向/动态镜头响应资格不因换了曲线而升级。周期图像f对应动作前观测f+1，转换自动选一个固定采样相位，避免stride2与30帧读回恰好永远错开；`--sample-offset`可显式指定。没有持有过去墨图，也没有用未来图像。训练就绪仍由各通道mask及完整性门共同决定。
