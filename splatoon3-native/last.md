# RL 阶段1恢复进行中（2026-10-23）

用户采纳`work/codex/astra-r1.md`并重置卡点计数。当前只推进阶段1，正式门槛不变；此前失败记录保留在下方。

ZR/ZL保持/按下/松开参数化、PPO优势下限/逐minibatch KL/逐头指标和按term/trunc评估已实现。13项学习组件与原14项CPU环境回归通过。未训练固定靶3种子对照已完成，切换语义仍极少满蓄；正在做固定6u靶的配对PPO（两臂×101/202/303，各128更新），之后仅改距离21u复测满蓄（离线两满蓄KO、三轻斩无伤控制已留原件）。短课程使用合成平地隔离控制，不是温泉峡谷正式验收；不据近靶轻斩KO签收蓄力。

远端私有`~/splatoon3-native-rl-stage0/`：源码r8/r9/r10；tmux `spl3-r1-fixed-paired`和等待其正常结束的`spl3-r1-fixed-charge`，脚本`fixed-paired-r1.sh`/`fixed-charge-r1.sh`；原件目录`stage1-action-ablation-r1`、`stage1-fixed-paired-r1-*`、`stage1-fixed-charge-r1-*`。另外资格复核`spl3-r1-verify-courses`（r12）结束后，`spl3-r1-pose`（r13）只有三种子21u首次生命门都通过才继续随机距离/朝向窄相机课程；脚本`verify-courses-r1.sh`/`pose-r1.sh`。首个21u种子原评估已从1/128→128/128，待三种子资格复核，不代表正式验收。下一步先查日志/exit再行动，不重复启动。SSH偶发超时/EOF，后台作业与连接分离，不计学习卡点。

阶段1尚未通过，未进入更高课程/阶段2或T1/S1。源码/运行约定与当前边界见`notes/rl-stage1-restart-20261023.md`。未动policies/原存档/宿主/VPT，不提交资源/派生网格/生成页/checkpoint。

---

# RL 阶段1：未通过，已按两轮规则停止（2026-10-23）

实现了主武器only的GPU PPO自我对战、158万/163万参数共享GRU、历史池、action mask、CSV/Elo和可播放回放。两轮有效训练各32,047,104环境帧：

| 同种子、每角色64局 | 未训练水刀赢随机 | 训练后水刀赢随机 | 未训练/训练后.52赢随机 |
|---|---:|---:|---:|
| A 基版 | 55/64 | 2/64 | 64/64 → 60/64 |
| B 自身动作反馈＋输入先验 | 34/64 | 12/64 | 64/64 → 64/64 |

两轮均未学出收益，停止续训，不进入阶段2。B的100% .52胜率在初始化已达到，不能算RL成果。D4近距61/64涂地胜但水刀0伤害/0KO；残血潜墨回血观察0，掩体意图未证实。曲线无NaN但行为退化，不能签收基础对枪。错误自落击杀奖励pilot16.06M已修复并排除，原件保留。

有效64,094,208帧是两个独立模型之和，非单模型64M；有效训练墙钟1067.52s（17.79分钟，不含评估/开发），峰值CUDA allocated2805.75MiB。CPU最终9项学习检查、原14项CPU/CUDA环境回归和GPU击杀归因控制通过。阶段0仍按用户验收接受；FOV纵55°/横85.56559°为待原生核验假设，实图4.34u偏差保留。

详细报告：[notes/rl-stage1-20261023.md](notes/rl-stage1-20261023.md)；聚合数值/SHA：[results JSON](notes/rl-stage1-20261023-results.json)；用法：[rl/gpu/stage1/README.md](rl/gpu/stage1/README.md)。源码分段提交推送，checkpoint/地图/日志留`asuka0:~/splatoon3-native-rl-stage0/`私有目录，A/B分别`stage1-credit32-r1`/`stage1-feedback32-r1`。远端driver均exit0，无活动tmux/GPU训练进程；64M续训脚本未启动。

本地私有回放已在showcase实际播放、暂停/跳帧/双侧跟随，无脚本error，未发布：

- 水刀：`work/rl-stage1/preview-feedback-r1/index.html`（6,337,285 bytes）；截图`work/rl-stage1/replay-stamper-r1.png`。
- .52：`work/rl-stage1/preview-feedback52-r1/index.html`（6,378,666 bytes）；截图`work/rl-stage1/replay-52-r1.png`。
- 曲线：`work/rl-stage1/curves-credit32-r1.png`、`work/rl-stage1/curves-feedback32-r1.png`。

