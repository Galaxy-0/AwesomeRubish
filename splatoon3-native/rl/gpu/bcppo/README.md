# 第二关：BC2无反馈单步 → 有界PPO

用户2026-10-25明确授权跳过补录及BC联合门槛，直接做本阶段。
此前BC0伤害/门槛未过的结论不变。本程序只在GPU近似环境训练Stamper，.52冻结；不运行原生宿主。

## 固定身份与启动

- BC：run80 `fit-nofeedback1-80/best.pt`，SHA256
  `e4bef923d42b3ab6a51fc1a715ba1b1937d1da0ed14595481f4c896ef25cb99e`。
- 模型所有actor/encoder/GRU权重逐值载入；保持BC2 physical level头、无上一动作输入、horizon1。
- critic单独置零后，使用冻结BC策略的两批完整180秒rollout做Monte Carlo回报拟合，
  仅改value.weight/bias；其余state_dict逐值断言不变。
- 沿用BC2过去墨图/缺测规则；没有加入敌方隐藏坐标、奖励记忆或裁判信息作为观测。
- 只用项目私有`~/splatoon3-native-rl-stage0/.venv`；不安装依赖、不碰VPT。

源码包解到私有目录`src/gpu/`，`data`只链接上一轮私有数据，`bc.pt`链接固定BC，
在asuka0执行（先确认没有本任务旧训练仍在跑）：

```sh
cd ~/splatoon3-native-rl-stage0/bcppo81-r3
tmux new-session -d -s bcppo81-main \
  'sh launch.sh > train-r1.log 2>&1; echo $? > train-r1.exit'
```

`launch.sh`的配置：128局、每2f决策、128-step rollout、32-step BPTT、16序列minibatch、
3 PPO epochs、AdamW1e-4、gamma .9995、lambda .95、clip .2、梯度范数 .5、
优势std下限 .05、逐minibatch joint KL>.025即停止当前更新。
24h累计墙钟预算（包括起机/预热/评估），外层25h超时保护。
所有长任务tmux，SSH只做短轮询；网络抖动30/60/120s退避，不据此判学习卡点。

## 奖励和衰减（非观测）

令`f=max(0,1-elapsed/(24h×25%))`，即前6小时1→0，之后0。

|项|初始系数/上限|乘f|
|---|---|---|
|武器击杀/被杀|+1 / −1；环境自灭不伪算敌方KO|否|
|局末涂地胜负|+.5 / −.5|否|
|伤害辅助|每条敌命/己命最多100伤害；原.5提高至.75/100，含新增.25|是|
|涂地辅助|每1% +.02；双方净差、零和|是|
|接近已可见/最近目击目标|正向距离减少×.003/u，每决策最多.5u；.30/己命、.80/局|是|
|准星角误差减少|正向角差×.03/rad，每决策最多.2rad；.10/己命、.30/局|是|
|射程内对准并实际出刀|目标当前可见、≤22u、弹道yaw/pitch误差<.12rad，实际发出墨刃+.01；.10/己命、.30/局|是|
|冻结BC正则|KL(BC||PPO)，六个可用动作头均值，系数1.0|是|

“准星误差”按GPU主武器发射方向和目标中心定义，不是直接控制相机或自动瞄准。
奖励最近目击点只有public enemy可见时更新，记忆最长90f；看不见时不追踪真实敌位。
接近/角差正奖励累计扣预算；失去/重获视线不刷新预算，死亡只刷新命预算，不刷新局预算，防往返/自灭刷奖励。
添加项按`[+r,-r]`保持零和；只更新水刀。未更改命中、伤害、移动、回血、出刀物理。

|累计墙钟|0h|1.5h|3h|4.5h|6h及以后|
|---|---:|---:|---:|---:|---:|
|f / BC KL系数|1|.75|.5|.25|0|
|训练近距开局比例|50%|37.5%|25%|12.5%|0|

普通熵系数按24h从.010线性到.005；ZR额外熵系数.005，**熵属于探索正则，不计环境奖励**。
ZR/ZL仍是BC的2类按住/松开，没有静默换成3类toggle，也没有读上一按钮latch；
R/RS只允许0，所有合法主武器动作保持可选。持续记录ZR比例、熵、最长按住帧数、出刀和满蓄频率。
连续10个rollout ZR>98%且entropy<.05写`collapse-warning.json`，不以强制松开宏伪装策略。

