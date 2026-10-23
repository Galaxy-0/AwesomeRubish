# 阶段1：主武器基础对枪

阶段0已获用户接受。只运行阶段1，不开放任何副武器/特殊武器，不运行T1/S1原流程或原生宿主。
地图温泉峡谷、工作刮水刀8000 vs .52(50)、fixed60、180秒涂地。

本轮已按两轮无进展停止，阶段1未通过；下列命令是复现说明，不是已安排的续训。

## 接口与网络

`Policy`基版1,581,513参数，`--action-feedback --control-prior`版1,632,841参数：32×18射线三层小CNN；实体MLP+mask后的mean/max DeepSets；
HUD和16×24池化墨色minimap分别MLP；武器embedding；384维GRU；八个离散动作头和value。
共享网络复用移动/观察学习，embedding区分两把武器。actor/value都只用public obs；
内部state仅用于环境、离线摆位、记录与明确标记的D4参考脚本。

HUD新增自身四档受伤反馈，作为屏幕受击程度代理，便于学习残血恢复；不提供敌方HP。
`action_mask[N,2,8,17]`屏蔽各头补位和R/RS=1。环境执行端再强制清除禁用键；
ZR/ZL/B保持独立电平。阶段2前必须补齐.52水帘和5.1声波炮，不能直接把full配置当完整套装。

FOV明确是假设：竖55°、16:9横85.56559°（按标准公式，不将近似88°强行写入）。
原生+5转速/eye-at读数沿用阶段0；投影轴向待一次已知敌位的截图坐标核验，不阻塞训练。
1u粗几何最大4.34u误差保留，不以PPO成绩升级原生保真度。

## PPO和历史池

默认256并行局、2f决策、128决策rollout、32步BPTT、3个PPO epoch、clip0.2、
gamma0.9995、lambda默认0.95（反馈实验0.99）、Adam2e-4、grad clip0.5；初始循环状态从采样序列保存。
终局截断GAE并清GRU记忆，死亡不是一局结束。历史动作不进入PPO损失。
50%当前对当前、40%历史对手（两个20% cohort）、10%保持16决策的随机对手；
每40次更新快照，历史版本只在新一局切换。共享版本池同时保存两把武器。

奖励保持用户约定；辅助项与早期近距初始摆位在**计划训练预算前30%**线性退火到0。
摆位curriculum最多70%训练局，普通地图地面6–18u、无遮挡配对，渐退回正常出生点；
不改动作/伤害/物理/局长，不给目标坐标。验收独立报告正常出生点与固定敌态遭遇战。
分段续训使用同一`--schedule-frames`，禁止延长训练时把已归零辅助重新打开。
续训恢复网络、优化器和池，重新开完整局；不宣称位级恢复中途对局。

## 运行（服务器私有目录，必须tmux/nohup）

先从本机项目根用`python -m rl.gpu.deploy --version stage1-rN --data 私有导出 --calibration 私有标定JSON`
上传源码与数据；版本目录不可覆盖。安装使用已经验证的独立`.venv`，不碰VPT。
以下是**后台脚本内容**，SSH只启动和轮询：

```sh
cd "$HOME/splatoon3-native-rl-stage0/stage1-rN"
export PYTHONPATH="$PWD/src"
export CC="$HOME/splatoon3-native-rl-stage0/cc-zig"
../.venv/bin/python -m gpu.stage1.train --data data \
  --calibration data/camera-assumption-v1.json --out ../stage1-run-new \
  --n-envs 256 --frames 64000000 --schedule-frames 64000000
```

独立`checkpoints/*.pt`和JSON记录版本/帧数/配置/源码与私有数据SHA；不进git。
`metrics.csv`记录损失、熵、KL、梯度、伤害、倒下比/涂地、墙钟和显存；
`matches.jsonl`保存每局cohort/池版本/比分。安装有TensorBoard则自动写event，无则完整CSV。
`STOP`文件在更新边界停止；最后进度以新checkpoint为准，不用kill训练进程。

```sh
../.venv/bin/python -m gpu.stage1.assess --checkpoint ../stage1-run-new/checkpoints/u000977.pt \
  --data data --calibration data/camera-assumption-v1.json --out ../stage1-eval-new \
  --games 128 --stochastic --history ../stage1-run-new/checkpoints/u000000.pt
```

`evaluate/assess`对随机双方角色均衡；D4参考为固定180°半平面、30u视距、13.4u开火、
静止、原D4直接瞄准且不补弹道下坠；它明确读取裁判位置，不是网络特权观测。
潜墨对手隐藏；脚本先有近距两枪阳性控制。D4正常出生点占地与近距三常见站位队列分开。
每次评估输出所有逐局结果和showcase trace，不能只选赢局。
历史版本输出按武器分别的Elo描述（batch K24、初始1000），不作全局玩家排名。