未启动原生宿主/T1/S1或阶段2，未动policies/原存档/VPT；未提交游戏资源/派生网格/生成页/截图/checkpoint。

---

# RL 阶段0：环境实现与有界停止（2026-10-23）

独立venv已安装 **torch2.12.1+cu126** 并完成RTX4070Ti真实CUDA运算；原cu128安装PID3407336已核对终止，VPT未使用/修改。源码位于`rl/gpu/`，无训练入口。

- **完整观测吞吐通过**：1024局、2帧决策、每次32×18射线/16实体遮挡/HUD/minimap，三次 **306177 / 306090 / 306124环境帧/s**；413.4MiB allocated / 750MiB reserved。由int64墨图16.7万提升到int8约30.6万，无缩水观测或改20万阈值。
- **数值与稳定性**：14项CUDA单测、8192射线/20步Graph+部分重置、另20步编译离散语义对照通过；S1平地8×120f最大位置1.35e−5u、HP0.20/100；实图粗几何24路线最大4.34u。4局随机策略均180秒、有限值/零和/终止正确，但无交火，不能当战斗质量证明。
- **回放**：GPU trace已在现有showcase本地实际播放到F505、暂停与Alpha跟随；私有页`work/rl-stage0/preview-gpu-r1/index.html`，**5,984,402 bytes**；截图`work/rl-stage0/replay-browser-gpu-r1.png`，未发布。
- **未过项 / 停止原因**：原生+5满推0.0642272rad/f、eye/at已测；两轮只读引用探针未确认55°候选FOV的最终投影轴向，保留accepted=false，按两轮无进展停止房间/地址试探。网络断开未计卡点。另.52仅主武器，副特尚未建模，不能称完整套装。

**阶段0未全门签收，不开始训练，不恢复T1/S1。** 原生测量峰值1房，进程均关闭；远端测试tmux已完成。源码/文档提交推送；游戏参数/派生网格/截图/生成页/wheel均不提交、不删除work。详细证据与后续明确选项见[环境报告](notes/rl-stage0-environment-20261023.md)和[数值/SHA](notes/rl-stage0-environment-20261023.json)。

---

# 历史：RL阶段0早期安装停止（当前状态见上）

阶段0未通过，未开始训练。首次asuka0硬件探测成功（4070Ti 12282MiB、24核、30Gi RAM），私有目录`~/splatoon3-native-rl-stage0`及独立venv已创建。首轮NVIDIA NVRTC依赖4.7/88MB下载超时；第二轮可续传/官方PyPI依赖源已进入889MB torch wheel下载，但SSH再次断开，两次重连均代理握手失败。第二轮安装最终状态及是否仍有有限安装进程**未知**，不能声称CUDA环境就绪或远端已收尾。

按两轮规则停止追加尝试，不改SSH配置/隧道。只有`rl/gpu/`安装脚本、17移动档/双9档镜头/五独立按钮的配置契约；缺少原生+5/FOV标定时拒绝配置。没有GPU模拟器、性能、机制单测、随机局或回放验收。未启动任何游戏房间、未向远端拷贝游戏参数/网格，policies/宿主/原存档/T1/S1均不动。

说明与门状态见[notes/rl-stage0-20261023.md](notes/rl-stage0-20261023.md)，原件`work/rl-stage0/bootstrap-blocker-20261023.json`。远端保留`install-torch.log`、`install-round2.log`，恢复连接后先核查已有进程/日志/可能的`cuda-verify.json`，避免重复安装。契约语法/枚举范围/缺失标定拒绝检查与shell语法通过，不能当GPU环境单测。源码与停止报告提交推送后停下。

---

# D4 自动补算交互（2026-10-23）

只改页面展示/任务调度，未启动游戏。更换敌位、四向朝向或手速后，缺少离线完整结果/内存完成缓存时300ms防抖自动补算；新选择直接终止忙碌Worker并拒绝旧请求。地图上方居中显示百分比、格数和秒数；普通可站点优先、首行和后续分块逐步显示，候选①②③及结论随结果更新，结束后自动选择①并重建路线。保留“重新计算”按钮，反查原入口继续可用。关闭图层/换图/切正反查也取消旧任务。

