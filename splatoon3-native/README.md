# splatoon3-native

把 Splatoon 3 (11.3.0) 按 [nxnative](https://github.com/seedds/nxnative) 的思路在 Apple Silicon 上原生跑起来
（AArch64 代码直接执行 + HLE Horizon + NVN→Metal），目标是做 4v4 本地 RL 训练环境。

- `upstream/`：nxnative 克隆（gitignore），基线 commit `9579030`；本地改动见 `patches/0001-splatoon3.diff`
- `tools/survey.py`：对 XCI 本体 + 11.3.0 更新 NSP 跑 nxnative 粗查
- `notes/`：粗查报告与进度
- `work/`：解包 / 构建产物（gitignore，含游戏数据，绝不入库）
- `tests/run_all.sh`：M1 至 M6 回归与分级验收（依赖与门槛见 [tests/README.md](tests/README.md)）；M1–M5 和 M6-B 双端帧锁存 / 位置 / 墨量已通过，当前进度见 [notes/PROGRESS.md](notes/PROGRESS.md)
- `rl/`：PettingZoo ParallelEnv，本机 Unix socket、固定 present 帧跳、headless 128×72 RGB；模式 / 地图 / 武器和分队复用 M5 路线。朝向等其余内部字段和八端随机策略签收仍待完成。
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
**M6-B 双端已 PASS**：按 present 精确推进、同帧 HID 动作锁存、逐 agent 结算、位置 / 墨量正式观测，以及 reset 重建第二局后继续 step 均通过。
首局随机策略 447 步到双方 Winners，第二局 10 步；正式入口退出 0。共享单调时钟统一扣除策略等待时间，解决各端分别暂停导致的计时分离。像素来自 headless 内部 720p 渲染目标。
朝向已接入并通过双端动作对照；HP / 存活、特殊量、比分 / 涂地比例、剩余时间和可见队友 / 敌人状态尚未全部接入，八端随机策略和完整 M6 尚未签收；reward 示例对尚不可用的计数返回 0。运行方式见 [rl/README.md](rl/README.md)。
