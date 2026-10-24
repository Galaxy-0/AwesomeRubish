# run73：方向短测001的pitch反向与yaw错轴（2026-10-24）

结论：**pitch取反；手柄yaw改送原生Z，不送Y。增益不加倍、不额外乘2π。** 上轮把宿主键盘测试键名当作Splatoon实际消费轴，是映射错误。本轮只离线分析、修profile和Python传输/提示；没有启动SDL设备或游戏。T1/S1暂停，policies、原存档、宿主二进制及冻结构建输入均未修改。

## 原件、帧时钟和筛选

来源 `work/rl-demo/direction-check-001/`：5400帧USB输入、5400条实际注入、5401个barrier。受控墙钟93.774秒，57.585 present/s。会话 `work/tests/m6-2p-20261024-101950-890143/`。

使用原生host.log里5400条带游戏frame的 `D3R_STATE` 对齐镜头；ACK的own_view有重复缓存，不能当每条都新采样。俯仰角速度用eye→at视线的真实仰角差，**不用相机+0x16c控制字段直接冒充弧度**。该控制字段与仰角相关0.999659，但有约−0.132rad截距、全范围线性斜率1.179，二者不完全相同。终端也将其改标 `Δpitch_ctl`，不再给控制字段套角度符号。

固定16帧不重叠窗口，从第300帧起；排除非存活/发射、实际右摇杆输入>0.01、Y回正附近、俯仰上限、混轴（主轴RMS不足其他轴3倍）和快速转回（平均值不足RMS的85%）。主轴RMS需>0.3rad/s。yaw另限制接近水平，pitch排除控制字段绝对值>0.85。扫0/2/4/6/8f因果滞后，不把自由动作拟合成某个精确输入延迟。

以下为 **镜头实际角速度 / 手柄实际角速度** 的窗口绝对值中位数。逻辑时间按fixed60；墙钟时间由USB时间戳独立计算。

|因果滞后|yaw窗口数|yaw逻辑增益|yaw墙钟增益|pitch窗口数|pitch逻辑增益|pitch墙钟增益|
|---:|---:|---:|---:|---:|---:|---:|
|0f|16|0.346|0.342|3|2.532|2.479|
|2f|14|0.344|0.337|3|2.511|2.460|
|4f|14|0.322|0.317|3|2.409|2.331|
|6f|14|0.314|0.308|3|2.285|2.236|
|8f|14|0.307|0.301|3|2.156|2.036|

不是互相独立的5组实验；只是同一记录的对齐敏感性检查。pitch样本仅3窗，但所有滞后下均为**负相关方向**：SDL x正→注入X正→实际视线仰角下降。结合003已确认“抬头=x正”和用户反馈，翻转原生X有直接依据。

yaw当前绝对增益约0.30–0.35（反过来手柄/镜头约2.9–3.3），且方向不可靠；错误Y轴与少量roll/累计姿态投影混入，不能把该数当作正确yaw路径的线性增益，也不该据此乘一个补偿倍数。

## 排除单位、设置与软件死区

- 减零偏后的SDL峰值x/y/z为4.058 / **7.903** / 1.145 rad/s；实际HID峰值X/Y/Z为0.646 / **1.258** / 0.182 turns/s。转手柄时输入不小，主要被送到错误Y槽。
- 逐帧原始→日志gyro与日志→实际actions的最大误差均0；rad/s→turns/s只除一次2π；没有额外除60。没有到达±8turns/s的宿主裁剪。
- 0.15死区只作用摇杆；引导的0.35rad/s阈值只用于自检判定，录制gyro没有这个死区。录制只减静置零偏，没有Python侧平滑/衰减。宿主保留200Hz六轴历史，不能把新旧轴错误解释为滤波吃信号。
- 001日志：frame987，临时控制选项从digital8/8改为 **20/20、gyro_on=1**。0..20范围最高档对应+5，保留原生 `(digital−10)/10` 归一化；此前阶段0独立读回为1/1。本局记录了写入最高档/开启，未额外添加持续读回探针，不宣称本局逐帧回读了选项。
- 全局57.585fps和个别长帧会影响墙钟手感，但干净窗口的墙钟/逻辑比值相近，不能解释约7倍的yaw路径差异。未用额外增益掩盖这类调度影响。

