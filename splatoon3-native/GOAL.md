# GOAL：Splatoon 3 原生 4v4 本地 RL 训练环境

终极目标：在 Mac (M1 Max) 上用 nxnative 思路原生运行 Splatoon 3 11.3.0，做成 4v4、全武器、全地图、全模式的本地 RL 训练环境（可复现、可加速、可多开）。

先读：`README.md`、`notes/PROGRESS.md`（当前进度与结论）、`upstream/docs/agents/`（nxnative 起机/图形/调试手册）、`../splatoon-rl-lab/notes/astri-troubleshooting.md`（模拟器路线的坑，尤其坑 5：LDN）。

## 里程碑（按顺序推进，每完成一个就 commit + push）

- **M1 画面**：修掉最终 1080p 输出黑屏与约 900 帧后主线程卡在 Presentation Thread 锁上的问题；`DM_NVN_SHOT` 截到标题/开场画面。
  线索：红字"渲染目标是压缩格式贴图…绘制落空""渲染目标都建不出 MTLTexture"、`nvnCommandBufferSetAlphaRef` 未实现、SetRenderEnableConditional 恒画；用 `DM_NVN_PASSDUMP` / `DM_NVN_TEXDUMP` 逐 pass 找哪一步变黑。
- **M2 进菜单**：用 `DM_KEYS` 脚本输入走过开场/存档创建，进入广场或大厅；能稳定跑 10 分钟不崩。
- **M3 单机可玩场景**：进训练场（试射场）或英雄模式一关，能用脚本输入移动、射击。
- **M4 RL 接口**：宿主侧加观测/动作通道（读玩家位置、墨量、HP、涂地图；写手柄输入），去掉帧率上限、可选关渲染；Python Gym 包装（`rl/` 目录）。
- **M5 本地通信（LDN）**：把 `hle_offline.c` 里失败的 `nn::ldn` 桩换成真实现：多个 dmhost 进程之间的虚拟本地网络（发现房间、加入、收发包；pia 在 main 里原生跑）。先 2 进程进同一私房。
- **M6 4v4**：8 进程私房对战，任选模式/地图/武器；整合进 Gym 多智能体环境；测吞吐（局/小时）。

## 规则

- 工作目录：`/Users/galaxy/Project/GalaxyAI/AwesomeRubish/splatoon3-native`。工具：`tools/boot.sh` `tools/run.sh` `tools/nsodis.py` `tools/nsosym.py` `tools/nsostr.py`。
- nxnative 改动做在 `upstream/` 里；每次提交前重新生成 `patches/0001-splatoon3.diff`（排除 `dm/games/0100C2500FC20000/shader_*` 与 `c1_full.tsv`，见 PROGRESS.md 里的命令写法）。`upstream/`、`work/`、`.venv/` 不入库。
- **绝不提交游戏数据**（NSO、RomFS、着色器包、截图里的游戏画面、prod.keys）。截图只放 `work/`。
- 不要删除 `work/` 下已解出的数据（重解要 10+ 分钟）。
- 每个里程碑：更新 `notes/PROGRESS.md`（做了什么、根因、怎么验证的），然后在仓库根 `git add splatoon3-native && git commit && git push origin main`。
- 着色器链需要 `DOTNET_ROOT=~/.dotnet10` 且通过 `dm/gfx/tools/nometal_run.py` 跑（没装 Xcode）。
- 不要联网对战、不碰任天堂在线服务；所有网络都是本机进程间的。
- 卡住超过合理时间就记录现象和假设到 PROGRESS.md，换下一个可推进的点。

## 卡住时找 Astra 讨论（只讨论，不实现）

实在推不动时，可以请 `gpt-6-astra` 出主意，但**只能只读讨论**（额度有限，不许它改代码或跑长任务）：

```
codex exec -m gpt-6-astra -s read-only -C "$PWD" "只做分析不做实现：<现象、日志片段、已试过的假设>。给出最可能的根因和下一步排查建议。"
```

一个问题最多问一次；Astra 的结论要自己验证、自己实现，并在 PROGRESS.md 里记一笔"问过 Astra：结论…"。
