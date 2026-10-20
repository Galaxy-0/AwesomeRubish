# A5 tournament runner (70-game native acceptance)

```sh
bash tests/run_all.sh --milestone a5 --games 4 --parallel 4
bash tests/run_all.sh --milestone a5 --games 70 --parallel 4 --fallback-three
.venv/bin/python -m arena.a5_audit arena/results/a5-paused-70-20261019.json --out arena/results/a5-accepted-70-20261019.json
```

The four-game smoke phase does not sign A5. The revised formal gate requires at least 70 valid
native games, all reaching Winners with both observers agreeing on the winner,
and void/(valid+void) <= 10%. Four concurrent 1v1 rooms (eight hosts) are the
default. A documented three-room fallback is authorized for excessive voids.
With `--fallback-three`, after at least 12 settled attempts a four-room void
rate above 10% stops new submissions while current rooms finish; remaining
fixtures resume in three rooms. `four_room_comparison` retains separate
statistics for the first parallel setting. Already valid fixtures are never
rerun; each segment records its room count and native overlap evidence.

Every adjacent logical fixture pair exchanges policy roles/teams/spawn sides
on the same map; pairs cycle through the three selected maps. Each policy
retains its declared loadout on either side. Each attempt uses fresh isolated
processes/save copies. Only rush and high-ground weak examples are provided.

A native `FATAL RL_STALL` or peer winner disagreement makes an attempt void.
Its owned room is cleaned
and the same logical map/role fixture is retried in a new attempt directory.
Other rooms continue. Arbitrary policy, integrity or setup errors are not
silently voided. Cleanup errors from the expected watchdog SIGABRT are retained.
Attempts are stored as `round-NNN-attempt-NNN`; only one successful attempt per
logical fixture counts. Above the feasible void budget, current rooms drain
before stopping. Voids remain outside the win/loss/draw denominator.

Raw game data stay under ignored `work/arena/tournament-*`. `native-barriers.jsonl`
contains referee metadata at synchronized ACKs, with actual native sample
frames. `inputs-per-present.jsonl` records exact held inputs for each present
interval. Positions are not interpolated into invented per-present state.
Separate policy allowlist observations/actions, periodic, Down-event and
Winners images (128x72) are retained. Policy/runtime, public atlas/visibility
hashes and per-session resource/cleanup evidence accompany each run.

Victory requires the two native observer-local score pairs to name the same
winner (or both a draw), reversing peer one's own/enemy order. The score is
their arithmetic mean. Both raw pairs, aligned differences and observer winners
are retained. A maximum difference strictly above 2 percentage points adds
`suspect` but still counts if winners agree. Suspect rate uses valid games;
void rate uses valid+void attempts. Small score differences never cancel
other rooms. Temporary 1v1 metrics use each observer's
own HUD enemy/self Down counters, including unknown causes. Position-classified
falls below the playable floor or outside static bounds are listed separately
with actual classification positions. Unknown causes stay unknown. No attacker
or weapon attribution is synthesized; A3b paint/knockdowns remain unknown.
Final Turf percentages are settlement values, not live world paint coverage.

Statistics use two-sided 95% Clopper-Pearson exact binomial intervals on decided
games, with draws separate. Superiority requires a lower bound > 0.5; with 70
decided games, at least 44 wins meet that rule. `statistics.by_policy`
reports HUD down/environment subsets, native score distributions and valid-game
wall/controlled durations. HUD non-environment subsets are not asserted to be
exact last-hit kills. Tournament elapsed wall time and void rate are separate.

`concurrency_windows` uses controlled start to the last successful native ACK,
with distinct host PIDs (eight for four rooms, six for three). A stalled room's
watchdog delay cannot inflate the windows. Merely selecting workers does not
satisfy the actual concurrent-room check. Runs below the revised 70-game gate
are diagnostic only.

`--resume` validates policy hashes, paired fixture identities, evidence hashes
and immutable native/skill/map runtime hashes. Completed fixtures are excluded
before submission. Cancelled attempts remain separately audited. Wall time
sums active run segments, excluding the human pause between sessions.
`arena/results/` contains numeric summaries and provenance hashes only. The
paused 70-game source retains its original `games_requested=100` and interrupted
status; the separate acceptance audit checks all 70 native score traces and
maps each winning seat through `role_to_policy`. It does not rewrite the source.
The original 32-game result plus round-032 was reconciled from native traces
without modifying any old result file:

