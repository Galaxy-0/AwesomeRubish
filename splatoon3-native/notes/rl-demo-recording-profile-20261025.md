# run74：Stage1正式控制profile与无手柄dry-run

用户已目视确认direction-check-002方向“正常”。基于该反馈、002的4505帧及实际USB矩阵记录、audit-r2、原003关键键/八个摇杆方向证据，生成：

`work/rl-demo/recording-profile-r1/profile.json`

- scope=`primary_only_recording`，complete=true；不是把原短测profile原地改成通过。
- ZR/ZL/B必须有valid且与binding一致的原始引导证据，八个摇杆方向全部有效，已验收的游戏内方向矩阵必须与注入矩阵相等。
- Minus/Plus/Up仍未确认，不回填映射；R/RS原有确认保留，但Stage1实际输出屏蔽。原始物理R/RS仍可记入USB原件，不会作为游戏动作发送。
- gyro的valid表示Stage1端到端路径被用户接受；保留之前孤立物理轴是否确认及旧basis，不伪造roll单轴新实测。
- 002被中断、未到Winners及原始退出错误都保留；方向签收不是整局通过。complete不代表ready_for_training。
- full不能使用此primary-only scope；对应full profile仍必须确认R/RS，不能靠binding存在或complete=true绕过。

发行工具（输出已存在时换新out）：

```sh
.venv/bin/python -m rl.demo.recording_profile \
  --base work/rl-demo/direction-check-001-audit-r2/profile.json \
  --direction-check work/rl-demo/direction-check-002 --feedback 正常 \
  --out work/rl-demo/recording-profile-r1
```

原件SHA和发行依据保存在该目录report.json/profile.json；不提交work数据。原audit-r2、002、失败my-demo-001均未改动。

capture增加显式 `--dry-run`：保留fixture、隔离宿主/参数和profile校验，随后返回，不构造Controller/SDL或DemoEnv。真实CLI已用原宿主/async/30f墨图/缓存参数通过，结果：`work/rl-demo/recording-profile-r1/dry-run/result.json`，passed=true、controller_opened=false、game_processes_started=false。

36项组件与静态检查通过，包括必需键缺失/未确认/禁用拒绝、摇杆缺项拒绝、方向矩阵未签收拒绝、Stage1不要求R/RS而full仍要求、未确认键保留、中断记录诚实继承、dry-run不构造SDL/手柄/游戏、原始R/RS可见但Stage1输出为0。

完整录制命令见[中文开录清单顶部](../rl/demo/开录清单.md)。录制设置只换profile；因失败my-demo-001已存在且需保留，输出顺延my-demo-002。无短测上限，正常180秒到Winners，Ctrl-C/STOP提前结束；保留原--allow-unqualified（其余BC/完整数据资格仍未全部闭合）。T1/S1、训练暂停，未开启实机房间/占用手柄，原存档/宿主/policies不改。
