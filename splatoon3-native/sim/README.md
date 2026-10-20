# S1 offline 1v1 simulator

Python + NumPy，只做工作刮水刀、占地、Yunohana / District00 / Yagara。
已加入历史辨识、短时域评估、预扣/退款、批量运动、A6高级机制与历史策略排名检验；原生一致性仍未签收。
默认入口完全离线，不构建宿主、不启动游戏、不修改原生擂台或策略。
`sim/calibration`另含显式开关门控的未来原生收集分支，本阶段没有执行。
从项目目录用 `.venv/bin/python -m sim.parameters` 开始。

参数从本机 `work/data/v720896/RomFS` 只读提取；碰撞/导航复用
`work/arena/maps`。提取结果默认写 `work/sim/parameters.json`，包括来源和
条目 SHA256，禁止写到 work 之外。不随源码分发游戏表、地图或原生记录。
需要本机已安装的 NumPy 和 zstd，以及项目现有 BYML/SARC 只读解析器。

注意：参数表是稀疏覆写，不含全部 C++ 默认值。缺失的移速/重力/回血回墨/
重生/配装曲线必须标记为近似或待校准，不能当作已提取值；目录 Range
也不能当成世界坐标射程。A6 实测边界与参数计数分开使用。

推进顺序：参数 → 核心移动/粗涂地/墨刃/HP/重生/墨量 → 历史同输入对照。
第三阶段以显式可选AdvancedModel补入乌贼滑、墙蓄跳、冲刺斩、快速炸弹；触手喷射仅简化启动/消耗/回归。

## 核心接口

```python
from sim.engine import Simulator, neutral

env = Simulator(stage_id=1, duration_frames=10800)
obs, info = env.reset(seed=0)
obs, info = env.step({'player_0': neutral(), 'player_1': neutral()}, frames=12)
# obs: 两份 arena.policy.v1 字典（含 A6 自身 special 扩展）。
# info: 模拟器裁判统计，不能传给策略。
```

`frames` 是 fixed60 游戏帧数；同时提交两端输入，先移动/发射，再统一结算伤害，
允许互杀。轻挥/满蓄采用 RomFS 球列、速度和存活时间；接触斩采用参数盒体与
胶囊近似。伤害/HP/墨量均归一化到 0..1。下潜取消蓄力；满蓄使用20内部计数
加首帧边界，站立21/出墨26是 A6 实测锚点。未传 `WeaponModel` 时保留第一阶段
释放扣款基线；传入第二阶段模型会执行预扣/退款与经原生采样区间拟合的HP生效延迟。

`Assumptions` 集中所有未提取默认值；A2 的 AP19 游速与 AP38 主墨效只是两个
经验锚点，其间线性插值不代表原生技能曲线。其他配装效果在 `unsupported`
中列出。未传AdvancedModel时仍保留旧核心：R/RS只记录未实现、乌贼+B为普通跳、前推满蓄为普通蓄斩。
传入后启用A6有效模型；触发门槛、局部墙墨和炸弹抛物线仍有未辨识项，见COMPARISON。

地形来自已提取的 `human.npz`，视线来自 `sight.npz`；多射线扫掠加端点球体距离
近似碰撞。涂地以导航节点为带高度层的粗格，墙阻断传播、同队重复涂色不再次
充能；计分分母含未涂格。节点可潜游性不等于原生可计分地面，原生纹理/涂点
映射仍未知。特殊量有近似面积充能，触手喷射钩索位移仍unsupported。出生从导航落地点开始，
重生直接回落地点，不模拟发射台飞行。移动/跳跃已有离线辨识，回血回墨和重生等仍待实机校准。

观测复用 `PolicyProjector`、`GeometricVision` 和 typed own-special encoder，
保持 FOV/墙遮挡/静止潜墨隐藏/溅墨例外及最后目击记忆；敌方 HP/墨量与裁判
墨图不会进入策略。`sim.run` 复用真实擂台的 macOS `ControlProcess` 沙箱及
策略 cadence/超时，不启动任何游戏进程：

```sh
.venv/bin/python -m unittest sim.test_core -v
.venv/bin/python -m sim.run arena/policies/rush arena/policies/high-ground --stage 1 --frames 600
# alpha/bravo 无需改代码；只在沙箱黑盒调用。
.venv/bin/python -m sim.run arena/policies/alpha arena/policies/bravo --frames 60 --out work/sim/compat-t1
```