完整结果按地图/敌位/朝向/手速缓存在本次页面内存，切回来即时显示；中断查询保留已收到行并续算；完整路线另有缓存。刷新页面清空，未写存储文件。预算截断与限定外仍为未知，动态①②③只称已计算候选；既有完整查询/冻结排序优先，未改变研究结论。

浏览器耗时（同一Chrome，无游戏；不能混用不同敌态声称加速倍数）：

- 温泉峡谷#779 / +X / 40f：原版完整1580格约15分24–34秒才刷新，最终①#641。新版首批行0.907s、首个可杀点及①4.491s（含防抖），随后继续渐进计算；本次用于快速切换/取消测试，没有把首批时间当完整完成时间。
- 边缘#0 / +X / 40f：新版普通集合718格12.280s、全1580格37.246s。完成缓存切回UI操作33ms；默认普通集合无确认点时明确提示，未知不当失败。
- 普通可站#95 / +X / 40f：首批0.476s、首个可杀点19.170s、普通集合259.029s、全1580格486.102s；完成后自动选①#121，路线/槽量/回放自动出现。跨地图切回该完成缓存的UI操作243ms，不重新算。

完整精算依敌态仍可能分钟级。当前收益是先显示、可取消、复用已算结果，并非把复杂模型全图压到10秒。

生成页 `showcase/index.html`：5,291,854 bytes，SHA256 `89e92cc33ebb3a689b994955373275bee531a6426f0d32b5104d3f9cdf8a4225`。未提交/未发布；派生网格、截图、游戏资源均未提交。所有原嵌入数值字段逐项不变，只有展示源码哈希更新；数值Worker核心和`d4_safe_worker.js`不改。未动对战代码、policies、宿主、存档；T1/S1暂停。

验证：24,603项原资源/数值审计，整页JS语法和`node showcase/test_d4_worker.cjs`通过（优先次序、增量行、原索引顺序、未知/预算不变、续算、取消后无最终热图）。Chrome实测敌位/朝向/手速自动触发、快速切换取消、部分缓存恢复、完整缓存命中、完成自动刷新、重新计算按钮。亮暗×3D/2D/390px自查，390px内容宽390，无横向溢出；无页面脚本错误，旧three.js弃用提示单列保留。临时视口恢复，自建页关闭；原件不删。

截图（本地自绘展示，均不提交）：

- `work/showcase/d4-auto-light-progress-3d-20261023.jpg`
- `work/showcase/d4-auto-dark-progress-3d-20261023.jpg`
- `work/showcase/d4-auto-light-progress-mobile-20261023.jpg`
- `work/showcase/d4-auto-dark-progress-mobile-20261023.jpg`
- `work/showcase/d4-auto-light-progress-mobile-2d-20261023.jpg`
- `work/showcase/d4-auto-dark-progress-mobile-2d-20261023.jpg`
- `work/showcase/d4-auto-dark-progress-2d-20261023.jpg`
- `work/showcase/d4-auto-light-complete-3d-20261023.jpg`
- `work/showcase/d4-auto-light-complete-mobile-top-20261023.jpg`
- `work/showcase/d4-auto-dark-complete-mobile-top-20261023.jpg`

审计原件：`work/showcase/d4-auto-baseline-20261023.json`、`d4-auto-first-result-20261023.json`、`d4-auto-browser-final-20261023.json`、`d4-auto-data-audit-v4-20261023.json`、`d4-auto-check-v4-20261023.json`。仅展示源码与本报告提交推送，完成后停止。

---

# D4 展示辨识修复（2026-10-23）

仅展示层，未启动游戏。D4开启自动使用中性灰底；绿/琥珀/红结果格、白色偷袭点、未知虚框、不可达不填色。地图左下常驻图例，上方直接显示敌位/朝向/最佳①/剩槽/偷袭或暴露。大号①②③图钉可点，默认温泉#634自动选中并显示路线；敌人具有人形、箭头和180°半圆。手机2D自动纵向排图，首屏可见结论、图钉和图例。空结果明确提示换朝向；关闭D4恢复原底图和控件。

图钉标签只从原有完整查询复制；模型/原始数据/研究结论不改。所有原有payload字段逐项一致，18个冻结top1/top2保持一致，11个已有完整敌态有排序标签；未完整计算只称候选。代表#634仍124f、69.90%、零钩偷袭；完整D4状态沿用下方既有记录，不因视觉修复改变。