## 课程与验收

选择更稳的“先固定.52”，不是双方同时学习：

1. easy：只依public视野/遮挡，400ms反应、有限镜头转速，普通输入，无直接姿态写入。
2. 对easy的**正常出生**评估平均武器KO≥.5且伤害≥50，下一场切现有D4 .52脚本。
3. 对D4正常出生平均武器KO≥1，切75%D4+25%冻结历史.52；历史在旧u000100/u000245间逐场轮换。
   这是固定历史池，不宣称对称自博弈已完成；旧策略较弱，旧camera档做近似重映射，不冒称完全等价。

训练初期50%近距开局随机分配，逐渐回到正常出生；明确不作门槛结果。
正式评估始终完整180秒、正常出生、无引导奖励；启动基线、30min健康评估，之后每1h一次。
每次对easy和**原有未弱化D4脚本**，sampled/greedy分别32局，报告胜率CI、武器KO、伤害、涂地、
出刀/满蓄频率、可见率与pitch触限，私有trace沿用showcase格式。

第二关门槛：对D4脚本胜率≥70% **且** 每局平均武器KO≥2；明确是哪种解码通过。
达到后保存`passed.pt`并停止GPU长训，标`gpu_gate_passed_native_precheck_pending`。
asuka0不运行游戏，原生medium/hard单房2–4局预检须在本机接着做，不能用GPU通过代替第三关预检。

6h正式正常出生D4评估仍未出现伤害则保存last并停止，输出`diagnosis.json`：
最后训练状态的可见性/几何LOS/距离/相机触限/地形与发射状态，以及独立合成平地数值控制的运行结果。
控制覆盖.52两发、70+35、回血/槽量等，不把有限loss当命中判定正确。完整评估trace保留供继续归因。
这比“近距训练打中过但正常出生从不接敌也继续跑满24h”更保守。

## 监控与停止

```sh
ssh asuka0 'cd ~/splatoon3-native-rl-stage0/bcppo81-r3 && PYTHONPATH="$PWD/src" ../.venv/bin/python -m gpu.bcppo.monitor --root train-r1'
ssh asuka0 'tail -n 4 ~/splatoon3-native-rl-stage0/bcppo81-r3/train-r1/metrics.csv'
ssh asuka0 'tail -n 1 ~/splatoon3-native-rl-stage0/bcppo81-r3/train-r1/evaluations.jsonl'
ssh asuka0 'nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader'
```

checkpoint每15min，按武器KO→伤害→胜率顺序保存`best.pt`，而非按零击杀涂地胜择优。
`checkpoints/*`/`best.pt`/`last.pt`为现有native BC2夹具可读actor，另有`*-resume.pt`含优化器/RNG/累计预算。
CSV每次更新，TensorBoard在依赖已装时启用。前后比较应对照baseline eval0，不挑一次高分。
评估seed固定用于公平的开发比较和checkpoint选择，不是新的独立最终留出；原生预检另算。

把数值日志快照取回本机后可离线生成聚合JSON与曲线（不提交生成图）：

```sh
.venv/bin/python -m rl.gpu.bcppo.report --root work/rl-bcppo/run81/snapshot-final \
  --out notes/rl-bcppo-start-20261025.json
.venv/bin/python -m rl.gpu.bcppo.plot --root work/rl-bcppo/run81/snapshot-final \
  --out work/rl-bcppo/run81/curves-final.png
```

优雅停止（只作用于本任务）：

```sh
ssh asuka0 'touch ~/splatoon3-native-rl-stage0/bcppo81-r3/train-r1/STOP'
```

需要恢复时先确认原进程退出，指定全新out并恢复同一BC身份，例如在该私有目录tmux中：

```sh
BCPPO_OUT=train-resumed-r1 sh launch.sh --resume train-r1/last-resume.pt
```

恢复会重新reset整场，不恢复中场物理/GRU；累计墙钟和退火不会重置，不承诺逐轨迹一致。
从`best-resume.pt`恢复是有意回到旧最佳，而非接续最后进度。
不要修改VPT、原录像/存档、policies或正式宿主；不恢复T1/S1。
所有地图/参数/样本/trace/PT留在本机work或服务器私有目录，不进git。