```sh
.venv/bin/python -m arena.checkpoint --legacy work/arena/tournament-20261019-021200-165802/result.json --out arena/results/a5-partial-20261019.json
```

## T1 BO3 输方更新入口

每轮完整打三局（不因先赢两局提前结束），三个房间并行，各地图一局。
`a/b` 始终对应命令行的 `--policy-a/--policy-b`；`player_0/1` 是出生点/阵营席位。
轮号为非负整数：偶数轮a在player_0，奇数轮a在player_1，三张图整体交换。
因此任意连续两轮，每份策略在每张图各占两个席位一次。

```sh
.venv/bin/python tests/t1_round.py \
  --policy-a arena/policies/alpha --policy-b arena/policies/bravo \
  --round 1 --out work/arena/t1/round-001
```

`--out` 必须是ignored work下尚不存在的目录。输出：

- `result.json`：沿用A5的matches、role_to_policy、outcome、双端原始比分、平均比分、suspect、HUD倒下与环境死亡、statistics及原生并行窗口；另有顶层round轮号及策略快照/源码哈希。matches中的round仍是本轮逻辑局号0/1/2。
- `summary.json`：逐图胜者、按席位和按策略映射的比分、按策略HUD倒下、本轮胜局数与round_winner（a/b/draw）。三局未齐时本轮胜者为null。
- `game-N-attempt-NNN/`：每次尝试的A5原生输入/状态/截图。void自动补跑同一地图、同一席位，不取消其它房；无效尝试完整保留，不计胜局。沿用A5的watchdog/双方胜者分歧判void，普通策略/完整性错误失败退出，不冒充void。Ctrl-C只回收本命令所属房间。
- `policies/a/`、`policies/b/`：开局前的只读使用快照（内容哈希核对原件/副本/再次读取的原件），运行中作者可继续改工作目录。快照留在ignored work，命令不会修改作者目录或读取对方源码用于战术分析。

若三局含平局且双方胜局数相同，round_winner为draw，没有自动指定输方。
BO3胜者是轮次调度结果，不是A5的70局统计优势签收；full_a5_passed保持false。
入口发现非空`DM_TEST_SPECIAL`即在启动/快照前拒绝。

## 第4房：按版本运行熟练度

```sh
.venv/bin/python tests/proficiency.py \
  --policy arena/policies/alpha --out work/arena/proficiency/alpha-v2.json
```

默认13项：静止靶3次；横移6/12/18各3次；乌贼滑接近1次。
各场景和分距离房间串行执行，任一时刻只占一个房间，可与上面的三房BO3同时运行。
结果为指定JSON和同名Markdown；未指定.json后缀时写入该目录的scorecard.json/.md。
每次先捕获完整策略版本，卡片绑定源码SHA256、配装、调用间隔、公共库及A6评测哈希；
`policy_version`给出快照与原生运行索引。作者后续修改不影响本次测量。
既有输出不覆盖，失败房保留原件且不生成冒充完整结果的卡片。

`--repeats 1`运行5项冒烟（静止1、横移三距离各1、接近1），不能与13项正式表直接比较。
该入口沿用A6固定射手/主武器夹具和自然特殊量，不接受DM_TEST_SPECIAL；
特殊量开关的独立测试仍用`tests/probe_a6_test_special.py`。
逐项unsupported与右截尾原样保留；接近项仅N=1，分数不单独解释战术输赢。

两个入口默认共用`work/arena/t1-load-slots/`的两把加载锁，房间激活标记仍独立。
如指定`--shared-load-slots PATH`，同时运行的两个命令应使用同一路径。
锁只限制重加载，不把四个房间串行化；不重编或替换dmhost。
建议在一个临时`caffeinate -i`父进程下同时启动两个命令，避免机器休眠触发墙钟看门狗。
推荐并发为独占机器的3房BO3＋1房熟练度；不要再叠加作者自测房。
若资源保护触发，保留失败原件和原阈值，改为BO3三房先完成、熟练度单房随后运行，
使用全新输出目录。共享加载锁不能限制其它命令另开的房间。
组件测试（不启动游戏）：

```sh
.venv/bin/python tests/test_t1_components.py
.venv/bin/python tests/test_settlement.py
```

