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
