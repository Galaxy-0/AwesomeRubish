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
该前端本身不提供建房、扫描、加入、收发；M3 的 `DM_LDN_AIR` 另行显式启用。
M2 测试不按下 Private Battle 的确认键，不证明 M3 互通。
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

`DM_FULL_UNLOCK=1` 是显式启用的运行时开关，覆盖武器拥有判定、武器 UI 内联判定，以及 M4 私房两个地图列表的赛季过滤。
仅支持已验证的 11.3.0 main 构建，并逐项校验原指令；默认关闭，未知构建或指令不符立即停止。
不改写存档拥有表，不包含单人 / 打工 / NPC 专用武器。游戏本身的自动保存只发生在运行副本内。

`DM_PLAYER=0..7` 为每进程单一本地账号配置不同 UID 和固定 `RL-N` 昵称；
未设置时保留原 UID / `DM_NICK` 行为。21 个独立进程单元用例覆盖全部 8 个身份、默认值、
非法参数、构建门控、指令签名门控及原生执行的武器类型筛选。

地图 / 模式解锁与私房设置验证已移到 M4，不参与 M2.5 结果判定。
结果仍记录 `stages_modes.status: deferred_to_m4`，`passed` 要求武器和身份检查均通过。
`--weapons-only` 保留为兼容别名，执行相同范围。M2.5 通过不证明 M3 建房、扫描或双进程互通。

## M3（已通过）

```sh
bash tests/run_all.sh --milestone m3
```

入口先跑通用组件与无游戏的 `tests/test_ldn_air.py`，再跑两个真实 dmhost。
无游戏测试用两个 C 进程直接调用宿主同一份 HLE；覆盖会话 / 信标一致性、扫描过滤、接纳策略、
状态事件、IPv4 字节序、变更历史、双向数据、EventFd、离房与房主退出、Finalize / 事件复用。
单跑这项可用 `.venv/bin/python tests/test_ldn_air.py`（先按 tools/ldn/README.md 构建测试客户端）。

真实验收创建独立 Unix socket 空气服务和每进程独立的参考档副本。A 在 Private Battle 的房间列表按 Y，
再按 A 确认；只有服务收到 A 的实际 CreateNetwork 后才启动 B。B 在房间列表选择，再在 Join this room 对话框确认加入。
要求完整会话 ID 有服务端建房 / 扫描 / 加入证据，两个宿主最新状态分别是 AP-created / Station-connected，
双方均看到两节点同房，两个游戏各实际取出至少一个对方数据帧，保持同房至少十秒后正常退出。
组件通过与真实游戏通过分别记录；真实阶段未通过时，完整 M3 必须返回非零。

默认超时 360 秒，可用 `--timeout` 延长。`--a-route` / `--b-route` 为诊断时的附加 DM_KEYS；
默认路线已由无补按的真实双进程验收证明。截图、日志、路由、结果仅放 `work/tests/m3-*`。
服务设计与独立使用见 [tools/ldn/README.md](../tools/ldn/README.md)。只使用 Unix domain socket，
虚拟 UDP 描述符不会交给 OS IP 网络；外部地址拒绝，DNS / SSL / 在线服务保持离线。

当前基线：59 项无游戏通信检查通过，两个真实游戏同房稳定 10.164 秒、各实际接收至少 128 帧，
两个宿主均优雅退出 0；最终证据为 `work/tests/m3-20261018-025742-268957/`。
此结果只覆盖 M3，开局 / 结算和地图 / 模式解锁留待 M4。


## M4（已通过：地图 / 模式与完整 1v1 验收）

```sh
bash tests/run_all.sh --milestone m4 --timeout 1200
```

先运行与 M3 相同的组件检查，再从两个独立参考档副本启动真实游戏。
A 建房后才启动 B；固定 DM_KEYS 输入轮选五种模式、打开并翻页地图面板，选 Scorch Gorge，
把 RL-0 设为 Alpha、RL-1 设为 Bravo，进入准备并由双方确认开始。对战期间不再输入。
所有操作通过手柄接口；没有直接改写队伍、倒计时、结果或房间状态。

11.3.0 的本地 VersusSceneInfo 表有 26 行，25 行 IsDisplayInStageList=true；隐藏的 Manbou 行不进入目录。
测试从本地 BYML 动态生成预期集合，要求房间地图列表与实际选择面板的插入 ID 集合 / 完成计数都严格相等。
DM_FULL_UNLOCK 仅绕过这两个原生列表的已解锁赛季上限，仍保留隐藏标记；五种模式原本就全部可选。
开关、构建号、全部原指令校验沿用 M2.5 的门控，关闭时保持原生判断，不修改参考档。
原生执行单元检查覆盖两处显示标记 / 赛季过滤在关闭与开启时的结果。

对局门槛要求双方原生 InGame、ResultJudge、ResultWinners 序列实际进入，完整对局至少持续 178 秒墙钟时间，
并在双方截图中识别到 Victory / Defeat。五种模式也从实际设置截图识别。
文字识别使用本机 macOS Vision（tools/vision-ocr.swift，依赖 Command Line Tools 的 swiftc），图片不上传。
任一目录缺项、模式缺项、未到结算、运行错误、非优雅退出、原档 / 参考档 hash 改变都会失败。

