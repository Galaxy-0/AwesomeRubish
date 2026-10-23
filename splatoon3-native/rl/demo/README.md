# 人工示范录制准备（只录制，不训练）

当前为**诊断夹具**：USB Pro Controller摇杆/按键/200Hz IMU已读通；原生1v1、私有输入/状态记录和近似BC转换已实现。实时60fps、物理陀螺仪方向确认、原生全图墨色/完整武器阶段仍未通过，暂不建议开始正式录示范。`--allow-unqualified`是显式诊断入口，不会把低速运行标成实时60。最终数值见`notes/rl-demo-20261023.md`。

在项目根运行。完全离线，只用本机已有SDL2和Python环境，不下载依赖，不训练。

## 先验手柄（不启动游戏）

```sh
.venv/bin/python -m rl.demo.controller --seconds 15 --out work/rl-demo/my-controller-check
```

USB接好后，先平放3秒，再推四向摇杆、按ZR/ZL/B，分别抬头/左右转动/侧倾。实时打印`raw_sticks`、`sticks`、`buttons`、`gyro_rad_s`和传感事件时间戳。SDL负责USB0x80握手、全量报告与IMU子命令。

- SDL IMU为rad/s；宿主为turns/s，除以`2π`。现有宿主坐标约定用`SDL(x,y,z)→native(x,-z,y)`，物理方向/正负仍须人工对照画面确认；原始数值完整保留。
- 传感事件200Hz，“最新值”约66.7Hz，三子样本随一份USB报告到达，不混称轮询频率。
- 默认**不加软件死区**，保留游戏原生死区；可在自检显式加`--deadzone .15`。摇杆范围±1，陀螺仪用物理单位，独立demo传输支持±8turns/s，不再误当归一化摇杆截到±1。
- 本轮未遇权限拒绝。若提示设备不可访问：系统设置→隐私与安全性→输入监控，允许启动脚本的终端/App，完全退出重开。不要给无关程序额外权限。

## 开一局、结束、换对手

已构建夹具`work/rl-demo/host-r5/dmhost-demo`及同目录`modules/`。需要重建时，输出到**新目录**：

```sh
.venv/bin/python -m rl.demo.build_host --out work/rl-demo/host-new --peer-elision
```

只影响headless对手的A8减绘；人玩窗口完整渲染，原生720p上屏，不是几何画面。原宿主及存档不覆盖。构建依赖本机私有阶段0诊断产物，不把它们放git。

诊断录制（当前尚未达到60fps，显式确认使用未合格夹具）：

```sh
.venv/bin/python -m rl.demo.capture --fixture --allow-unqualified \
  --source controller --opponent 52 --present-link 0 \
  --out work/rl-demo/my-demo-001
```

画面出现后用ZR从出生发射，正常操作即可。水刀8000、温泉峡谷、180秒涂地，默认双方主武器only，R/RS在输入端屏蔽；灵敏度+5/陀螺仪开启，只改进程内临时设置，不改原存档。

- 正常到Winners自动保存、关闭本局进程。下一局重新运行，换一个输出目录，不复用旧文件。
- 提前结束：终端Ctrl-C，或手柄Minus+Plus；也可`touch work/rl-demo/my-demo-001/STOP`。保存部分记录并标取消，不当完整局。启动期间Ctrl-C/STOP也会取消，只收尾本次进程。
- 换T1策略：加`--opponent policy --policy arena/policies/alpha`（或bravo/其版本目录）。策略仍走公开观测与原沙箱，不读写策略目录。**T1策略的原武器是水刀8000**，此选项对手按其原武器，不能冒充.52；源码哈希随局记录。当前GPU转换仅支持水刀vs.52，对策略水刀局明确拒绝转换。
- `--loadout full`只开启原生完整按键供今后录制；GPU .52副特未实现，转换器拒绝把它标成阶段1样本。本轮没有运行全装备对局。
- `--source script`代替人输入，用于链路/性能冒烟，标`scripted_smoke`，不是人的示范。

