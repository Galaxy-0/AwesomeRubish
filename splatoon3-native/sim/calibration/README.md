# 原生校准清单与 P0 窗口

2026-10-21 S1 已进入用户批准的原生窗口。P0 专用入口是 `python -m sim.calibration.p0`，使用 A8 已签收的默认 v4 相机宿主、geometry 模式、每案例新进程，最多三房。默认 `python -m sim.calibration` 仍只读显示146项通用清单；通用全扫描没有运行，不把 P0 收集状态冒充全套通过。

本轮原件、纹理、失败/取消记录、冻结采集源码及派生模型只在 `work/sim/window-20261021/`。`opening` 跳过450帧 warmup，采三图双侧中立/前推；`paint-retry` 采 Yagara 单轻挥、单蓄力与八轻挥到双方 Winners；`probes*` 采 AP0/19/57、局部脚下接触涂地扫描、伤害/重生。完整结果和剩余义务见 [COMPARISON](../COMPARISON.md)。

```sh
# 必须在用户另行批准的空档内给出绝对截止时间；不要照抄旧时间开启新窗口。
.venv/bin/python -m sim.calibration.p0 --execute-native --window A7_A8_IDLE --phase opening --parallel 3 --deadline <epoch-seconds> --out work/sim/<new-window>/opening
# 只取消本批：在该 --out 下创建 STOP，或对本批 Python 驱动发送 SIGINT。
# 当前案例在有界 STEP 边界关闭自己的房间，排队案例不再入场。
```

`p0 --phase generic --plan <json>` 接受专用 `p0_paint/p0_motion/p0_scan/p0_combat/p0_bends` 案例。每份 case 显式包含地图、loadout、frame_budget、settings；loadout 原生逐槽读回。settings 可指定 warmup_frames、shared_load_slots、既有单帧 texture_frame 诊断；不改宿主和公共测试文件。resource Monitor 的压力、增量swapout、停帧与 Session 超时保护均保留。纹理是 UV 空间证据，尚未映射世界/计分面积；geometry 的无像素截图记 unavailable，不写黑图假冒画面。

拟合与离线复验：

```sh
.venv/bin/python -m sim.calibration.fit --directory work/sim/window-20261021
.venv/bin/python -m sim.calibration.fit --directory work/sim/window-20261021 --transitions
.venv/bin/python -m sim.calibration.fit --directory work/sim/window-20261021 --gear
.venv/bin/python -m sim.calibration.fit --directory work/sim/window-20261021 --paint --core-field
.venv/bin/python -m sim.calibration.fit --directory work/sim/window-20261021 --full-paint --core-field
.venv/bin/python -m sim.calibration.fit --directory work/sim/window-20261021 --air
.venv/bin/python -m sim.calibration.analyze --directory work/sim/window-20261021
```

`--air` 把空中候选连同其它模型复制到 `models-v2/`，不会覆盖首轮模型；地图1/2角色0自由空中段拟合，地图3/另一角色留出。脚下墨半径是当前粗网格的有效半径，不等于原生精确笔刷；`--core-field` 为经扫描对照的 CoreIndex 整条墨刃终止候选，非核心球的场景碰撞仍各自永久遮断，不能复活穿墙。

这些命令只读已有记录并写 ignored work/，不启动游戏。模型需显式传给模拟器，旧模型/历史结果不会被覆盖。原生 collected 仅表示收集结束；拟合、独立验证与验收分开报告。

下文保留窗口前的通用清单与证据要求；其中 pending 描述以本轮对照报告的逐项状态为准。

## 反例诊断后的最高优先级（先于下面146项通用扫描）

这些义务已经列入 `plan.json.priority_followups`，当前均为 pending，**不计入已可执行案例或已覆盖机制**。

1. **P0 开局、重生与采样协议**：三图双侧，从首个受控帧起采 STEP1，比较中立/移动/开火输入；记录发射锁定、落地、首次重生、own 包和 HUD 的采样/交付时钟。A5 Yagara 的 high-ground 在飞行第36帧已经用完重规划次数，不能从地面起跑来验证这22局。R1/R2 own 包延迟1–5帧。现有 `Lab.start` 有450帧 warmup，**不能采这个项目**；空档执行前必须新增绕过 warmup 的专用 opening collector，并独立验证发射/重生模型。历史前缀重建只用于离线诊断。
2. **P0 出生侧与高处涂地/计分域**：Yagara 原生实际落点两侧，先固定位置轻挥12/36，再转向扫射；再测 central_high 和 District00 坡道/侧线。逐次记录墨量、得分增量、局部画面及世界墨图/UV 映射，拆分脚下墨、沿途墨刃、碰撞喷溅和不计分区域。现有脚本无原生墨图传感，最终比分不足以识别这些项，须额外读回或审核标注。
3. **P0 早期拐点、攻击后移动与回墨**：重点复测 Yunohana `(x±20,y7.5..10.5,z±70)`、District00 `(x±1或±6,y9..13,z±70)`、Yagara `(x±2,y10.5..14.5,z±64)` 与 `(±1,7.5,±52)`；AP0 对照历史 R1/R2 的精确冻结配装，短段原输入加中立/跳跃对照。同步检查地面支撑/小道具、身体朝向与相机、脚下墨色和潜墨恢复，不能把早于交战的路线漂移归因于伤害。通用 terrain 自动选边不等于覆盖这些位置。

以上不是给现有146项收集器追加的虚假通过项。一次空档先完成这些专用采集和传感适配，再统一跑通用扫描；当前只生成清单，不运行实机。

