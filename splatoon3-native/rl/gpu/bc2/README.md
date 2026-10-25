# BC第二轮：闭环对照

独立于BC1，未修改Stage1原训练器/物理、策略目录或正式宿主。
只训练Stamper主武器；.52固定为随机、D4参考脚本或历史Stage1。005整局作验证，002–004训练。

后续用户于2026-10-25明确批准跳过补录与下述BC联合门槛，直接做独立的
[BC warm-start PPO第二关](../bcppo/README.md)。BC未通过的记录及门槛数字不变。

## 固定的三项门槛

完整正常出生180s，至少16局：出刀频率≥训练人类39.333/min的30%（11.8/min）、
GPU对D4脚本有非零**武器**击倒、平均涂地≥8%。三项同时成立才进入30–60min带BC KL的PPO。
涂地赢静止对手、环境自灭、仅近距摆位命中不能替代这三项。

## 数据和传感器

`rl.demo.bc_ink`新建私有contract：唯一向上native面板、可涂碰撞格、UV非奇异、拒绝远距UV别名。
133/147以外是同一原生变换公式的几何推导，**没有冒充逐面板新增原生涂地实测**。
旧`NativeInk`精确帧真值规则不改。新数据是最多29f旧的最近一次墨图观测，并显式编码年龄。
墙面、重叠/歧义、非纯R/G像素仍未知；当前真值完整性门仍false。

```sh
.venv/bin/python -m rl.demo.bc_ink --recording work/rl-demo/my-demo-002 \
  --out work/rl-bc/new/ink-contract
.venv/bin/python -m rl.demo.bc2_export --recording work/rl-demo/my-demo-002 \
  --bc work/rl-bc/run79/bc-002 --contract work/rl-bc/new/ink-contract/contract.npz \
  --out work/rl-bc/new/data-002
```

纯数值prepared.npz、mask bank、contract、PT都在work/或asuka0私有目录，不提交。
GPU与native都按同一地面格/高度容差查询过去墨图；GPU使用仅002–004生成的缺测mask bank，005不入bank。
native运行在读取当前场景数组与contract逐值相同后才解mask；冷启动多目标图像只取逐格一致值。
GPU的蓄力HUD按既有E0预留曲线显示扣留量，不改tank、伤害、发射或回墨物理。
未补造武器阶段、弹体/实体速度。`bc2_pair`/`gpu.bc2.paired`用同一原生姿态、镜头、过去墨图检查CPU/CUDA重建。

## 方案和训练

四组各79/80/81三种子，保持数据、事件监督、训练预算一致：

- `--feedback --horizon 1`：上一输入反馈的控制组。
- `--horizon 1`：删除原始上一动作/按键反馈，保留可见形态和GRU。
- `--horizon 8`、`--horizon 16`：无反馈未来动作块，每2f查询，按对齐的概率做时间集成(exp(-age/4))。

所有输出仍是逐帧物理按住/松开，没有自动瞄准、按住到满蓄宏或攻击脚本兜底。
监督使用physical labels，ZR/ZL不再是稀有keep/press/release命令。ZR/ZL/B变化±8f和原生墨刃生成±12f加权；
可见交战片段过采样，另有none/hold/light-birth/full-birth辅助头，仅作训练目标。
轻挥横斩、满蓄纵斩的生成标记来自本地world0池化对象新setter-run代理，去掉逐帧重复；不是完整生命周期真值。

远端用原私有`~/splatoon3-native-rl-stage0/.venv`，不碰VPT；必须tmux/nohup并写日志：

```sh
export PYTHONPATH="$PWD/src"
../.venv/bin/python -u -m gpu.bc2.train --train dataset/data-002 \
  --train dataset/data-003 --train dataset/data-004 --val dataset/data-005 \
  --horizon 8 --seed 80 --out fit-new > fit-new.log 2>&1
```

## 闭环和观测分布

`gpu.bc2.evaluate`跑完整180s；`--kind random/script/history`，history需`--opponent`。
默认greedy argmax；`--stochastic`作独立诊断。`--camera-decode expectation`只对有序yaw/pitch档求期望再量化，
不改模型权重或按钮决策；若没有收益应保留argmax基线，不宣称它自动修好镜头。
导出trace v1与私有分布探针，`distribution.compare`报告每分量均值/方差/KS，空实体集保留null。
同姿态数值重建一致不代表自由闭环状态分布一致，后者必须单独报告。

原生入口在普通capture夹具上追加：

```sh
--fixture-bc-checkpoint work/rl-bc/new/fit/best.pt \
--bc-ink-contract work/rl-bc/new/ink-contract/contract.npz
```

只允许script-source、primary_only、.52对手；最多一房。人类录制不加上述参数，继续原实时录制路径。
下一批人类数据与完整命令模板见`rl/demo/bc-recording-plan.md`。