`showcase/index.html`已重生，5,283,490 bytes，未提交/未发布。整页JS语法、原字段不变/标签原件/冻结点审计及24,591项页面检查通过。三图默认点、无确认点提示、图层开关恢复、2D/3D俯视、亮暗及390px通过；390px内容宽390，本页无控制台错误（浏览器扩展日志另保留）。临时视口恢复，自建页关闭。未动policies、存档、宿主或对战代码；T1/S1暂停。

最终截图（均在work下，不提交）：

- `work/showcase/d4-visual-final-light-3d-top.jpg`
- `work/showcase/d4-visual-final-dark-3d-top.jpg`
- `work/showcase/d4-visual-final-light-2d.jpg`
- `work/showcase/d4-visual-final-dark-2d.jpg`
- `work/showcase/d4-visual-final-light-mobile-3d.jpg`
- `work/showcase/d4-visual-final-dark-mobile-3d.jpg`
- `work/showcase/d4-visual-final-light-mobile-2d.jpg`
- `work/showcase/d4-visual-final-dark-mobile-2d.jpg`

审计：`work/showcase/d4-visual-data-audit-v7-20261023.json`、`d4-visual-check-v7-20261023.json`、`d4-visual-browser-final-20261023.json`，绑定最终页SHA。详情见showcase/README.md；源码提交推送后停止。

---

# D4c 限定交付 / 停止（2026-10-23）

**新216全部闭合；完整D4未闭合。** 最初被打断两刀result/steps/双方host.log原件与SHA已保全。优先查横5球左右/纵7球上下裁剪，最终物理数组身份、核心共享及接触分半仍未闭合；未把领域知识误写为已否定。四刀机制预算用完后按授权切换接触确定不相交、整波墨刃场地清晰的有限路线。

三图各3敌态×top1/top2/对照×8：216有效（217尝试，1发动前进程失败，原例按规则只重试一次成功），0对战未决，旧12/机制/资格0复用。优选144/144先杀，对照0/72；各敌态8/8、8/8、0/8。原生KO124–128f，剩槽69.074–69.815%；队列墙钟6时28分47秒、峰值3房。原驱动退出0、stop_reason=null；当前无dmhost，143项原件/保护宿主/冻结输入/模块SHA一致。

**边界**：所有27点为零钩满蓄接轻斩40f，不证明飞索切入/连钩。原生.52固定脚本直线枪口跟瞄未补下坠，不是理想防守方/玩家胜率。实际姿态可判136次，16次模型原生不一致、80次未知均保留。接触规则、极限连钩、完整D4及全局最优仍未闭合；不恢复T1/S1，不改策略/原存档/正式默认宿主，不启动下一阶段。

[交付报告](notes/d4c-delivery-20261023.md) · [216数值/逐例原件SHA](notes/d4-blade-only-native-20261022.json) · [两半机制](notes/d4-halves-20261022.md)。原件 `work/d4/restart-v4/chain-preservation-v1.json`；正式批次 `work/d4/restart-v4/blade-native216-v1/batch.json`；最终完整性 `work/d4/restart-v4/integrity-20261023-final.json`。

生成页 `showcase/index.html`，5,259,960 bytes（<10MB）；11完整限定查询/14,771起点行，并非63,328组合全量完成。支持敌位/四向/四手速正反查、3D路线/暴露/槽曲线/步骤回放、旧均匀先验附录和新原生实数表，未知不涂失败。Python/浏览器72单刀/288终结/45查询/3预算恢复通过；最终24,526项格值/trace/来源/资源审计通过。点634复核124f/69.90%/零钩偷袭，控制台无错误，390px内容宽390无横向溢出。页面未发布。

最终截图（本地自绘页面，均不提交）：

- `work/showcase/d4c-final-map-light-20261023.jpg`
- `work/showcase/d4c-final-map-dark-20261023.jpg`
- `work/showcase/d4c-final-native-light-v3-20261023.jpg`
- `work/showcase/d4c-final-native-dark-v3-20261023.jpg`
- `work/showcase/d4c-final-native-mobile-20261023.jpg`

审计 `work/showcase/d4c-final-check-v2-20261023.json`，UI摘要 `work/showcase/d4c-final-browser-20261023.json`，二者绑定最终页SHA。生成页/派生网格/截图/游戏资源不提交；源码和文档分段推送，本轮在最终提交推送后停止。