`sim.interfaces.ParallelEnv` 提供字典式 reset/step 与双端 reward/termination；
`BatchSimulator` 提供批量输入形状，复用只读地图/参数，每个环境有独立墨图。
`BatchSimulator` 保留串行兼容接口；`sim.batch.VectorBatchSimulator` 向量化同图多局
的运动/分桶地面查询，近墙回退同一标量判定。武器/涂地仍逐局处理，完整核心均执行。
未通过官方 Gym/PettingZoo API 验证，尚未提供 spaces/注册适配器。无渲染、无需游戏引擎。

## 历史同输入对照

```sh
.venv/bin/python -m unittest sim.test_core sim.test_replay -v
.venv/bin/python -m sim.replay work/a6/combat-20261019-131326-782403 --a6-prefix minimum-full-damage --out work/sim/a6-full.json
.venv/bin/python -m sim.replay work/arena/t1/round-001/game-0-attempt-000 --frames 600
# --frames 0：从双方首次共同落地到原生计时归零，不运行结算阶段。
.venv/bin/python -m sim.report
```

报告与逐采样曲线默认在 `work/sim/comparison/`，来源/地图/源码均带 SHA256。
回放从窗口首个原生样本一次初始化，逐帧送回记录输入；后续原生位置/HP/墨量
只用于比较，不纠正模拟状态。按每个宿主的独立帧原点对齐样本，重复包去重。
输入缺口报错，不偷偷填中立。A1/A2较早的原件没有完整动作，报告明确单列为
按已签收夹具脚本重建；A2调参锚点不作为独立验证。

当前结果见 [COMPARISON.md](COMPARISON.md)。第三阶段以闭环策略排名为关键有效性检验，
短时域用于定位机制误差，整局开环为次要诊断；**未通过原生一致性验收**。
实机校准及后续操作清单在 `notes/PROGRESS.md`。

## 第二阶段保真度

`.venv/bin/python -m sim.corpus` 将本机历史输入与原生状态归一化并按完整会话划分
训练/验证/测试；T1作为整个测试家族，不拆时间片进入训练。
`.venv/bin/python -m sim.horizon` 每隔30/60/120/300帧因果重置，报告位置、朝向、
墨量、HP、形态的采样/窗口/末端误差分布。缓存与原始曲线仍只在work/。
包龄、未知速度/武器中间态/墨图和排除的锚点均有明确口径；短时域为主，整局开环为辅。

`.venv/bin/python -m sim.identify` 从训练会话拟合六种形态/武器阶段的杆量响应、
速度上包络、加速/制动、相机转向及跳跃，验证集按模式决定是否采纳；稀疏速度激励
保留独立先验，不能把堵墙后的慢速分位数当作自由最大速度。模型只写
`work/sim/fidelity/motion.json`。使用 `Simulator(motion_model=MotionModel.load(path))`
或 `.venv/bin/python -m sim.horizon --model work/sim/fidelity/motion.json --out work/sim/fidelity/horizon-fitted.json`。
未传模型时保留第一阶段方程用于可复现基线。支持面与墙体分别处理，坡道不因脚部
判定球碰到其支撑面而被误判成墙。人形所在墨色、完整AP曲线和台阶材质上限仍不可辨识。

```sh
.venv/bin/python -m sim.calibrate_weapon
.venv/bin/python -m sim.horizon --model work/sim/fidelity/motion.json --weapon-model work/sim/fidelity/weapon.json --vector-batch 16 --out work/sim/fidelity/horizon-final.json
.venv/bin/python -m sim.speed --games 16 --frames 600 --out work/sim/fidelity/speed-final.json
.venv/bin/python -m sim.fidelity_report
.venv/bin/python -m sim.run arena/policies/rush arena/policies/high-ground --frames 60 --motion-model work/sim/fidelity/motion.json --weapon-model work/sim/fidelity/weapon.json
```

预扣曲线66点属于校准重算，独立combat房另报验证。5帧HP延迟是对端包反馈的有效模型，
不是已分解的物理命中时间；接触斩关节起点仍是A1校准候选。原始模型JSON、历史曲线与
证据哈希只在work/。单/双CPU吞吐分别报计算和进程启动成本，最多两个worker，BLAS线程1。

## 第三阶段：高级机制与排名

```sh
.venv/bin/python -m sim.ranking_sources
.venv/bin/python -m sim.advanced
.venv/bin/python -m sim.advanced_report
.venv/bin/python -m sim.ranking
.venv/bin/python -m sim.ranking_input_audit
.venv/bin/python -m sim.ranking_report
.venv/bin/python -m unittest sim.test_advanced sim.test_ranking sim.test_calibration -v
```

