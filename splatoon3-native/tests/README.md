# 回归测试

M1 的一键入口：

```sh
uv pip install --python .venv/bin/python -r tests/requirements.txt
bash tests/run_all.sh
```

需要当前 Apple Silicon / Metal 4 环境、`upstream/` 补丁以及已提取并改写的 `work/data/v720896/`、`work/build/patched_v720896/`、MSL 缓存和字体。测试不下载游戏数据，也不连接任天堂服务。

入口先构建宿主，执行无游戏素材的条件渲染 / 命令复制 GPU 检查和 NVN 检查，再启动真实游戏 75 秒。运行使用独立的新存档目录；每次的日志、600/1200/2400 帧截图和 `result.json` 保存在 `work/tests/m1-<timestamp>/`。

M1 同时要求：宿主持续运行到测试时限、最终帧数至少 2400、末尾采样窗口内帧数增长、无 CRASH/FATAL/看门狗及 GPU 执行错误、SIGTERM 优雅退出完成，以及三个 1920×1080 截图平均 RGB 方差 ≥25、非黑像素比例 ≥5%。任何一项失败都会返回非零。方差检查只证明输出不是全黑，不代表图形已经完全正确。

可用 `bash tests/run_all.sh --seconds 120` 延长检查。初次编译 MSL 的机器可能需要更长时间。默认入口仍只验收 M1，不能当作全部目标已完成的证明。

M1 当前基线：116 项条件渲染 / 复制 / 资源退休 GPU 检查、79 项 NVN 检查、73 项 HID、10 项本地前端检查及 75 秒游戏运行全部通过。NVN 检查包含 END 在内存段末尾应直接终止，不能因多余的 JUMP 余量覆盖相邻缓存 BEGIN 的回归。

可选排障开关 `DM_NVN_CMDWATCH=<起始帧>` 会登记可达命令段、来源块并检查 hash / 写保护；`DM_NVN_CMDWATCH_HASH=1` 只比较 hash。
它不属于正常验收配置。`DM_NVN_CMDWATCH_JUMP_TRAP=1` 用于在录制阶段对“JUMP payload 写入已登记 BEGIN”的 store 设保护，命中后故意进入崩溃报告；正常验收不要设置。

## M2 验收入口（已通过）

```sh
bash tests/run_all.sh --milestone m2
```

该入口要求完整的 `tools/routes/m2-local-lobby.keys` 和人工确认目的地为本地通信入口的
`work/m2/reference-local-lobby.png`。也可以用 `--route` / `--reference` 指定本地路径。
参考图只放 `work/`，绝不入库；不得从待验收的同一次运行自动生成参考图。
当前路线在 300 帧开始、通过 X 地图的 The Shoal 进入本地大厅，在 1500 帧打开 Match Menu；
默认验收截图为 2400 帧，画面必须是选中 Private Battle 的菜单。

起点改为 `work/save_ref/save.dat`：它是指定模拟器存档的只读副本，大小 188,719 字节，
SHA256 为 `89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd`。
首次准备时仅从 `../splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat`
复制到该位置，并将副本设为只读；原件不修改，存档不入库。
测试检查参考档 hash，每次复制到独立 `work/tests/m2-<timestamp>/save/` 后才设为 `DM_SAVE`；
运行结束再次检查参考档未变。可用 `--save-ref` 指定另一个含相同 `save.dat` 的目录。
测试会清除继承的 `DM_*` 开关，再设置验收需要的环境，避免 FIFO 或诊断配置干扰。

门槛：独立的参考存档副本启动，DM_KEYS 脚本执行，在指定帧截取 1920×1080 画面；按 320×180 缩图的
局部亮度 SSIM ≥0.90、RGB 平均绝对误差 ≤0.06 与参考图比较。截图成功且相似度达标后，
再持续运行至少 600 秒，要求帧数继续增长、无 M1 的运行时失败标记、SIGTERM 优雅退出。
日志、存档 / 路线 / 参考图 SHA256、采样、比较结果写入 `work/tests/m2-<timestamp>/result.json`。
默认到达超时 1200 秒，可用 `--arrival-timeout` 调整；`--soak-seconds` 不能低于 600。

历史的广场补段耗尽已修复。当前已有完整路线和独立探索时人工确认的 Private Battle 菜单参考图，
已通过到达后十分钟验收，证据和完整结果见 `notes/PROGRESS.md`。旧教学路线已放弃，不得用其前缀替代验收。

M2 显式启用 `DM_LDN_FRONTEND=1`（仅 main 构建 `28c4287aee36f7499da60f3e68b54c70`）：
提供进程内空闲初始化状态和 NX 协议配置，使游戏能显示本地私房入口；默认仍离线。
建房、扫描、加入、收发均未实现；本测试不按下 Private Battle 的确认键，不证明 M3 互通。
没有联网到外部或连接任天堂服务。

M1 可用相同框架做存档场景对照（仍创建独立副本）：

```sh
bash tests/run_all.sh --save-ref work/save_ref --seconds 180
```

无 `--save-ref` 时仍从空存档开始。单元检查新增大量短缓存列表的补段上限、有效回调给块、
大记录容量及无外层 autorelease pool 时退休真实 GPU 缓冲的检查；LDN 前端检查同时证明未知构建和连接操作仍失败。

HID 单元检查已从 22 项扩展到 73 项，覆盖 16 个六轴历史样本、有效加速度、按时钟推进的采样号、
连续读取不重复推进，以及原有姿态 / 右摇杆 / ZR 行为。HID 单元检查通过不表示 M2 通过。

## M2.5（调整后：武器全解锁与多身份）

```sh
bash tests/run_all.sh --milestone m25
```

按 GOAL.md 的 2026-10-18 调整，这是完整 M2.5 验收。会从参考档创建三个独立副本：关闭解锁的对照、
`DM_PLAYER=0` 和 `DM_PLAYER=1` 两个启用解锁的真实宿主进程。
按本地游戏 BYML 表的 `Type=Versus` 动态生成预期 ID 集合（包含全部副 / 特殊组合），
从实际武器 UI 的列表插入与完成计数探针读取 ID 集合，要求每次列表重建均完全一致。
再用手柄脚本选中末页武器，关闭并重开界面，检查内部装备 ID 属于原档缺少的武器；
两进程必须实际调用账号读取接口，得到不同 UID 和 `RL-0` / `RL-1` 昵称。
原档与只读参考档运行前后均核对 hash。截图、日志、运行副本和完整结果只写入 `work/tests/m25-*`。
依赖本地 `zstd`，不会下载武器表或提交游戏数据。

`DM_FULL_UNLOCK=1` 当前**仅实现武器拥有判定及武器 UI 内联判定**，是显式启用的运行时开关。
仅支持已验证的 11.3.0 main 构建，并逐项校验原指令；默认关闭，未知构建或指令不符立即停止。
不改写存档拥有表，不包含单人 / 打工 / NPC 专用武器。游戏本身的自动保存只发生在运行副本内。

`DM_PLAYER=0..7` 为每进程单一本地账号配置不同 UID 和固定 `RL-N` 昵称；
未设置时保留原 UID / `DM_NICK` 行为。21 个独立进程单元用例覆盖全部 8 个身份、默认值、
非法参数、构建门控、指令签名门控及原生执行的武器类型筛选。

地图 / 模式解锁与私房设置验证已移到 M4，不参与 M2.5 结果判定。
结果仍记录 `stages_modes.status: deferred_to_m4`，`passed` 要求武器和身份检查均通过。
`--weapons-only` 保留为兼容别名，执行相同范围。M2.5 通过不证明 M3 建房、扫描或双进程互通。
