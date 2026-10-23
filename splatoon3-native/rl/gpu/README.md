# RL stage 0: GPU environment

工作刮水刀8000 vs .52(50)、温泉峡谷1v1、fixed60、180秒的近似环境。
仅环境实现，没有训练器；T1/S1入口、策略、正式宿主和原存档不修改。
阶段状态与误差见 `../../notes/rl-stage0-20261023.md` 及同目录后续报告。

## 安装与隔离

asuka0私有根目录 `~/splatoon3-native-rl-stage0/`，权限700，独立`.venv`。
固定Python3.13、torch2.12.1+cu126、numpy2.2.6；不使用或修改VPT环境。
`bootstrap-remote.sh` 是首次安装入口。已有下载优先复用pip缓存；
`bootstrap-cached.sh` / `bootstrap-resume.sh` / `bootstrap-mirror.sh`
保留本次有状态恢复流程，依赖前次 `.exit` 与校验清单，不应盲目并行执行。
镜像依赖必须与独立官方PyPI SHA256匹配；torch来自官方cu126索引。
`bootstrap-toolchain.sh` 将Python开发头文件解包在私有目录，不安装系统包；
需要先在独立venv安装`ziglang==0.13.0`，用作用户目录C编译器。

所有长任务用自己创建的tmux会话与日志，SSH只做启动/短轮询。
网络抖动按30/60/120s退避；一次断线不算数值/工程卡点。
服务器不运行游戏或原生宿主。原生测量仅本机的独立work构建与存档副本。

## 私有数据与执行

以下在项目根执行，地图/参数/回放/报告都写入已忽略的work目录。

```sh
.venv/bin/python -m rl.gpu.data --out work/rl-stage0/data-new
RL_STAGE0_DATA=work/rl-stage0/data-new .venv/bin/python -m rl.gpu.test_env
.venv/bin/python -m rl.gpu.deploy --version source-new --data work/rl-stage0/data-new
```

远端上传仅允许GPU Python源码、README和校验过的私有NPZ/JSON；
不传宿主、资源、存档、策略或VPT文件。远端`source-new/src/gpu`作为模块根：

```sh
export PYTHONPATH="$PWD/src"
export RL_STAGE0_DATA="$PWD/data" RL_STAGE0_DEVICE=cuda
export CC="$HOME/splatoon3-native-rl-stage0/cc-zig"
../.venv/bin/python -m gpu.test_env
../.venv/bin/python -m gpu.test_cuda --data data --out ../cuda-parity-new.json
../.venv/bin/python -m gpu.run --data data --out ../bench-new --n-envs 1024 \
  --compile --fast-rays --cuda-graph --steps 500 --warmup 10 \
  --calibration data/native-camera-calibration-v1.json
../.venv/bin/python -m gpu.run --data data --out ../random-new --n-envs 4 \
  --mode random --fast-rays --cuda-graph --trace \
  --calibration data/native-camera-calibration-v1.json
```

示例命令必须从自己的后台脚本运行；`remote-checks.sh`提供顺序检查入口。
输出目录必须是新的，避免覆盖实验。`compare.py`导出本机S1同输入参考，
`replay_s1.py`在CUDA重放该参考；`compare_map.py`另报真实地图粗几何误差。

## 张量接口

`ParallelEnv(data, Config(...), n_envs=N, device='cuda')`：

- `reset(seed, options={'mask': bool[N]}) -> obs, infos`，无静默自动重置。
- `step(int64[N,2,8]) -> obs, rewards[N,2], terminations[N,2], truncations[N,2], infos`。
- 动作字段 `move,yaw,pitch,ZR,ZL,B,R,RS`；范围17/9/9/2/2/2/2/2。
  按键是持续电平，释放沿/按下沿由环境记忆；移动相对当前镜头。
- `screen[N,2,18,32,4]` = 距离/地墙人无/表面墨色/可挂。
  `entities[N,2,16,7]` = 屏幕xy/距离/类型/镜头相对速度，另有mask。
  潜墨对手不出现；视野/场地遮挡过滤后补零。HUD只给自身状态/时间/比分，
  minimap只给墨色，不给敌人位置；audio为空接口。
- `state/shots/paint`是裁判内部，禁止作为agent观测。记录器可显式转CPU保存真值。
- 奖励对称零和；伤害辅助按受害者每条命最多100，回血不清计数。
  `set_auxiliary_scale(0..1)`退火伤害与涂地辅助，保留击杀和局末胜负奖励。
- `GraphEnv`只用于CUDA，捕获内回写持久输入缓冲，支持部分重置。
  单测比较连续变化动作的完整状态/弹体/涂地/观测，防止只重放冻结帧。

## 近似边界与验收

本项目不是原版物理重实现。S1相符也不等于原生保真签收。
私有1u导航/表面体素替代连续碰撞，坡面/薄墙/台沿会偏差；
玩家胶囊、接触OBB扩展角点、简化击退、枪弹距离曲线与散布模型均须独立报告。
快速炸弹将直击与爆风合并在碰撞时结算，不声称原生延迟相同。
`.52`目前实现主武器；其R/RS套装范围待明确，不能把忽略输入当完整套装。
接触遮挡默认`whole_shape_clear`，半片裁剪默认`whole_wave`；
替代开关`ignore`/`independent_halves`均是未闭合机制假设，不是已证实规则。
飞索ARM字段不代表已证明护甲效果。

镜头+5由原生临时控制副本测量，无存档写入；陀螺上限π/12rad/f是人手上限假设。
标定JSON的`accepted`/轴向核验会保留真实状态，不因跑通而自动置真。
未提供标定时run使用明确标记的合成夹具参数，不能冒称原生标定。

门：GPU/S1误差、关键机制单测、180秒随机局、私有showcase回放、
原生镜头测量，以及含完整观测≥200,000环境帧/s。
计数=N×实际fixed60帧，不乘2agent；计时同步GPU，排除编译/重置/RNG须明示。
`preview.py`仅生成work内私有回放QA页，不发布、不修改showcase原始数据计算。
