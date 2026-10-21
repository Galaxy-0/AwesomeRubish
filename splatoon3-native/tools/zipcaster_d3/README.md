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
