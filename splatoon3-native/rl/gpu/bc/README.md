# 人类示范 BC 首版

只训练工作刮水刀；复用 Stage1 的公开观测编码和 GRU，加显式有效性编码。
副武器和特殊武器禁用，ZR/ZL 为 keep/press/release，其他键为电平。
不修改原 Stage1、策略目录或正式 arena/T1 入口。

## 数据与划分

在项目根运行原生状态同步转换。数值/录像/网格/模型都保留在私有 `work/`，不进 git：

```sh
.venv/bin/python -m rl.demo.convert \
  --recording work/rl-demo/my-demo-002 --out work/rl-bc/new/bc-002 \
  --camera work/rl-demo/run70/camera-nonlinear-r2.json --allow-approximate
```

`--allow-approximate` 明确允许本轮不完备数据试训，不代表升级 `ready_for_training`。
缺失 HUD/射线墨色/minimap/实体速度在送入网络前清零，并额外编码有效性。
状态同步零积分；`rl.demo.dynamics_audit` 独立报告自由积分漂移，不能混用作观测。
只读 human_USB、native_state_sync_only 的 shard，拒绝不可训练标签/非法动作。
完整局划分，禁止 train/val 同路径；序列不跨局、缺帧或分片拼接处的真实间隙。

## asuka0 私有环境

沿用 `$HOME/splatoon3-native-rl-stage0/.venv`；不使用 VPT 环境。
`rl.gpu.deploy` 上传 allowlist 源码、私有 map/参数和标定；另外上传转换后的私有 shard。
部署后目录形如 `bc79-r1/{src/gpu,data,dataset}`。下面是 **tmux 后台脚本** 内容：

```sh
export PYTHONPATH="$PWD/src"
../.venv/bin/python -u -m gpu.bc.train \
  --train dataset/bc-002 --train dataset/bc-003 --train dataset/bc-004 \
  --val dataset/bc-005 --out fit-new --seed 79 --edge-balance > fit-new.log 2>&1
```

1,739,465 参数；64 决策 BPTT、batch16、AdamW3e-4、最多50 epoch/耐心8。
原始基线不加 `--edge-balance`。该选项仅对 ZR/ZL 按训练集频率的平方根倒数加权，
权重上限8；不做自动蓄力宏。验证集依相同权重选择 checkpoint，报告仍列未加权 CE。
所有多数类/Markov 持续性先验只在训练集拟合。005 是用于早停/诊断的验证集，**不是独立测试集**。
逐头准确率不能代替闭环出刀和武器击倒；特别注意上一动作反馈导致的复制捷径。

## 评估

```sh
export CC="$HOME/splatoon3-native-rl-stage0/cc-zig" CXX="$CC"
../.venv/bin/python -u -m gpu.bc.evaluate --checkpoint fit-new/best.pt \
  --data data --calibration data/native-camera-calibration-v1.json \
  --kind random --games 16 --seed 79001 --out eval-new > eval-new.log 2>&1
```

另测 `--stochastic`、`--kind d4-spawn`、`--kind history --opponent 私有历史PT`。
`d4-encounter` 是独立的近距摆位诊断，不冒充正常出生结果。
所有对局按终止信号完整跑180秒，Stamper固定role0，.52分支没有BC训练。
GPU/原生部署保守屏蔽墨色/武器阶段/弹体速度；原生稀疏墨图不会伪造连续真值。
命中指标是造成伤害的决策数/出刀次数，含接触/墨刃；不是逐发物理命中率。
轨迹用已有 showcase trace v1，私有保存，不自动发布。

原生可用 `rl.demo.capture --fixture --source script --fixture-bc-checkpoint 私有PT`。
只能 primary_only、对手52，与输入回放/其他玩家策略互斥；不接手柄。
读取当前原生状态与因果相机样本生成公开射线/可见实体后送入同一网络；
离散视角通过独立标定矩阵反解为普通 gyro 输入，**不直接设置瞄准**。
此 CPU 观测重建夹具不承诺人玩实时60，不改变人类录制默认路径。

本轮只有 BC 及评估。只有闭环相对基线的实质收益明确，才能再启动带 BC 正则的 PPO；
多数类准确率提升或靠涂地赢静止对手不满足这个条件。