预先口径：双方对随机各胜率≥95%、Wilson95下界≥90%；水刀对D4的Wilson下界>50%。
固定敌态遭遇队列单列，避免仅绕开出生区站桩敌人涂地就证明对枪能力。
回血/受伤后掩体位移自动数只作线索，最终必须看回放；曲线稳定也要审查，不能自动签收。
阶段1达门槛或两轮无进展后停；不启动阶段2。

## 检查

```sh
RL_STAGE0_DATA=work/rl-stage0/data-v5 .venv/bin/python -m rl.gpu.test_env
RL_STAGE0_DATA=work/rl-stage0/data-v5 .venv/bin/python -m rl.gpu.stage1.test_learning
```

9项学习检查覆盖mask+物理防线、GRU终局重置、DeepSets排列不变、GAE终局截断、
PPO更新/历史样本屏蔽、固定.52的正面KO/背面不开火、无伤自落不计击杀控制、自身动作反馈隔离与循环序列logprob重算一致性。原14项环境单测继续保留。
事件第6项单列武器击倒；自落不给对手伪造击杀奖励，延迟推落助攻暂未建模。
算法依据：[PPO原论文](https://arxiv.org/abs/1707.06347)。


验收部署策略默认遵循训练时的masked categorical采样；greedy取各头最大值另作诊断，
不能将二者混成同一策略。使用`assess --stochastic`可评估实际采样策略；保留greedy原结果，
最终验证使用预先固定的新种子，不通过重抽赢局来改变胜率。`--pool-history`逐一评估checkpoint
中保存的所有历史快照，并输出分武器Elo表。


## 本轮状态：未通过，已停（2026-10-23）

两种配置各32,047,104帧，水刀对随机均较自身初始模型退化：基版55/64→2/64，
反馈版34/64→12/64；反馈版.52训练前后均64/64，不能把初始先验成绩归功于RL。
近距D4计分胜场不代表击倒；残血潜墨恢复为0。两轮无进展已停止，示例运行命令不是待执行任务，
不追加64M或进入阶段2。数据/显存/区间与原件路径见`notes/rl-stage1-20261023.md`及results JSON。

反馈版把自己上一控制输入嵌入128维，不提供敌人信息或手工世界记忆。
控制先验只是可训练logit初始偏置，所有合法动作仍可能采样；GRU和PPO都训练，
不强制宏/动作保持。旧checkpoint缺少flags时按基版加载。新增CLI `evaluate --trace-env 1`
可记录learner为.52的奇数环境；不要把env0的随机.52当作learner。
评估记录实际禁用输入计数；CSV完整，当前未安装TensorBoard，event写入为可选项。

## 2026-10-23 恢复：先验证输入与出刀能力

用户采纳Astra只读分析并重置卡点计数；此前两个32M失败结果仍保留。
新增`controller.py`：`--button-semantics toggle`将ZR/ZL变为0保持/1按下/2松开，
底层仍按原决策间隔输出0/1电平，无自动蓄满释放。`prepare`的mask对应命令空间；
PPO保存命令标签，环境/回放保存物理电平，自身上一物理输入用于反馈。
旧checkpoint缺省level语义，跨语义不能直接resume。

`drills.py`提供仅水刀更新的固定/随机距离朝向/移动靶/弱脚本夹具；后面三项必须逐级能力通过才运行。
当前先在合成平地隔离控制问题，使用相同相机/武器数值，不能当温泉峡谷正式对局。
`--mode ablation --seeds 101 202 303 --trial-frames 10800`做未训练ZR/ZL表示对照；
`--kind fixed --button-semantics level|toggle --seed N --updates 128`做配对ZR课程。
`--fixed-distance 21`另测远距离满蓄；离线确定三轻斩无伤、两满蓄可KO后才用于课程。
训练过程中辅助恒定1；没有按住/出刀输入奖励。短尝试局长显式记录，能力门与正式180s门分开。
每组至少3种子，版本/输出目录不覆盖。进阶依据独立KO/满蓄能力，而非帧数到期。

PPO现在将优势归一化分母限制≥0.02、逐minibatch更新前检查KL，记录逐动作头熵/KL、
按武器优势与非零奖励率；配对实验两臂共同使用这些设置，不将效果单独归因于某项稳定性修改。
`encounter_starts`补足有效近距配对并随机选环境行，拒绝静默缺额；旧`train.py`的帧退火保留作历史复现，
恢复期间不使用该旧入口跳过能力课程。`evaluate.py`按term/trunc终止，并以配置游戏时长做超时保护；
正式环境仍默认180秒，sampled/greedy分开报告。增加控制转换逐帧等价、toggle循环logprob、
3f决策终止、KL越限不更新/优势下限、近距配对补足及随机分配检查。当前13项学习组件通过。
