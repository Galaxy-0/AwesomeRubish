# D3：飞索对 .52 的有限模型与原生校准

独立研究夹具，不属于策略目录，也不修改正式对战入口。游戏只在本机运行，最多三房；特殊量开关仅属于测量夹具。原始参数、网格、逐帧记录、页面产物保存在 ignored `work/` / `showcase/data/`。

目标是对声明的敌人位置、朝向、形态、行为与参数分布求期望击杀概率，并对有限行为库求 max-min。搜索最优只适用于实际枚举集合；蒙特卡洛区间、静态挂点可信度和原生校准误差必须随结果保留，不能声称证明真实玩家的普遍最优解。

先完成 `.52` 参数提取与原生测量，再进行搜索、反应式对手验证和页面接入。每阶段报告保留失败及不确定参数。护甲倍率、天花板规则仍未知；不追飞行中再次发钩的 RL_STALL。

## 第1步检查点

`notes/d3-52-20261021.md/.json`记录12个测量房、59个完整射击试验和两份转向控制；所有测量房已关闭。52／49.2伤害、9f控制两枪、原生速度约3.06u/f和220.79°/s转向有证据；30HP下限／完整曲线／纯内在散布PDF不冒称实测。

```sh
.venv/bin/python tools/zipcaster_d3/parameters.py
.venv/bin/python tools/zipcaster_d3/report_measurements.py \
  initial-range initial-turn initial-cadence control-range control-dispersion \
  control-cadence ballistic-control stationary-spread edge-angle edge-angle-low \
  --out work/d3/measurements-final.json
.venv/bin/python tools/zipcaster_d3/report_stage1.py
.venv/bin/python tools/zipcaster_d3/check_stage1.py
.venv/bin/python tools/zipcaster_d3/check_geometry.py
```

本地原件存在时可离线归约；原始游戏参数／内存不提交。`report_stage1.py`使用五份已关闭弹体归约，不能在运行日志上冻结哈希。弹体归约示例：

```sh
.venv/bin/python tools/zipcaster_d3/analyze_bullets.py \
  --result work/a6/d3-bullet-r2-20261021-170619-510304/result.json \
  --out work/d3/bullet-r2-evidence.json
```

只读测试host构建必须指定不存在的work目录；不覆盖任何原宿主：

```sh
.venv/bin/python tools/zipcaster_d3/build_sensor.py --out work/d3/new-bullet-build
```

游戏运行由当前D3任务授权，`measure.py`一次只占1房；外部调度总量仍≤3。`--bullets`配合独立弹体宿主及`--rest-frames`／`--aim-pitch-offset`保留完整控制输入。目标生命／摆位仅通过普通输入，不写HP或坐标；特殊量开关只用于后续飞索夹具。未隔离的角度／速度成因继续记录，不能把输入完成等同命中。

## 当前停止点：原生C校准失败

**D3未签收。** 第1步检查点已提交`22dcd35`。第2–4步只有有限模型原型与一轮离线算例；第5步没有合格的匹配C对练cohort，第6步未改页面。`notes/d3-model-20261021.md/.json`与`notes/d3-blocker-20261021.md/.json`是收尾权威记录。

- `model.py`：声明参数先验、飞行／两剑弹体、反应与转向、可见性门、三种有限行为的NumPy模拟。输出依赖这些假设，潜墨开火眼高、完整弹道／护甲等缺项另列。
- `batch_geometry.py`：与CollisionMesh同语义的共起点批量射线BVH；原始网格不提交。
- `search.py`：全部可达节点距离解析粗筛，单钩分位候选＋束搜索序列的精算；本轮每最终落点30u内全部敌人格，8朝向、合法形态权重、每行为8次参数抽样。
- `hooks.py`：按HookCheck材料过滤、35u连边，有限束搜索。只在模型中到达后再发下一钩，未原生验证连钩。
- `validate.py`／`aim.py`：**已知未合格的原生原型**。慢gyro与模型C准备时长不同；直接摇杆和脉冲gyro两轮未收敛，不得用于生成正式击杀率或排名。driver退出0也不代表瞄准／击杀成立。
- `report_model.py`、`report_blocker.py`、`check_closeout.py`：冻结算例、失败原件与范围审计。`passed`仅指审计通过，`full_d3_passed=false`始终保留。

离线复现须另选新的输出路径，保留本轮原件。地图数据依赖本地提取结果：

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 .venv/bin/python tools/zipcaster_d3/check_batch_geometry.py
.venv/bin/python tools/zipcaster_d3/test_model.py
.venv/bin/python tools/zipcaster_d3/search.py coarse --out work/d3/replay-coarse.json
.venv/bin/python tools/zipcaster_d3/hooks.py --coarse work/d3/replay-coarse.json --out work/d3/replay-beam.json
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 .venv/bin/python tools/zipcaster_d3/search.py fine \
  --coarse work/d3/replay-coarse.json --beam work/d3/replay-beam.json \
  --enemy-nodes 0 --samples 8 --stage 1 --out work/d3/replay-stage1/result.json
```

其它两图用`--stage 2|3`与各自输出目录；同目录的partial文件会覆盖，必须各用独立目录。完整每敌人格结果只放work，不提交派生网格；提交的notes只保留27个tactic摘要／源SHA。当前全部原生已关闭，按两轮上限停止，不恢复T1/S1，不再启动原型。