```sh
.venv/bin/python -m sim.calibration
.venv/bin/python -m sim.calibration --write-plan
```

A7/A8排定空档以后，一条命令按清单串行执行并生成汇总：

```sh
.venv/bin/python -m sim.calibration --execute-native --window A7_A8_IDLE
```

以上最后一条本阶段**没有执行**。入口要求显式原生开关与空档名称，并只读检查
dmhost/test_a5/t1_round/proficiency是否活跃；发现其它房间就拒绝，不发信号、不清理他人进程。
最多一个双人房间；病例间释放自己创建的房间，按案例重建以隔离地图墨色和配装。
复用A6 setup/trace方法，使用自己的当前宿主SHA清单；不调用A6旧T1冻结构造器，
不修改任何测试、对战代码或公共库。未来A7接口若改变仍需适配，本次仅做离线语法/流程检查。

每案例最多9,000受控帧（包括setup），房间正常结束、导航失败、样本过期、配装读回失败
均留档为failed，继续其它案例；不因采样失败推断机制不存在。成功收集标记collected，
不等于通过机制验收。重跑同命令跳过已collected的案例；失败项创建新attempt保留原件。
源码/宿主/地图/清单hash变化时拒绝沿用旧目录；用`--out work/sim/native-calibration-<new>`建新批次。
`--only <完整case-id> ...`可重跑清单子集；完整批次不传该参数。

| 组 | 一次采集的控制变量 | 用来解决什么 | 必须核验的前提 |
| --- | --- | --- | --- |
| motion | 人形/乌贼×己墨/敌墨/无墨；杆量.25/.5/.75/1，启动/停杆/反向/跳落/转向，3次重复 | 脚下墨色速度、加减速、死区、转向与状态过渡 | 平地、无碰撞；己墨可用真实潜墨确认，其余颜色须审核截图或增加原生墨图读回 |
| gear motion | run/swim/resistance AP0/3/10/19/38/57，同上控制 | 解除速度与AP混淆、敌墨抗性与损血 | 原生gear三件逐槽读回；非目标槽为quick_super_jump，测量不触发超级跳 |
| ink | main/sub saver与recovery AP同六档；1/20/21/30蓄力、松开退款、副武器、停墨与人/潜恢复曲线 | AP非线性、预扣/退款、恢复停顿/速率 | 满墨、朝天空；潜恢复必须确认脚下己墨，重复前基线须审核 |
| roll | intensify AP六档；6/12/18/30助跑，45/90/120/180°反向+B，120帧落地 | 速度/转角触发阈值、全程重力/落地、重复衰减候选 | 助跑实际处于己墨；与motion无B反向及普通跳对照；护甲仍需另加同步射击实验 |
| surge | intensify AP六档；B1/20/30/40/44/45/46/60；记录停止攀爬与松B后60帧 | 最短蓄墙跳阈值及AP曲线、余速 | 真实墨墙/爬升证据；形态枚举不能单独证明墙状态 |
| terrain | 三图各一个坡/台阶候选，往返前后图像和逐帧轨迹 | 支撑坡面、台阶门槛、阻挡反例 | atlas边只作几何候选，截图/三角形检查确认坡/阶/道具；不能直接按dy标签拟合 |
| contact | 实测距离1/1.5/1.8/2/2.5/3/5.8/6.2/12/19 | A1接触关节起点、55伤害区间与墨刃/接触分离 | 实际坐标而非请求距离；双端HP采样区间，避免被敌墨持续伤害污染 |
| recovery | 静止受击后240帧双端HP、脚下颜色与动量 | HP恢复停顿/速率，敌墨伤害时序 | 原生射击与表面证据；不能把持续敌墨掉血当恢复速率 |
| dash/bomb | 原A6相同距离，3次；逐present出刀/碰撞/HP/墨量 | dash位移/停止、15/18时序、炸弹25/35分包与有效延迟 | 同输入对照；物理碰撞与PIA/采样延迟仍需独立宿主事件才能彻底分离 |
| zip | 自然涂地积满，RS→R→耗尽回归 | 启动/消耗/回归，钩索位移是否存在 | 禁止DM_TEST_SPECIAL；涂地特殊点换算仍要真实占地/墨图支持 |

所有输入和双端原包写steps.jsonl；测量段STEP1，setup可批量STEP。
按每端自己的`position_sample_frame`去重，保留guest_time、有效位、位置、相机、形态/contact、HP/墨量/特殊。
不要把ACK帧当状态帧，不用未来包初始化，不用拟合速度给墨色打标签。
每案例有前后截图、gear读回、session路径、host/源码/地图hash、案例状态与原因。

尚需人工审核/额外传感的事项必须保持pending：

- 无墨/敌墨的**脚下**颜色、完整原生可涂/占地分母、世界坐标到墨图映射，不能只靠输入推断。
- 同步攻击下roll/surge护甲、重复衰减和特殊护甲；当前脚本只采运动，不宣称已覆盖伤害减免。
- 接触骨骼关节真值、真正物理命中/网络传递/HP编码分离；双端时间区间只能识别有效延迟。
- 多个坡/阶材质与移动平台的泛化。脚本只采三图候选，不覆盖全部动态碰撞。

这些项连同收集失败项进入同一summary审核。数据未确认前不自动写回sim参数，避免一次脚本运行
把未知标签固化成看似精确的模型。运行完成后的拟合/短时域复验与策略排名复验是下一次任务。
