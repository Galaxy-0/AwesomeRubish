# S1 offline 1v1 simulator

Python + NumPy，只做工作刮水刀、占地、Yunohana / District00 / Yagara。
此目录的程序不构建宿主、不启动游戏、不修改原生擂台或策略。
从项目目录用 `.venv/bin/python -m sim.parameters` 开始。

参数从本机 `work/data/v720896/RomFS` 只读提取；碰撞/导航复用
`work/arena/maps`。提取结果默认写 `work/sim/parameters.json`，包括来源和
条目 SHA256，禁止写到 work 之外。不随源码分发游戏表、地图或原生记录。
需要本机已安装的 NumPy 和 zstd，以及项目现有 BYML/SARC 只读解析器。

注意：参数表是稀疏覆写，不含全部 C++ 默认值。缺失的移速/重力/回血回墨/
重生/配装曲线必须标记为近似或待校准，不能当作已提取值；目录 Range
也不能当成世界坐标射程。A6 实测边界与参数计数分开使用。

推进顺序：参数 → 核心移动/粗涂地/墨刃/HP/重生/墨量 → 历史同输入对照。
乌贼滑、墙蓄跳、冲刺斩、快速炸弹、触手喷射留在本轮核心对照后的阶段。

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
加首帧边界，站立21/出墨26是 A6 实测锚点。墨量在释放时扣款，尚未模拟原生
蓄力过程的预扣/退款，因此中途墨量曲线存在已知差异。

`Assumptions` 集中所有未提取默认值；A2 的 AP19 游速与 AP38 主墨效只是两个
经验锚点，其间线性插值不代表原生技能曲线。其他配装效果在 `unsupported`
中列出。输入 R/RS 会记录未实现操作；乌贼+B只执行普通跳跃并标记不支持，
不会把它计为已实现乌贼滑。冲刺斩尚未实现；前推满蓄目前仍按普通蓄斩处理。

地形来自已提取的 `human.npz`，视线来自 `sight.npz`；多射线扫掠加端点球体距离
近似碰撞。涂地以导航节点为带高度层的粗格，墙阻断传播、同队重复涂色不再次
充能；计分分母含未涂格。节点可潜游性不等于原生可计分地面，原生纹理/涂点
映射仍未知。特殊量有近似面积充能，大招效果留待后续。出生从导航落地点开始，
重生直接回落地点，不模拟发射台飞行。移动/跳跃、回血回墨和重生均待实机校准。

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
当前 CPU 串行步进，不宣称已向量化或通过官方 Gym/PettingZoo API 验证；尚未
提供 spaces/注册适配器。核心每帧不做渲染，无需游戏引擎。