## 原生轴与单位核对

`nn::hid::SixAxisSensorState` 对应的公开[libnx结构](https://switchbrew.github.io/libnx/structHidSixAxisSensorState.html)将angular_velocity、angle与direction分别保存；向量轴是设备坐标，不能把SDL的“yaw=y”直接套成游戏镜头消费原生Y。libnx页面本身没有给出完整单位/握姿定义，不能将它当任天堂私有SDK的完整轴说明。

单位旁证：[SDL输入源码](https://raw.githubusercontent.com/nintendoswitchemulators/ryujinx/master/src/Ryujinx.Input.SDL2/SDL2Gamepad.cs)把rad/s转deg/s；[公开模拟器历史实现](https://www.git.axenov.dev/Museum/ryujinx/src/commit/d987cacfb720f2f4bc18958fc26ac0893903c090/Ryujinx.Input/HLE/NpadController.cs)再将deg/s及累计角乘约1/360送HID。这里只用于交叉核对转数单位，不复制它的0.0027近似系数。本宿主明确使用精确turns/s与turns，构造direction时再乘2π；保持这个接口。

更直接的本构建证据来自已保存的**独立单轴原生校准**：`work/rl-demo/run70/bc-periodic-full-r1/camera-response.json`，源 `native-survey-full-r2`。其宿主与001宿主使用相同 `hle_hid.c` SHA（见JSON），没有拿另一套HID单位混用。

|注入单轴1turn/s|原生yaw增量（rad/游戏帧）|pitch控制量增量/帧|
|---|---:|---:|
|X|0|−0.252248|
|Y|0|0|
|Z|+0.250627|0|

这是原校准的稳态中位系数，零表示该受控样本中的响应，不等于所有姿态下数学恒零。yaw换算实际角速度增益为 `0.250627 × 60 / (2π) = 2.3933`。pitch控制系数不能冒充实际仰角；其方向另由001真实eye→at仰角确认。

宿主的初始参考重力沿−Z，旋转矩阵按设备XYZ构造；这也与Z作为该参考姿态水平旋转轴相容。键盘里 `GRight` 写Y只是旧测试名称，不是游戏/SDK消费方向的证明。没有修改宿主或游戏内部机制来绕过轴问题。

正确轴预计在+5档产生约2.39的yaw角速度比，大于用户描述的基础1:1，符合“+5更快”的定性预期。**这是同宿主单轴数据的预测，非Switch实机+5的独立数值标定；002尚未实测。** 大幅倾斜/累计姿态的投影仍待后续确认，不为消除残差新增混轴增益。

## 修正与复测

物理识别 `gyro_mapping` 保留SDL pitch=x+、yaw右转=y−、roll右倾=z−的原证据/假设，不篡改“抬头=x+”的事实。新增独立 `gyro_native_matrix`：

```text
HID [X,Y,Z] turns/s = [-SDLx, +SDLz, +SDLy] / (2π)
```

均先减003静置零偏；无额外增益。这是det=+1的正交旋转，不是任意缩放或反射。profile验证会拒绝非正交增益矩阵。USB记录同时保存物理方向量和实际HID XYZ，终端从物理量解释“右/抬头”，另列HID XYZ，避免换轴后提示再误导。

新profile：`work/rl-demo/direction-check-001-audit-r2/profile.json`，仍为 `complete=false / scope=direction_check_only`；原001及原profile均保留不改。中间audit-r1也保留，最终报告以r2的真实视线仰角为准。脚本可复现：

```sh
.venv/bin/python -m rl.demo.gyro_audit --source work/rl-demo/direction-check-001 \
  --out work/rl-demo/direction-check-001-audit-r2
```

输出已存在时必须换新目录。完整窗口/原件SHA在该目录audit.json，[提交的JSON](rl-demo-gyro-20261024.json)只含汇总，不提交录像/派生profile。

给用户的002命令见[开录清单顶部](../rl/demo/开录清单.md)：相同完整渲染宿主，1房脚本对手，主武器only，最大5400受控帧。Minus/Plus仍未确认，Ctrl-C或STOP结束。32项组件和静态检查通过，未以组件测试代替002物理方向/手感验证。到此停下等用户复测。
