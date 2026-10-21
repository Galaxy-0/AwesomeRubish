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

## 新机制恢复（2026-10-21，进行中）

按玩家B跳离与槽预算提示重置卡点计数。`hint_probe.py` / `report_hint_summary.py`为独立新cohort，旧停止原件不动。机制检查点见`notes/d3-hint-20261021.md/.json`：B6两图静止靶KO、到达后预瞄/B/续钩见证、XOR剩余计数与动作成本。

`budget.py`有限随机资源DP、`model_v2.py`跳离/落地模板与预算、`search_v2.py`/`hooks_v2.py`另路径重跑；当前仍未完成原生排名校准与多目标条件转移。`validate_hint.py`是新B6/有界普通瞄准对练原型，只把通过前置条件的窗口标可统计，结果仍需与同条件模型匹配。不得把`calibration_eligible`等同已校准。运行命令、原件SHA及未定项见检查点；不覆盖任何旧输出。

## 恢复后的第4/5步（2026-10-21）

上面的“停止点”是旧轮历史。新B/预算方向已完成27路径v2续算、两组真实.52威胁控制，以及每图6点×3初态的54案校准；见 `notes/d3-model-v2-20261021.md`、`notes/d3-reactive-controls-20261021.json`、`notes/d3-calibration-v2-20261021.md/.json`。结论仍是原生最高挂点未证明，不把弱相关或全负留出集的误差下降当验证成功。

- `batch_calibration.py select|batch`：固定种子初态、每图高/中/低两点，独立进程至多3房。`--attempt 2`仅在测量前经hub/普通涂地潜墨恢复健康；不能修复已经发生的战斗结果。失败原件保留。正式批次源码已归档到其`source-snapshot/`，测试自己的源与通用helper分开绑定。
- `report_calibration.py` / `native_calibration_data.py`：实际锚点、HP、过滤可见门、输入与失败归约；先验不同的排名单列。试次0/1训练，试次2留出。`calibration_stats.py`无SciPy依赖，支持并列秩和Beta区间。
- `calibrated_model.py`：独立控制替代模型，旧`model.py/model_v2.py`和所有旧遍历不动。0.25/0.50只是有效控制保留率，不能当武器伤害/普遍精度。最后弹体发出前须符合R时0.96槽；发出后的等待可触发声明的回程路径，不抹掉已发弹体。
- `joint_duel.py/joint_search.py/report_joint.py`：双敌共享水刀HP/槽、敌HP跨出刀保留的有限程序比较，另有回程受伤两种边界；没有原生双敌认证。`budget.py`只对调用方给定的有限条件核求DP最优。
- `search_calibrated.py`：同27方案以训练参数重算，不重新择优抽样或覆盖v2；初始潜墨开火后视点转人形是显式近似，材料/落点/弹道结构误差未解决。页面仍标模型未认证。

```sh
PYTHONPATH=tools/zipcaster_d3 .venv/bin/python -m unittest discover -s tools/zipcaster_d3 -p 'test_*.py'
.venv/bin/python tools/zipcaster_d3/report_calibration.py \
  --batches work/d3/calibration-v2/final/batch.json work/d3/calibration-v2/retry/batch.json \
  --out work/d3/new-fit
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 .venv/bin/python tools/zipcaster_d3/search_calibrated.py \
  --input work/d3/fine-v2-stage1/result.json --calibration work/d3/new-fit/report.json \
  --out work/d3/new-corrected-stage1/result.json
```

所有输出用新路径；完整每敌人格热度、native逐帧和派生图不提交。`return_control.py`为有界回程受伤夹具；没命中不能反推无敌，不追飞行中再R。当前只交付研究模型/可视化，不改变策略、正式host、存档或T1/S1状态。