## 数据与转换

每局留在指定的`work/rl-demo/.../`，包括：

- `usb-inputs.jsonl`：原始SDL摇杆/陀螺仪/按键与传感时间戳（脚本局为空）。
- `inputs-per-present.jsonl`、`native-barriers.jsonl`：沿用S1输入区间/ACK结构；每present一条，保留双方原始`position_sample_frame`/valid标志；状态编码器通常每4帧才有新样本，绝不伪装为逐帧新测量。
- `trace.json`：既有`inklab.trace.v1`三维回放格式；输入边沿、HP变化/倒下是观察边界，个人K无可靠归因时保持未知。
- `result.json`：完整/取消/错误、时长、双方HUD倒下、结算比分/涂地和宿主/源码身份；其`passed`只表示录制到结算链路，不表示60fps或BC真实性已通过。
- 原生日志/资源记录在`result.session`指向的本次私有目录。`telemetry`另将只读相机/弹体候选简化成JSONL，缺测为未知。

```sh
.venv/bin/python -m rl.demo.analyze work/rl-demo/my-demo-001
.venv/bin/python -m rl.demo.telemetry work/rl-demo/my-demo-001
.venv/bin/python -m rl.demo.convert --recording work/rl-demo/my-demo-001 \
  --out work/rl-demo/my-demo-001-bc --allow-approximate \
  --camera work/rl-demo/bc-lean-r4/camera-response.json
```

转换只计算/导出，不训练；M1默认CPU执行同一torch GPU环境代码，也可未来显式`--device cuda`。
输出分片`bc-*.npz`含screen/entities/mask/hud/minimap、17档移动、9档yaw/pitch、ZR/ZL切换标签及上一物理按键；量化与自由回放误差在`report.json`。相机线性响应需有对应标定，未给`--camera`时仅可用有足够激励的脚本局拟合，不能把低秩拟合当完整标定。

BC观测用当前/过去原生位置/镜头/HP/墨量锚定，墨图/弹体/内部动作阶段由GPU近似重建；另做一次初始化后不校正的自由回放报告漂移。**没有原生全图墨色真值，minimap和射线墨色尚不能作合格BC标签**；明确`ready_for_training=false`，默认不加`--allow-approximate`就拒绝导出。FOV纵55°/横85.56559°仍是已接受的假设，几何近似偏差保留。

所有数据/网格/生成页/截图/权重不提交，正式arena/T1/proficiency拒绝`DM_TEST_DEMO`及demo宿主。T1/S1保持暂停。

## 实时性诊断续查（2026-10-24）

本次逐帧证明interval一直为1、game/Metal目标一直60，30fps上屏中位数不代表被钉30Hz。持续超时主要在条件渲染CPU↔GPU等待；原生画质参数覆盖层未确认减掉实际pass，仍未达到实时60，未激活为默认。详细计时/失败原件见`notes/rl-demo-fps-20261024.md/.json`。

以下仅为脚本短测，不是人的示范，也不是Winners/等价性验收。每次用新输出目录，一次一房；GPU counter诊断有开销。

```sh
.venv/bin/python -m rl.demo.build_profile --out work/rl-demo/profile-host-new
.venv/bin/python -m rl.demo.profile_run \
  --host work/rl-demo/profile-host-new/dmhost-demo \
  --out work/rl-demo/profile-new --gpu-profile
.venv/bin/python -m rl.demo.profile_report work/rl-demo/profile-new
.venv/bin/python -m rl.demo.render_research --out work/rl-demo/render-research-new
```

`render_overlay --out work/rl-demo/overlay-new`只生成私有资源覆盖层，可用`profile_run --overlay ...`测试游戏已有颜色分级/bloom强度/默认DOF字段。它不是已确认有效的降分辨率方案，不修改原RomFS。不要将`DM_PRESENT_INTERVAL=display`或`DM_PRESENT_HZ=0`当作达到60fps的证据。
