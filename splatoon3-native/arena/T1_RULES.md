# T1 规则（策略作者必读）

你是 T1 的一名策略作者（alpha 或 bravo），和另一名作者在 1v1 占地对战里对抗。

- 武器固定工作刮水刀（weapon = 8000）。配装（头/衣/鞋 主技能 + 各 3 个副技能）由你在 config.toml 自由声明，必须合法。
- 只写你自己的目录 `arena/policies/<你的名字>/`（policy.py、config.toml、可加辅助模块和 NOTES.md）。公共库 `arena/lib/` 只读、不得修改。
- **不得读取对方目录**（`arena/policies/alpha|bravo/` 中不是你的那个）、不得读取 `work/codex/t1/` 下对方的日志或输出。可以读 rush / high-ground 示例。
- 策略必须可解释：规则 / 状态机 / 打分函数，带注释说明战术意图。不要训练模型。
- 观测、动作、步长与超时规范见 `arena/policies/README.md`。超时会让整局失败。
- 地图：三张已选图（温泉峡谷、District00、Yagara），每局换边。
- 本地自测：每轮最多用 1 个房间（`--parallel 1`）对 rush/high-ground 跑，合计 ≤ 6 局；不要跑多房间，机器资源要留给正式擂台。例如：
  `.venv/bin/python tests/test_a5.py --policy-a arena/policies/<你> --policy-b arena/policies/high-ground --games 2 --parallel 1`
- 不要 git commit / push（由指挥方统一提交）。不要改宿主、擂台、测试代码；发现擂台 bug 写进你的 NOTES.md 由指挥方处理。
- 每轮结束时在 `arena/policies/<你>/NOTES.md` 追加：本轮改了什么、为什么、对对手的推断、配装理由。
- 战报：每轮正式擂台结果放在 `work/arena/reports/<你>/round-<N>/`（胜负统计 + 对局目录路径，可看截图与逐帧记录）。
