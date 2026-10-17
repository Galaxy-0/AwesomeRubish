# GOAL：Splatoon 3 原生 4v4 本地 RL 训练环境

终极目标：在 Mac (M1 Max) 上用 nxnative 思路原生运行 Splatoon 3 11.3.0，做成 4v4、全武器、全地图、全模式的本地 RL 训练环境（可复现、可加速、可多开）。

先读：`README.md`、`notes/PROGRESS.md`（当前进度与结论）、`upstream/docs/agents/`（nxnative 起机/图形/调试手册）、`../splatoon-rl-lab/notes/astri-troubleshooting.md`（模拟器路线的坑，尤其坑 5：LDN）。

## 已对齐的方向（2026-10-17）

- **只做 4v4**：不做单人/训练场退路，精力押在本地通信（LDN）多开。
- **观测两者都要**：训练用游戏内部状态，画面（像素）可随时打开用于评估/录像。
- **速度暂不追求**：先打通，吞吐以后再说。
- **验收要自动化测试**：每个里程碑都要有可一键运行的回归测试（`tests/`，`tests/run_all.sh`），通过才算完成。

## 里程碑（按顺序；每个完成 = 测试通过 + PROGRESS.md 更新 + commit + push）

- **M1 画面**：最终 1080p 输出不再黑屏，约 900 帧后的锁死修掉。
  测试：启动 N 秒，`DM_NVN_SHOT` 截图非全黑（像素方差阈值），日志无 CRASH/FATAL，帧计数持续增长。
- **M2 进到本地通信入口**：不走开场教学。用模拟器路线已经打过教学的存档（`../splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat`，复制到 `work/save_ref/`，绝不改原件、不入库）作为起点，`DM_KEYS` 脚本从读档走到大厅里"本地通信 / 私房"的入口。
  测试：每次用 save_ref 的新副本启动，脚本跑完后在预期帧截图，与参考图像相似度达标；连续跑 10 分钟不崩。
- **M2.5 全解锁 + 多身份**：存档原样不动，由宿主在运行时让游戏认为全部武器（含副/特殊组合）、地图、模式都已拥有/解锁——在游戏判断拥有/解锁的函数处返回"有"（用 `../splatoon3-decomp/symbols/` 的类名/参数表定位，按 main 构建号门控）。
  宿主按进程给出不同的账号身份（`DM_PLAYER=<0..7>` → 不同 Uid 与昵称），8 个实例共用同一份存档的副本。
  测试：自动脚本进入武器选择/私房设置界面，检查可选武器数与全武器数一致（截图或读内存）；两个不同 DM_PLAYER 的进程报出不同 Uid/昵称。
- **M3 LDN 两进程互通**：`nn::ldn` 换成真实现（进程间虚拟本地网络：建房、扫描、加入、收发包；pia 在 main 里原生跑）。
  测试：两个 dmhost 进程，一个建房一个扫到并加入；日志/内存状态确认双方同房。
- **M4 1v1 私房开局**：两进程在私房里开一局并打完（任意模式/地图）。
  测试：自动化脚本跑完整一局，双方都到结算画面。
- **M5 4v4**：8 进程私房对战，可指定模式、地图、每人武器。
  测试：自动跑一局 4v4 到结算；内存/CPU 占用记录在 PROGRESS.md。
- **M6 RL 接口**：宿主侧观测（内部状态：位置、朝向、HP、墨量、特殊、涂地图、比分、时间；可选像素帧）和动作（手柄输入）通道；Python 多智能体 Gym 包装（`rl/`），8 个 agent 同步 step。
  测试：随机策略跑完一局，观测数值合理、动作生效、reset 可重复。

## 规则

- 工作目录：`/Users/galaxy/Project/GalaxyAI/AwesomeRubish/splatoon3-native`。工具：`tools/boot.sh` `tools/run.sh` `tools/nsodis.py` `tools/nsosym.py` `tools/nsostr.py`。
- nxnative 改动做在 `upstream/` 里；每次提交前重新生成 `patches/0001-splatoon3.diff`（排除 `dm/games/0100C2500FC20000/shader_*` 与 `c1_full.tsv`，见 PROGRESS.md 里的命令写法）。`upstream/`、`work/`、`.venv/` 不入库。
- **绝不提交游戏数据**（NSO、RomFS、着色器包、截图里的游戏画面、prod.keys）。截图只放 `work/`。
- 不要删除 `work/` 下已解出的数据（重解要 10+ 分钟）。
- 每个里程碑：更新 `notes/PROGRESS.md`（做了什么、根因、怎么验证的），然后在仓库根 `git add splatoon3-native && git commit && git push origin main`。
- 着色器链需要 `DOTNET_ROOT=~/.dotnet10` 且通过 `dm/gfx/tools/nometal_run.py` 跑（没装 Xcode）。
- 不要联网对战、不碰任天堂在线服务；所有网络都是本机进程间的。
- 卡住超过合理时间就记录现象和假设到 PROGRESS.md，换下一个可推进的点。

## 分工

- 里程碑由 Claude 制定和调整（本文件），Claude 定时检查进度并给出下一步指示。
- Codex（gpt-6.1-sol）负责实现。卡住时把现象、日志、已试假设写进 PROGRESS.md 的"卡点"一节然后停下，等指示；不要自己去问别的模型。