结算动画独立于策略调用间隔：双方停止策略后，使用30present中立块推进到
Winners，上限为1800present（fixed60下30秒游戏时间），按实际ACK帧数计数，
末块截断到剩余预算。不会因step_frames=1而只给120帧结算时间；对局记录保留
settlement_budget_frames与settlement_frames。超出游戏时间预算仍未到Winners则失败，
不会伪造结算或比分；原生无进展看门狗及墙钟会话截止仍生效。

2026-10-20独占实机冒烟已通过：rush vs high-ground第1轮三图有效、0 void，
high-ground以3–0获胜；三局均在额外480present结算后到达双方Winners。
同时运行的rush五项熟练度全部measured，JSON/Markdown已生成，源码哈希与BO3一致。
四房实际原生控制窗口重叠239.55秒、8个不同宿主PID；全部自有宿主已退出。
数值与证据哈希索引见`arena/results/t1-entry-smoke-20261020.json`。
这次证明入口和3＋1并发可用；五项冒烟不替代默认13项正式熟练度表，BO3不替代A5统计签收。

A7 原生开局为已签收的显式选项，默认入口仍使用已接受的菜单流程。先构建独立宿主和模块；不要覆盖默认dmhost或work/build/patched_v720896：

```sh
.venv/bin/python tools/build_a7_host.py --out work/a7/dmhost-native
.venv/bin/python tools/prepare_a7.py --out work/a7/patched-native
.venv/bin/python tests/t1_round.py --policy-a arena/policies/rush --policy-b arena/policies/high-ground --round 0 --out work/arena/t1-native-smoke --native-host work/a7/dmhost-native --native-patched work/a7/patched-native
.venv/bin/python tests/test_a5.py --games 4 --parallel 1 --native-host work/a7/dmhost-native --native-patched work/a7/patched-native
.venv/bin/python tests/proficiency.py --policy arena/policies/rush --out work/arena/rush-native-card --repeats 1 --native-host work/a7/dmhost-native --native-patched work/a7/patched-native
```

两个native参数必须一起提供；宿主可执行文件、构建源哈希、原生观察门均校验后才开局。当前适配层只开放两人占地与三张擂台地图。阵营固定player_0/1为0/1，轮次换侧继续由原有roles映射策略，outcome a/b口径不变。Python入口尚不开放原生种子参数；Gym seed仅动作空间种子。底层`DM_SCENE_SEEDS`四个uint32的实验已验证原生发布/两端读取，但未证明这些值覆盖所有随机流，不可当作完整确定性控制；比分按下述自身复现波动口径验收。

复用池由协调进程持有，完整双方Winners且有效比分后才可保留。下一局换图仍经游戏场景、Create/Find/Join、私房设置发布和MatchFix流程。装备/配装变化、未到Winners的训练夹具或取消会关闭原进程再建房；不在旧进程里冒充热更新装备。已保留房间的进程若意外退出，下一次租用先完整清理再重建；存档/参考文件完整性异常继续报错，不能被恢复逻辑吞掉。A5同一worker的连续任务可复用；当前t1_round CLI一轮退出会回收三个worker及其宿主，不声称跨CLI命令保存房间。熟练度夹具通常提前结束，因此使用统一原生开局但关闭未结算房间。

2026-10-20阶段结果：两局同PID换图均到双方Winners；原生三图BO3通过（rush 0–3 high-ground、0 void），一份参考策略五项熟练度全部measured。单房旧流程695.789秒→原生375.279秒；三房BO3为633.589秒，尚未达到原10分钟目标。此阶段推荐最多三房，熟练度在BO3之后串行；原生路径未重新验证3＋1并发，不沿用旧菜单的四房结论。证据见`arena/results/a7-entry-smoke-20261020.json`。

**A7已签收（2026-10-20 17:37），full_a7_passed=true。** v43/v16菜单与原生各3局，同输入/种子/实际出生侧；均值差0.266667/0.366667pp≤自身波动上界2.2/1.3pp，全部九对跨组差也≤上界。最终18项A1–A6作业、三份13/13分数表原始轨迹独立审计、41项A7组件全部通过。当前A5新测为同图换侧同PID两局；另外最终v43的District→Yagara两完整局也到双方Winners并复用同PID，原生场景/阶段/代次读回已校验。总审计、原件SHA及范围见`arena/results/a7-acceptance-20261020.json`。此前0.1pp单对照负例保留，当前按自身复现波动验收，不声称确定性。正式T1仍用显式native参数选择新路径；A8在A7推送后另建渲染实验版本。

