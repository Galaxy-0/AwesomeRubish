# 第二关启动：BC2无反馈单步 → PPO（run81，后台进行中）

2026-10-25用户明确批准跳过补录及BC联合门槛，以BC第二轮主候选直接warm start。
**b736240的BC仍是0伤害、未通过；本报告是新PPO的启动健康检查，不是第二关签收。**
正常出生基线虽对不涂地的固定脚本100%涂地胜，但0武器KO，不能当作对枪通过。

## 身份、隔离与运行

- BC固定为run80 `fit-nofeedback1-80/best.pt`，SHA
  `e4bef923d42b3ab6a51fc1a715ba1b1937d1da0ed14595481f4c896ef25cb99e`。
- WarmActor加载全部BC2 actor/CNN/实体/HUD/GRU权重，horizon1、无上一动作反馈，原physical level语义。
  未偷偷换toggle头，也没有自动蓄满/释放宏；R/RS仍只有0。
- 只在asuka0的`~/splatoon3-native-rl-stage0/bcppo81-r3/`，沿用项目私有`.venv`，未安装依赖或访问VPT。
  私有`data`/`bc.pt`链接上一轮已留存数据和固定BC，源码隔离在`src/gpu`。
- tmux会话 **`bcppo81-main`**；启动2026-10-25 **23:27:23 UTC+8**，配置128局GPU并行、每2f决策。
  24h累计预算，外层25h只针对本任务的超时保护；SSH只短轮询，抖动不计学习卡点。
- 不启动原生/不接手柄/不录新人类局，T1和原S1暂停。GPU阶段通过后才做本机单房medium/hard共2–4局预检。

正式启动前8局pilot完成冻结BC预热、4组32局评估和一次PPO更新，随后因日志系数`bc_kl`
与测量`bc_kl`重名退出；已分成`bc_kl_coef`/`bc_kl`，原件保留且不混入正式学习帧。
`bcppo81-r2`只有上传包，没有训练；正式R3没有覆盖或删除R1原件。

## 价值预热与PPO

critic先置零，仅拟合value线性头。冻结BC采集两批完整180秒、128局/批，
50%随机分配近距开局，记录1,382,400个决策状态（2,764,800环境帧，不计正式PPO帧）。
Monte Carlo目标gamma .9995，6轮value-head拟合：

|项|数值|
|---|---:|
|预热耗时|50.63秒|
|MSE拟合前|0.058758|
|MSE拟合后|0.014057|
|非value的state_dict逐值不变|true|

PPO：AdamW1e-4，rollout128、BPTT32、minibatch16序列、3epoch、clip .2、
gamma .9995、lambda .95、梯度范数.5、优势std分母下限.05。
每minibatch检查joint KL，>.025停止当前更新；逐动作头熵/KL、非零奖励率、ZR比例与最长按住、
出刀/满蓄、pitch触限、可见率及显存写CSV。冻结BC teacher按自己GRU历史推断当前rollout观测，
用KL(BC||PPO)六个有效头均值，不把teacher值或裁判信息放进actor。

## 奖励、退火和课程

击杀±1、局末涂地胜负±.5不退火。伤害每条命封顶100，辅助由.5提高至.75/100（新增.25）；
涂地每1% .02。新增引导：接近×.003/u、正向角误差减少×.03/rad、
当前可见且≤22u/误差<.12rad时实际出墨刃+.01。
接近/角差/对准出刀三项分别封顶每命.30/.10/.10、每局.80/.30/.30；
失去或重新看见不重置预算，死亡不重置局预算。最近目击点仅可见时更新，90f后失效。
符号按[+r,−r]保持零和；“准星”用GPU主武器弹道yaw/pitch方向，未直接改瞄准或命中。

所有伤害/涂地/新增引导辅助与BC KL系数同乘`f=max(0,1-elapsed/6h)`：

|累计墙钟|0h|1.5h|3h|4.5h|6h及以后|
|---|---:|---:|---:|---:|---:|
|辅助/BC KL系数|1|.75|.5|.25|0|
|训练近距开局比例|50%|37.5%|25%|12.5%|0|

基础熵系数按24h .010→.005，ZR另加.005；探索熵不计环境奖励。
连续10个rollout ZR>98%且熵<.05写collapse-warning，不以强制松开掩盖塌缩。

选更稳的**先固定.52，只更新水刀**，避免共享网络的未训练.52角色或双边漂移干扰归因。
课程：easy（公共可见性、400ms反应、有限镜头）→原D4固定脚本→75%D4+25%冻结历史池。
对easy正常出生平均KO≥.5且伤害≥50才进D4，D4平均KO≥1才进历史池；
历史u000100/u000245是已知较弱的旧Stage1，旧camera档近似重映射，不能冒称强自博弈或完全等价。
近距开局用于探索，绝不并入正式门槛统计。

## 观测/物理边界

沿用BC2同一camera codebook、墨图过去快照和缺测mask，不重新放开原生未知通道。
actor只有screen/entities/hud/minimap、质量mask和GRU；不输入真实敌位、奖励的最近目击记忆、手工危险图。
原生连续墨图和完整弹体/阶段缺口、相机/地形/攀墙/重生近似仍在，未据整局曲线调物理。
伤害辅助系数提高只影响奖励，不改HP伤害、碰撞、弹速、射程、潜墨回复或出刀时序。

## 自动评估、保存与停止

