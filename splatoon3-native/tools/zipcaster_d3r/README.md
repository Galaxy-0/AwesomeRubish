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
