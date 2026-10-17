# splatoon3-native

把 Splatoon 3 (11.3.0) 按 [nxnative](https://github.com/seedds/nxnative) 的思路在 Apple Silicon 上原生跑起来
（AArch64 代码直接执行 + HLE Horizon + NVN→Metal），目标是做 4v4 本地 RL 训练环境。

- `upstream/`：nxnative 克隆（gitignore），基线 commit `9579030`；本地改动见 `patches/0001-splatoon3.diff`
- `tools/survey.py`：对 XCI 本体 + 11.3.0 更新 NSP 跑 nxnative 粗查
- `notes/`：粗查报告与进度
- `work/`：解包 / 构建产物（gitignore，含游戏数据，绝不入库）
- `tests/run_all.sh`：M1 一键回归（依赖与门槛见 [tests/README.md](tests/README.md)）；当前 M1 仍未通过，卡点见 [notes/PROGRESS.md](notes/PROGRESS.md)

复现：`git clone https://github.com/seedds/nxnative upstream && (cd upstream && git checkout 9579030 && git apply ../patches/*.diff)`