启动基线、30min健康评估，随后每1h：easy和原D4脚本各sampled/greedy各32局，
完整180秒、正常出生、无引导奖励；报告胜率CI、武器KO/伤害/涂地及出刀/满蓄/可见性。
baseline D4 sampled：32/32涂地胜、0KO/0伤害、涂地2.350%、43.156刀/min、满蓄.792/min；
greedy：32/32涂地胜、0KO/0伤害、涂地.642%、8.302刀/min、满蓄5.208/min。
对手没涂地且没相遇，所以100%胜率不算门槛通过。

第二关必须同时：**D4脚本胜率≥70%且每局平均武器KO≥2**。保存passed并停GPU，标原生预检待办，
再在本机单房对medium/hard做2–4局，GPU结果不能替代迁移验证。
best按KO→伤害→胜率排序，每15min另存checkpoint；初始best可以是未学习的BC，不能凭文件存在宣称改善。

若6h正式正常出生评估仍未出现伤害，6h点强制补评估，保存last并停止；
`diagnosis.json`/数值控制日志含可见性与裁判LOS、距离、pitch触限、地面/发射/HP状态，
及独立合成平地.52两发/70+35/回血/槽量/伤害归因等控制。单个末态不冒充因果证明。
约2026-10-26 **05:27 UTC+8**到6h点（补评估略晚）；24h截止约当日23:27。

## 当前健康快照

最终启动快照于2026-10-26约00:00 UTC+8取得：**运行32.70min，1658次更新、54,329,344 PPO环境帧**；
从首个PPO更新到末次的跨度29.50min（包含期间评估，不是纯优化器计时）。全部曲线统计有限，
68份启动时源码SHA与本地相同，无collapse-warning。后台任务继续，不等待24小时完成。

最近20次更新：出刀49.49/min、满蓄.685/min、ZR比例.411、ZR熵.537、joint KL .00342、
BC KL .00254、value loss .000623、最长ZR52f，峰allocated4244.73MiB（4.15GiB）。
可见率1.55%、pitch触限6.02%；仍有显著感知/路线问题，不从有限loss推断能力通过。
独立资源轮询：GPU75%、1437MiB、58°C；同项目venv确认PyTorch2.12.1+cu126/CUDA/4070Ti。

混合近距训练39批×128=4992局，累计471武器KO/62435伤害，平均**.094 KO/局、12.51伤害/局**。
这些数值只作非零学习信号，不能并入正常出生验收，且不能仅据不同摆位种子的逐批上升证明因果收益。

30min定时评估已完整结束，下面每格都是32局完整180秒，D4与easy结果相同：

|D4正常出生|BC基线|30min PPO|结论|
|---|---:|---:|---|
|sampled 涂地胜率|100%|100%|对手0涂地，不能当对枪通过|
|sampled 平均武器KO / 伤害|0 / 0|0 / 0|未过|
|sampled 涂地%|2.350|2.694|小幅增加，非击杀证据|
|sampled 刀/min|43.156|43.938|总出刀未塌缩|
|sampled 满蓄/min|.792|.385|仍低且下降，须持续监控|
|greedy 平均武器KO / 伤害|0 / 0|0 / 0|未过|
|greedy 涂地%|.642|.763|未证明接敌|
|greedy 刀 / 满蓄每分钟|8.302 / 5.208|5.719 / 2.917|尚无能力改善证据|
|sampled / greedy 敌人可见率|0 / 0|0 / 0|正常出生接敌仍是瓶颈|

第二关未通过，没有原生预检。**运行健康不等于策略有效，满蓄低频也没有被“总出刀保持”掩盖。**
按用户预算继续至后续小时评估/6h零正式伤害诊断点。评估seed固定作开发比较与checkpoint选择，
不是独立最终留出集。没有因近距训练已命中而取消正常出生的6h保护。

[完整聚合数字与启动源码SHA](rl-bcppo-start-20261025.json)；
数值曲线私有`work/rl-bcppo/run81/curves-final.png`（已自查），CSV/JSON快照`work/rl-bcppo/run81/snapshot-final/`。
65项组件/环境/适配器测试执行通过，远端启动前16项Warm/复用BC测试通过，Ruff/compileall/shell语法/diff通过。
9个保护宿主SHA未变，无本机游戏进程；不提交数值曲线图、原生数据/模型/PT，代码和数值报告提交推送。

## 监控命令与原件

```sh
ssh asuka0 'cd ~/splatoon3-native-rl-stage0/bcppo81-r3 && PYTHONPATH="$PWD/src" ../.venv/bin/python -m gpu.bcppo.monitor --root train-r1'
ssh asuka0 'tail -n 1 ~/splatoon3-native-rl-stage0/bcppo81-r3/train-r1/evaluations.jsonl'
ssh asuka0 'tail -n 4 ~/splatoon3-native-rl-stage0/bcppo81-r3/train-r1/metrics.csv'
```

优雅停止只需创建本任务STOP文件，不要杀任何未知进程：

```sh
ssh asuka0 'touch ~/splatoon3-native-rl-stage0/bcppo81-r3/train-r1/STOP'
```

源码与完整系数/恢复说明：[bcppo README](../rl/gpu/bcppo/README.md)。
本机原件`work/rl-bcppo/run81/`；远端正式目录`bcppo81-r3/train-r1/`。
代码/notes只提交数值证据，不提交地图/录像/trace/生成页/PT。原件保留，未动原存档/policies/正式宿主/VPT，T1/S1仍暂停。