离线入口：`tests/test_a7_scene.py`、`tests/test_a7_start.py`、`tests/test_a7_comparison.py`。严格比分审计示例（失败仍写JSON并返回非零）：

```sh
.venv/bin/python tests/analyze_a7_routes.py --menu work/a7/baseline-20261020-144058-646609/result.json --native work/a7/baseline-20261020-144121-097488/result.json --out work/a7/frozen-input-seeded-v39.json
```

当前复现性入口（原始数据只放work，最多3房）：

```bash
.venv/bin/python tests/probe_a7_repeatability.py --host work/a7/dmhost-team-v43 --patched work/a7/patched-seeds-v16 --policies work/a7/replay-policies --out work/a7/repeatability-v43 --parallel 3
.venv/bin/python tests/probe_a7_repeatability.py --out work/a7/repeatability-v43 --analyze-only
.venv/bin/python tests/regress_a7.py --host work/a7/dmhost-team-v43 --patched work/a7/patched-seeds-v16 --out work/a7/final-regression-v43 --parallel 3
```

输入须先冻结；旧Session菜单与生产NativeSession各至少3局，固定原生四字种子，并检查实际消费、实际出生位置/朝向/槽、全部逐present动作和双端Winners。逐策略比较两组均值差≤两组内部最大两两差的较大值；输出所有组内/跨组差和胜负频数。这是经验波动口径，不声称确定性或置信界。任何参数/运行失败都不得混入噪声分布。v42曾发现一局原生出生侧相反，整组不签收；v43在MatchFix初始化后重新提交游戏自身队伍选择并读回，六局实际出生侧一致。3+3结果：菜单组内最大差1.0/1.3pp，原生2.2/0.3pp，自身波动上界2.2/1.3pp；组均值差0.266667/0.366667pp，全部九对跨组差也均≤上界，两组均a1/b2。原件SHA和全部差值见`arena/results/a7-repeatability-20261020.json`。

最终回归不调用会重编默认dmhost的旧run_all分支；A1/A2/A3a与A4三图30路线使用原断言，伤害新测，A6重测支持操作/控制组/时序/射程/特殊量生命周期及三份冻结策略各13次试验的分数表（原始轨迹独立审计）。A5严格重审70局历史原件，再测当前运行版两局同图换侧且要求同PIDs连续开局。本次全部通过，A7签收后继续A8。

最终回归需要特殊量测试时，构建生产宿主的显式测试派生版，只添加既有测试宏，不改变生产宿主；构建记录绑定父宿主与相同生产源码。新运行的`regress_a7.py`会自动构建该派生版，也可传`--special-host`指定已验证构建。正式T1/A5对战仍拒绝`DM_TEST_SPECIAL`。本次旧队列的三项测试驱动错误保留原件，队列完整结束后再补测，禁止与原队列抢占额外房间：

```bash
.venv/bin/python tools/build_a7_host.py --test-special-of work/a7/dmhost-team-v43 --out work/a7/dmhost-team-special-v43
.venv/bin/python tests/retry_a7_regression.py --previous work/a7/final-regression-v43/result.json --special-host work/a7/dmhost-team-special-v43 --out work/a7/final-regression-v43-supplement --parallel 3
.venv/bin/python tests/probe_a7_continuous.py --host work/a7/dmhost-team-v43 --patched work/a7/patched-seeds-v16 --out work/a7/continuous-v43-final --timeout 2400
.venv/bin/python tests/audit_a7.py --baseline work/a7/repeatability-v43/result.json --regression work/a7/final-regression-v43-supplement/result.json --continuous work/a7/continuous-v43-final/result.json --out arena/results/a7-acceptance-20261020.json
```

跨图补测放在上述三项补跑之后串行执行（本次在补跑释放名额后启动，始终≤3房）。最终审计要求完整18项作业、相同生产宿主/运行文件、三份13/13分数表及原始轨迹独立复核、新鲜A5同图换侧同PID两局及额外跨图连续开局、历史70局精确审计、关闭日志后的乌贼滑对照校准。任何失败或哈希漂移均拒绝产生签收文件。