产物在 work/tests/m4-*，含每端输入、截图、日志、实际地图集合、阶段时间和 OCR 结果；不入库。
空气服务每五秒记录双方收发数据报 / 字节数、当前排队、队列峰值、丢包数，供加载或对战停滞时对照。
默认时钟沿用同机单调时钟，不启用独立的 DM_DETCLOCK。当前状态以 notes/PROGRESS.md 末尾为准。


最终证据：`work/tests/m4-20261018-031759-249564/result.json` 为 `passed: true`、`errors: []`。
两个地图集合 / 计数均为 25，五模式截图全部识别；双端 InGame 到 ResultJudge 约 186 秒，
双方 ResultWinners 与 Victory / Defeat 截图均确认，两个宿主优雅退出 0。
同会话最后五秒采样分别发送 / 对端收到 4247、4298 个数据报，队列峰值 2、丢包 0。
这不表示所有 25 张地图 / 五模式都已各跑一局，也不表示 M5 4v4 或完整图形效果已验收。

## M5 资源准入与 4v4

先测单进程，再逐级准入。所有阶段都使用独立参考档副本，网络仅为本次 Unix domain socket 空气服务。

```sh
bash tests/run_all.sh --milestone m5 --players 1 --timeout 400
bash tests/run_all.sh --milestone m5 --players 2 --weapons 8001,2040 --timeout 1200
bash tests/run_all.sh --milestone m5 --players 4 --admission-only --weapons 8001,2040,10,3000 --timeout 1400
bash tests/run_all.sh --milestone m5 --players 8 --mode 0 --stage-id 1 \
  --weapons 8001,2040,10,3000,0,1000,6000,7010 --timeout 2400
```

M5 默认 `--players 8`；1 / 2 / 4 只是中间阶段，返回 0 表示该阶段 `phase_passed`，其 `passed` 仍为 false。
只有实际八端完整对战且所有门槛通过，最终 `passed` 才为 true。`--admission-only` 只验证同房和资源，不开始比赛。
`--visible` 可让 player 0 建窗，其余仍 headless；不传时所有八端都 headless。

- 每个进程使用 `DM_OPMODE=0`、`DM_HEADLESS=1`；同时传 `DM_WINDOW=1` 验证 headless 优先级。
  720p 用原生 `WindowCrop 0,0 1280x720` 验证；原始交换链截图仍可能是 1920×1080。
- 新进程必须完成加载、加入房间并度过启动峰值，才启动下一端。稳定运行目标 ≤6 GiB / 端；
  冷启动峰值单独报告，不能据稳定占用同时启动八端。
- `--mode 0..4` 依次为 Turf War、Splat Zones、Tower Control、Rainmaker、Clam Blitz。
  `--stage-id` 用本地可显示 VersusSceneInfo 的 Id；也可用 `--stage-index 0..24`，按目录 DisplayOrder 排序。
  `--weapons` 须为每人一个本地 Versus 武器 Id，原生 kit 读回必须与请求一致。
- 设置、分队和开局都通过控制器脚本；最终队伍 UI 通过本机 Vision 检查双方人数。
  所有八端必须实际进入 InGame / ResultJudge / ResultWinners，Turf War 从入图到判定至少 178 秒；
  不改倒计时、结算、队伍内存或 PIA 消息。
- `resources.jsonl` 每两秒记录逐端帧、RSS、footprint、分类、压缩页与全机 AGX GPU 利用率。
  footprint / VM / 项目文件共享页快照分别保存在阶段命名文件。
  共享页按实际 resident clean file 页的 inode + offset 去重；COW / dirty / GPU / guest 页不列入共享节省。
  Metal 分配与 guest no-copy pool 重叠，不相加；RSS 也不能覆盖 GPU owned/unmapped 的物理占用。
- 新增 swapout、swap 相对本阶段启动基线增长 >16 MiB、非 normal 内存压力、或本任务 footprint 合计 >44 GiB，
  任一触发即失败并回收本次所有宿主，不继续扩容。
- 产物均在 `work/tests/m5-<N>p-*`，含完整输入、空气日志、截图、native kit、原生状态序列与 `result.json`。
  原件与参考档前后 hash、运行错误标记及优雅退出为所有阶段的硬门槛。

`DM_RESOURCE_REPORT=1` 提供逻辑帧时间、内部 pass / draw，以及低频 GPU 资源分类；
`DM_MEMSTAT=<path>` 提供逐秒 VM 记账。`<path>.request` 可请求只读项目文件页快照，产物为 `<path>.shared.tsv`。
这些诊断不导出训练观测、不提供同步 RL step；M6 尚未由 M5 自动完成。

2026-10-18 当前状态：两端整局、四端资源阶段通过；八端实际同房后在开局加载触发系统 pressure=2，
已按停止条件退出，八端整局未通过。分队首个输入等待和 RL-0/RL-1 的 OCR O/I 歧义也仍是待修复项。
完整数据与边界见 [PROGRESS.md 的 M5 最终停止位置](../notes/PROGRESS.md#M5-最终停止位置八端同房通过开局加载触发内存压力整局未通过)。
