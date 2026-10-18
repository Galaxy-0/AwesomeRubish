# splatoon3-native

把 Splatoon 3 (11.3.0) 按 [nxnative](https://github.com/seedds/nxnative) 的思路在 Apple Silicon 上原生跑起来
（AArch64 代码直接执行 + HLE Horizon + NVN→Metal），目标是做 4v4 本地 RL 训练环境。

- `upstream/`：nxnative 克隆（gitignore），基线 commit `9579030`；本地改动见 `patches/0001-splatoon3.diff`
- `tools/survey.py`：对 XCI 本体 + 11.3.0 更新 NSP 跑 nxnative 粗查
- `notes/`：粗查报告与进度
- `work/`：解包 / 构建产物（gitignore，含游戏数据，绝不入库）
- `tests/run_all.sh`：M1 至 M6 回归与分级验收（依赖与门槛见 [tests/README.md](tests/README.md)）；M1–M6 已通过（双端字段 / reset + 八端随机策略到结算），当前进度见 [notes/PROGRESS.md](notes/PROGRESS.md)
- `rl/`：PettingZoo ParallelEnv，本机 Unix socket、固定 present 帧跳、headless 128×72 RGB；模式 / 地图 / 武器和分队复用 M5 路线。已接入朝向、HP、特殊量、时间及公共HUD/结算字段；八端随机策略整局已通过。
- `tools/ldn/`：M3 本机虚拟 LDN 空气服务及运行说明；双真实游戏建房 / 扫描 / 加入 / 双向收包验收已通过。
- `tools/routes/`：M2 使用已过教学的存档副本，脚本走到 The Shoal 的 Private Battle 菜单，入口后连续十分钟验收通过；旧教学路线仅保留历史记录。
- `work/save_ref/save.dat`：指定模拟器存档的只读副本，不入库。M2 测试每次复制到独立运行目录，绝不把参考档或原件作为 `DM_SAVE`。

复现：`git clone https://github.com/seedds/nxnative upstream && (cd upstream && git checkout 9579030 && git apply ../patches/*.diff)`

M2.5 已按 2026-10-18 调整后的口径通过验收武器全解锁（174 件 Versus 套装）与 `DM_PLAYER=0..7` 多身份。
M3 已打通本机两进程 LDN；M4 已通过 25 张普通私房地图、全部五模式与全自动 1v1 到双方结算的验收。
**M5 已 PASS**：八端独立身份 / 指定武器，Turf War / Scorch Gorge 的离线 4v4 自然结算；八端优雅退出 0。
headless / 720p、代码与文件 mmap、GPU binary archive 共享、上传暂存 / 退役 private 内存回收和两端一批开局均已实测。
八端 footprint 合计峰值 28.38 GiB，单端全程峰值均 <6 GiB，对战共同窗口约 13.4–14.0 fps / 端；最高采样压力 warning，新增 swapout 0。
阶段提交 `81a2edf`，完整八端验收提交 `2006a98`。
**M6 已 PASS**：present 精确帧跳、同帧HID动作锁存、逐agent终止、headless内部720p→128×72 RGB，以及位置 / 朝向 / HP / 独立存活 / 墨量 / 特殊量 / 时间 / 结算比分与涂地比例正式观测均已接入。各端公共HUD提供队友 / 敌人存活及特殊就绪信息，公开分队 / 武器按原生槽位关联。
双端字段整局 + reset 436步通过，四宿主优雅退出；八端随机策略正式入口186步到全部Winners，八宿主优雅退出，footprint合计峰值28.05 GiB、pressure normal、无新增swapout。共享单调时钟统一扣除策略等待，不宣称固定物理dt或确定性。
当前实机字段签收范围为Turf War / Scorch Gorge；其它模式的比分和加时仍需各自实机覆盖。比分 / 涂地比例来自结算HUD，局内没有实时涂地图；reward示例采用充能增量与敌队HUD倒下事件塑形（包含环境死亡），没有个人最后一击计数。运行与各字段有效位见 [rl/README.md](rl/README.md)。
