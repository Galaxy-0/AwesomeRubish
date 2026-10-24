# run71：USB Pro 引导式自检与印字映射（2026-10-24）

本轮只修手柄自检、录制端读取校准和操作说明；不启动游戏、不读取实时手柄、不训练。用户需再跑一次引导，物理映射尚未签收。T1/S1保持暂停，policies、宿主/渲染和原存档不改。

## 先复核首次原件

完整读取用户指定的会话输出，并复核 `work/rl-demo/controller-check-001/samples.jsonl`（24776次轮询）与 `summary.json`。原件保留不覆盖，SHA及逐个trigger事件见[审计JSON](rl-demo-controller-20261024.json)。

“ZR/ZL完全没读到”的初判不符合完整原件：

|通道|相对记录开始的事件到达时刻|记录值|旧六路游戏输入|
|---|---:|---|---|
|SDL axis4（lefttrigger）|24.607622s|32767、0，各一次|旧ZL曾置1|
|SDL axis5（righttrigger）|25.592380s|32767、0，各一次|旧ZR曾置1|

同一次轮询可能收到按下/松开两个事件；旧工具还以约10Hz抽样打印到终端，不能用终端片段里没出现事件代替完整JSONL。旧summary的 `button_seen` 也确为 `[true,true,true,false,true,true]`（ZR/ZL/R/RS/B/Y）。这只能证明两个扳机通道可读，不能证明其对应用户印字的左右；尤其用户回忆顺序与肩键SDL序号仍有疑点，必须由新引导确认，不自动猜测或预先交换。

本机安装SDL `SDL-release-2.32.10-0-g5d2495703`：本地 `SDL_gamecontroller.h` 和未初始化设备的枚举函数均确认共有21个按钮枚举，旧 `range(15)` 漏了misc1（Switch截图键）以及paddle/touchpad扩展。后者属于通用枚举，不表示Pro手柄实际有这些实体键。

## 本次改动

- `controller.py` 显式保存六个SDL原始轴整数、trigger4/5、完整运行时按钮枚举、raw joystick轴/按钮/hat、按下边沿；trigger按住状态与短按边沿均能进入游戏输入。原始摇杆/陀螺仪和处理后值都保留。
- 固定 `SDL_GAMECONTROLLER_USE_BUTTON_LABELS=1`。默认标准映射按Nintendo印字（A0/B1/X2/Y3）；引导按物理印字逐项学习并覆盖默认值，包括左右扳机/肩键可能的互换。不会把SDL“位置”名直接展示为用户印字结论。
- 默认0.15径向死区；引导静置3秒估计中心、中位IMU零偏和P99噪声。中心校正后仍保留至少0.15径向死区、满推达到1；另给未校中心的死区建议。不把静置漂移当移动。
- 新 `controller_check.py`：18个按键、8个摇杆方向、6个陀螺仪方向，共32项；每项开始前等松开/回中，陀螺仪另等静止。收到输入后自动推进，默认12s超时；超时明确标未确认。
- 陀螺仪按唯一IMU时间戳积分，区分yaw水平转、pitch抬头/低头、roll侧倾，要求正反同轴异号且三轴互异；静置噪声、混合轴、反向不一致不强填结论。单位rad/s，宿主输入除2π为turns/s。profile按宿主已有GUp/GRight/GRollRight的+X/+Y/+Z约定传入；实际游戏画面正负仍须开录前短测。
- 输出完整 `samples.jsonl`、逐项 `summary.json`、中文结论表 `report.md`、私有 `profile.json`。只有全项通过、静置稳定、绑定唯一且三轴闭合才标 `complete=true`。Ctrl-C保留已写的原始记录，不冒充完成。
- 录制端增加 `--controller-profile`：加载校中心/死区/印字绑定/陀螺仪轴与零偏，Minus+Plus也按校准后的印字取值。显式提供的不完整profile、SDL版本/映射变化会被拒绝；脚本录制不受影响。未提供profile保留标准按键和旧临时gyro换轴，不能当作已物理校准。

## 用户下一次只做自检

```sh
.venv/bin/python -m rl.demo.controller --out work/rl-demo/controller-check-002
```

跟终端当前提示操作，不要提前连续做完；识别后松开并回中，转动后恢复正常握姿。约2–3分钟，可加 `--timeout 20`。002存在则使用003等新目录。之后查看终端结论表或 `report.md`，把结果交回再确认；本轮不自动开游戏。

印字游戏语义：**B跳跃、ZL潜墨、ZR开火、R副武器/出钩、RS大招、Y回正**。阶段1人玩仍屏蔽R/RS。未来人玩命令加 `--controller-profile work/rl-demo/controller-check-002/profile.json`；详见[开录清单](../rl/demo/开录清单.md)。

若设备访问拒绝：系统设置→隐私与安全性→输入监控，授权启动命令的终端/App，完全退出重开。新工具仍由SDL HIDAPI完成USB握手/IMU，不另起hidapi争抢设备。

## 验证与边界

```sh
.venv/bin/python -m unittest rl.demo.test_controller rl.demo.test_demo rl.demo.test_capture_loop rl.demo.test_monitor
```

26项全部通过。新增12项无硬件组件覆盖：双trigger轴、短按后松开、印字映射覆盖、扩展按钮/raw fallback、径向死区/中心与满推、漂移建议、唯一时间戳gyro积分、正反轴冲突、真实sample路径的模拟SDL事件、profile应用、未通过profile在接触设备前被拒绝、32项完整引导及超时。静态检查、`controller --help`、`capture --help`通过；未启动SDL设备或原生游戏进行物理验收。

用户首次实测的208.18Hz为IMU事件频率，69.24Hz为最新状态更新时间；不把24776次轮询换算成传感采样率。新物理轴/正负、左右印字映射、手感与画面一致性均等用户重跑，未宣称已闭合。
