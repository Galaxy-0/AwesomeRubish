# run72：003首次动作复核与游戏内方向短测准备（2026-10-24）

本轮只离线读003、改自检/录制端提示及准备用户命令；未打开SDL设备、未启动游戏、未训练。policies、正式arena/T1/A8宿主、原存档不改，T1/S1保持暂停。

## 复核结论：不能把003的yaw/roll升级为已确认

003关键键通过：ZR axis5、ZL axis4、B btn1、R btn10、RS btn8、Y btn3；其他已识别键沿用报告。Minus/Plus/十字上保持未确认。pitch原报告的x+正反配对结论按用户指示保留，其来源明确为“previous accepted pitch pair”，不伪称新版首次动作也通过。

按所有轴中**首个超过0.35rad/s**的采样锁定动作（减静置零偏，不取峰值、不跳过开头去挑期待轴），得到：

|提示步骤|相对该步骤首个IMU采样|首次向量 x/y/z（rad/s）|结论|
|---|---:|---|---|
|yaw_left|3.172592s|−0.480 / −0.162 / −0.097|主轴x，非期待y|
|yaw_right|0.032886s|−0.369 / −0.181 / +0.212|主轴x，非期待y|
|roll_left|0.194258s|−0.353 / +0.226 / −0.087|主轴x，非期待z|
|roll_right|1.221182s|−0.331 / +0.352 / −0.133|主轴y，非期待z|

0.2/0.5rad/s探索也未得到四步一致的轴向与反向配对：例如0.2时yaw_left首先y负（与“向左”期待的y正相反），roll_right首先是y动作；0.5时yaw_right先z正，roll_left先x负。阈值不能为追求通过而逐步更改。

因此用户/Claude提及的后段yaw_right y负、roll_right z负，与SDL约定可以相容，但**不是全轴首次动作的闭合证据**；可能混有握姿调整/回位。不能仅挑这两段把所有方向标为实测通过。

本机 `/opt/homebrew/include/SDL2/SDL_sensor.h` 明确rad/s、逆时针为正、x=pitch/y=yaw/z=roll。以正常握姿解释，采用右转y负、右倾z负作为下一次视觉短测假设。宿主已有键盘夹具约定抬头+X/右转+Y/右倾+Z，因此把物理方向投到宿主时采用 `[SDLx, −SDLy, −SDLz] / 2π` 并减零偏；是否正确驱动游戏镜头仍由画面对照确认，不由终端输入方向字样判定。

## 已准备的私有配置

- `work/rl-demo/controller-check-003-rechecked/audit.json`：逐步骤首次动作与原件四文件SHA。
- `work/rl-demo/controller-check-003-rechecked/profile.json`：沿用003按钮/摇杆基线，pitch已确认；yaw/roll `valid=false`、basis为 `SDL convention assumption`。
- `complete=false`、`scope=direction_check_only`、`usable_for_direction_check=true`。仅 `capture --direction-check` 显式接受，普通录制拒绝；不把诊断数据升级为训练就绪。
- Minus/Plus没有补填默认映射，组合提前结束不可用；改用Ctrl-C/STOP文件。
- 原003的report/profile/summary/samples全部保留，四份SHA复核一致。只提交[汇总数值/哈希](rl-demo-direction-20261024.json)，原始输入和派生profile留work。

复核可复现：

```sh
.venv/bin/python -m rl.demo.controller_recheck \
  --source work/rl-demo/controller-check-003 \
  --out work/rl-demo/controller-check-003-rechecked
```

该输出已生成；若再次运行需换新out，不覆盖本次或原003。

## 自检改动

1. `gyro_gesture` 锁首个越阈值的轴与符号，检查30ms同号/明确主轴；首次混轴、非期待轴、过短或反向记失败，不再等后面的峰值改答案。后续大幅回位不反写。
2. 明确提示“转到位保持不动，等出现✓再回正”；项目之间静止0.7s。失败显示✗，不能当✓。
3. `--only gyro` / `--only buttons` + `--base-profile` 只测该组，继承其他组证据与设备映射；会重新测静置基线。全项/部分项证据与继承来源均保存。
4. 普通profile的 `complete` 现在指关键六键、八个摇杆方向、三轴确认且基线稳定、无重复绑定。非关键键未确认单列，不阻断主武器短测/录制；不会默认为已识别，缺少Minus/Plus就不提供组合结束。

单项命令见[中文清单](../rl/demo/开录清单.md)，可从003重测gyro；以后若再测buttons，可将新gyro profile作为base合并。

## 用户独立终端：游戏内方向短测

在项目目录执行：

```sh
.venv/bin/python -m rl.demo.capture --fixture --allow-unqualified \
  --source controller --direction-check \
  --controller-profile work/rl-demo/controller-check-003-rechecked/profile.json \
  --opponent 52 --loadout primary_only \
  --host work/rl-demo/ink-recording-host-r1/dmhost-demo \
  --modules work/rl-demo/ink-recording-host-r1/modules \
  --render-predicate async --present-link 0 --max-catchup-frames 1 \
  --ink-every 30 --warm-from work/rl-demo/async-live-full-r1 \
  --max-frames 5400 --out work/rl-demo/direction-check-001
```

用户启动后使用已有完整渲染隔离宿主、温泉峡谷单房、水刀vs.52脚本、主武器only、+5/陀螺仪。参数路径已检查存在；本轮没有实际开局验证。

窗口出现先ZR发射出生；向右水平转、保持、回正，再向左；抬头、低头，最后试侧倾是否误带水平转向。看画面是否同向。终端每0.25s打印输入yaw/pitch/roll方向、SDL原始rad/s以及原生镜头Δyaw/Δpitch（有可用原生视角时）。提示描述输入解释，不直接等同于屏幕方向；原生角度变化也保留原坐标符号。

5400受控帧约90s，不计起机/建房；`--direction-check` 不显式设上限时默认3600帧。Ctrl-C提前结束，或另一终端 `touch work/rl-demo/direction-check-001/STOP`。目录已有则同时改命令和STOP路径；不强杀进程。输入/状态照常保存在该私有目录，标 `direction_check_only`；它是诊断，非正式训练示范。

## 检查

29项组件全通过：`rl.demo.test_controller / test_demo / test_capture_loop / test_monitor`。覆盖首次出转+更大回位不覆盖、首段混轴不扫描后段凑通过、错误轴拒绝、单项继承/不重复提示、部分非关键键profile、临时假设profile普通入口拒绝/短测允许、终端方向提示与4Hz节流。静态检查和三个CLI帮助通过。

运行时性能/画面方向尚待用户这次短测，不以无硬件组件测试替代验收。本轮停下等待用户。