排名用git show提取到work/的历史版本，不读取当前策略作为替代。R0用精确v0，
R1–R4运行文件与原生冻结策略核对；A5采用接受70局检查点。当前公开atlas/skills与
A5/R0历史实现无修改，后来新增stamper文件不被它们导入。
每对阵36个完整180秒模拟：三图、交换侧、固定起点及五组预登记起点敏感性。
保持原沙箱、原配装/频率/超时；六局批量，BLAS单线程。最多两个模拟worker，
分别指定互斥`--pairs A5 R0 R1`与`--pairs R2 R3 R4`，同组禁止并发写。
也可用`.venv/bin/python -m sim.ranking_schedule --workers 2`按同一计划动态调度，
耗时长的组优先，空闲worker接下一组；它复用同一个`ranking.group`，不改变模型/输入/样本。
该入口有独占调度锁，**不要与sim.ranking同时运行**；已有完整组先核对SHA与情景后跳过。
每组绑定核心、模型、策略SHA；恢复时校验原计划，最终报告拒绝缺局/重复局/混模型。
原生不是完整全互打，故报告六条实测边方向、逐图差异及固定bravo-v1对手下alpha三版的tau-b，
不编造跨A5/R0/T1的统一全局排名。敏感性场次不当原生独立随机样本。
原生输入审计按真实逐present输入计R/RS、ZL+B边沿及前推满蓄松刀候选，
不能把按键计数当高级动作的原生启动证明。最终报告同时列模拟高级触发频数。

单局可用`sim.run ... --advanced-model work/sim/advanced/model.json --swap`启用高级模型与换侧。
详见[COMPARISON.md](COMPARISON.md)。待实机项目已编入[校准清单与脚本](calibration/README.md)，
默认`python -m sim.calibration --write-plan`只生成清单，不执行游戏。

## 离线反例诊断：A5 Yagara、R1/R2

```sh
.venv/bin/python -m sim.diagnosis --inventory
.venv/bin/python -m sim.diagnosis --run --seeds 1 --out work/sim/diagnosis/ground-new
.venv/bin/python -m sim.diagnosis --run --mode prefix --seeds 1 --out work/sim/diagnosis/prefix-new
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m sim.diagnosis --run --mode prefix-clock --seeds 6 --workers 2 --out work/sim/diagnosis/clock-new
.venv/bin/python -m sim.diagnosis_horizon
.venv/bin/python -m sim.diagnosis_report --baseline work/sim/diagnosis/ground-new --prefix work/sim/diagnosis/prefix-new --clock work/sim/diagnosis/clock-new
.venv/bin/python -m unittest sim.test_diagnosis sim.test_horizon -v
```

所有命令都只运行 Python 模拟/策略沙箱，不导入原生对战执行器。`inventory`审核原生28局
（A5 Yagara22局、R1/R2各三局）；模拟NPZ逐帧留位置/朝向/相机/墨量/HP/形态、输入、
可见性和网格占地；JSON另含伤害/击倒事件。原生重复包按自己的采样帧去重，不能声称
每present都有新位置。高台用公共central_high的XZ半径2、层差.3；同时统计Skills的.7/.3到达条件。
停留以短采样间隔左保持估计，ZR时长/松开只代表涂地机会，真实涂地时长/面积仍unknown。

`ground`复现原排名基线；`prefix`在前120帧用历史**白名单观测**恢复同一策略的内部记忆，
逐次核对输出与历史动作，然后只在第120帧重置一次可观测模拟状态。此后没有原生状态纠正。
`prefix-clock`再使用历史**时间戳**，只从模拟器过去的快照生成延迟观测，不从原生复制后续位置/HP。
这些是条件诊断干预，**不等于实现了发射、重生或网络生成模型**。初始世界墨图/投射物/真实速度
仍未知；过去速度、武器阶段和潜墨脚下小墨块是显式估计。六个seed在第120帧施加原预登记扰动，
不能与原地面seed逐个当作同一随机事件，也不能充当原生独立胜率试验。

A5按每侧首局重建、另外原生局用于审计；T1只重建实测出生侧，未把另一侧镜像成新原生证据。
报告保留原216局排名结果并另列条件对照，拒绝缺局/混时域/改动原件的报告。
模拟地面模式默认同时交换出生侧，重建模式只用已有原生侧。每个输出目录登记代码、模型、
冻结策略和原件绑定；重复运行先校验计划，源码变化应选择新目录。失败留下failure.json，
不会推断一场胜负。原实验原件与新输出都只在ignored work/，不提交游戏数据。

短时域状态外推现在遵守已知地面支撑，避免把“已落地”的最新包按上一段下落平均速度推进
地板下；空中预测跨过静态支撑时也会落地。修复和剩余残差见[COMPARISON.md](COMPARISON.md)。
`diagnosis_horizon`会更新早期窗口结果；本轮修复前副本另存early-horizon-before.json，需保留以复核前后表。
