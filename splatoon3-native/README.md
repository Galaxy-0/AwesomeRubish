# splatoon3-native

把 Splatoon 3 (11.3.0) 按 [nxnative](https://github.com/seedds/nxnative) 的思路在 Apple Silicon 上原生跑起来
（AArch64 代码直接执行 + HLE Horizon + NVN→Metal），目标是做 4v4 本地 RL 训练环境。

- `upstream/`：nxnative 克隆（gitignore），基线 commit `9579030`；本地改动见 `patches/0001-splatoon3.diff`
- `tools/survey.py`：对 XCI 本体 + 11.3.0 更新 NSP 跑 nxnative 粗查
- `notes/`：粗查报告与进度
- `work/`：解包 / 构建产物（gitignore，含游戏数据，绝不入库）
- `tests/run_all.sh`：M1 / M2 回归与 M2.5 验收（依赖与门槛见 [tests/README.md](tests/README.md)）；M1、M2、调整后的 M2.5 已通过，当前进度见 [notes/PROGRESS.md](notes/PROGRESS.md)
- `tools/routes/`：M2 使用已过教学的存档副本，脚本走到 The Shoal 的 Private Battle 菜单，入口后连续十分钟验收通过；旧教学路线仅保留历史记录。
- `work/save_ref/save.dat`：指定模拟器存档的只读副本，不入库。M2 测试每次复制到独立运行目录，绝不把参考档或原件作为 `DM_SAVE`。

复现：`git clone https://github.com/seedds/nxnative upstream && (cd upstream && git checkout 9579030 && git apply ../patches/*.diff)`

M2.5 已按 2026-10-18 调整后的口径通过验收武器全解锁（174 件 Versus 套装）与 `DM_PLAYER=0..7` 多身份。
地图 / 模式解锁及私房设置验证移到 M4；M3 负责先打通本机两进程 LDN。
详见 [进度与卡点](notes/PROGRESS.md) 和 [验收说明](tests/README.md)。
