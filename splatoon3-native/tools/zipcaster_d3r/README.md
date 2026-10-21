# D3-R：直接瞄准的理想操作上限夹具

默认关闭，只用于本机研究。先定位原生实际用于钩索/弹道的状态，以手柄达到同方向作实测对照；写入方向不是游戏机制、武器伤害或位置/HP修改。正式 arena/T1/熟练度禁止测试开关；独立宿主和模块只生成到全新 work/d3r/ 目录，不替换默认宿主/原模块/存档。

按 work/codex/d3r.txt 执行：1 方向等价性 → 2 三图瞄准/实际绑定映射 → 3 俯仰与两刀上限 → 4 原生分档/留出校准 → 5 操作速度20/40/60/129f模型 → 6 页面。≤3房，保留原件；两轮真实无进展停止。第一轮先读取并验证PlayerCamera owner/vtable与候选状态，不把网络包副本写入当作瞄准成功。

## 第1步已完成（受限物理方向对照）

证据见 `notes/d3r-step1-20261021.md/.json`。最终测试宿主`work/d3r/aim-v1/dmhost-aim`；同向轻斩/满蓄各3发方向差2.56e-6°/0°，钩尖0.029878°；.52均值差0.786455°落在组内散布范围。直接改方向实际改变墨刃方向，关闭时文件请求不生效。只有已测方向/姿态的见证，不声称所有情况或RNG流等价。

```sh
# 每次构建选择不存在的work路径；不覆盖已有构建。
.venv/bin/python tools/zipcaster_d3r/build.py --out work/d3r/new-aim-build
.venv/bin/python tools/zipcaster_d3r/probe.py --name new-sword --mode sword \
  --host work/d3r/new-aim-build/dmhost-aim
.venv/bin/python tools/zipcaster_d3r/probe.py --name new-off --mode gun --disabled \
  --host work/d3r/new-aim-build/dmhost-aim
.venv/bin/python tools/zipcaster_d3r/report_step1.py
```

`control.py`只供可信测量驱动：显式`new_lab(host)`→`fixture(lab)`→`set_native(player,yaw,native_pitch)`。测试标志注入该自建host的options，永不设置全局环境以绕过正式入口；读写文件是fixture私有的单调序号/有限角命令，不是策略API。普通导航/回墨准备必须先`off()`；写入每帧在游戏正常相机计算上下文消费，native pitch不等于世界仰角。默认宏不进生产宿主，源/build/module哈希与实际原件绑定。

`hook_mapping.py plan|room|batch`是下一步的预定120方向夹具。每房8次独立自然回程，不战斗、不到飞行中再R；三房上限由批处理父进程约束。plan输出新路径且事前固定train/held-out；记录实际输入、tip/锚点/法线、到达姿态和失败，不把请求锚点当实际挂点。第2步尚未完成，不应直接把计划当预测准确率。

## 第2步：120方向闭合映射

`notes/d3r-mapping-20261022.md/.json`：每图40，实际锚点/法线/到达姿态和失败均留存。最终未参与拟合48次中墙面候选35/36正确，完整方向41/48；近地面/边界不外推。代理半径不是原生半径。测量只签绑定/位置，不签击杀率或最高挂点。

```sh
# fresh output paths; parameter files immutable, evaluation never refits.
.venv/bin/python tools/zipcaster_d3r/ray_model.py freeze \
  --snapshot work/d3r/mapping-partial-closed5.json --out work/d3r/new-ray.json
.venv/bin/python tools/zipcaster_d3r/sweep_fit.py evaluate \
  --parameters work/d3r/sweep-v1-frozen.json --out work/d3r/new-evaluation.json
.venv/bin/python -m unittest tools.zipcaster_d3r.test_ray_model tools.zipcaster_d3r.test_sphere_cast
```

历史冻结链：R1线性竖直分量；R2正切方向只用批0/1训练，批2–4确认；R3扫掠/材料只用批0–2事前train，批3/4确认。早期开发held-out不冒称最终盲测。70种离散候选设置和冻结时刻记录到JSON；不按最终确认结果反复改参数。

## 第3步：显式刀种、真威胁与操作档

证据`notes/d3r-mechanics-20261022.md/.json`。有效执行器为`duel_v3.py`（三图静止靶控制）、`duel_v4.py`（同一满蓄+轻斩，另加三轻斩程序）；`weapon_aim.py`用显式full/light，禁止从full-flight之类阶段字符串猜刀种。两份`reactive_control.py`使用过滤观测R18/有限转速，实测52→KO，35f/70f。

`blade_probe_v2.py`使用普通涂地/回墨恢复靶，`analyze_blades.py`分开35/70/52瞬时伤害和敌墨慢性掉血。最初probe/duel原型及错误版代码只保留在对应work原件和tested副本，不作为正式执行器。20f满蓄预蓄控制`precharge_probe.py`只出轻斩；不能画成满蓄成立。20档仅light3（已测35+35+剩余30），40/60/129比较full-light与light3。帧数定义为到达确认→发射动作（满蓄松ZR/轻斩按ZR），生成6/11f另计；到达读数有4f采样窗。

`ideal_search_v2.py`枚举18个实测墙面起点/挂点、四操作档与合法程序，共126份有限估计；全可达格粗筛，近30u每点12敌位×8向×有效形态、三行为、MC16精算。不是全地图连续挂点最优证明，也不是把未精算格插值成真实概率。`native_kinematics.py`是两份低墙B6的数值派生，`blade_field.py`用参数core radius.3/.5和场地扫掠；两个轻斩原生停止点复现<.001u。侧球、动态物体、晚期曲线与高墙地面外推仍有界限。`ideal_search.py`/v1结果是修正前快照，20满蓄项已被实测否定，不用于推荐。

`calibration_plan_v2.py`事前固定54案：六点/图、按40f full-light新模型分高/中/低，每点三个人形站位/朝向，试次0/1训练、2留出。站位从bravo可达格5..20u、距源>=9u中均匀抽，不按原生胜负挑选；和全图先验分开报告。`batch_duel_v4.py`固定<=3房，源/参数/计划SHA冻结，setup void与战术绑定失败分开；不自动重抽战斗失败。
