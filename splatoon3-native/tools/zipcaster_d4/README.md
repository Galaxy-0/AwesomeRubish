# D4：给定敌情，反推全图开大点

输入敌人位置/固定世界朝向，查询地面开大点。旧D3-R均匀敌人先验排名不再作主结论。2026-10-22采纳Astra后已重启：逐刀生成点/体积归因、同状态八刀、真实接触形状/世界变换与20+35独立伤害已完成机制检查点；正在接回新模型，正式三图重复/全量模型仍未签收。见`notes/d4-attack-confirm-20261022.md/.json`。旧浏览器QA不能替代新模型原生验证。测试特殊量/直接瞄准仅测量夹具，默认/正式对战禁用。

重启入口（原件新路径，禁止覆盖）：

- `ablate_attacks.py --out <新JSON> [--results <闭合原件> ...]`：逐级替换与核心/侧球分解；删除前截断明确标记。
- `attack_probe_v4.py --plan <冻结计划> --group <组名>`：每刀自然返回/恢复摆位和满血/重新发动，原生内部计数500–530门；每房最多两刀，未尝试项另开新房。`infinite`不延长原生大招计时。
- `build_contact.py --out work/d4/<新构建>`默认`contact_sensor_v3.h`，读取实际box/cylinder、创建方向和engine父对象；私有gate51/BuildID/测试瞄准门。旧`contact_sensor.h`是被否定的d8矩阵假设复现源码，不作当前传感。
- `contact_probe_v2.py --host <新私有宿主> --plan ... --group ...`、`report_contact.py --results ... --out <新JSON>`：四帧局部形状与物理消费者使用的世界变换核对。
- `attack_model_v4.py`、`attack_sequence_v2.py`、`model_v3.py`：真实体积/接触/强制位移后再瞄准/有限程序组件。尚未完成新全图和正式原生排名，不能据此给最优推荐。

```sh
.venv/bin/python -m unittest tools.zipcaster_d4.test_attack_geometry tools.zipcaster_d4.test_attack_batch tools.zipcaster_d4.test_attack_sequence tools.zipcaster_d4.test_attack_sequence_v2 tools.zipcaster_d4.test_model_v3
```

历史搜索/执行入口（旧远端代理，仅复查；不可与修正模型结果混池）：

- `model_v2.py`：固定180°视锥、原生参数代理、完整枪口→生成点碰撞段、31f开大就绪、严格槽截止。
- `query_v4.py` + `reverse_v2.py`：全部声明开大点，0–3钩、有限程序、反向预算下界/成本有序路径；出刀前已经确定倒下的前缀可安全丢弃。不是beam/排名子集。
- `enumerate_v4.py`：按敌态/手速批算，gzip原件可续；旧闭合文件按SHA复用。timeout/error保持未知，不能涂成0。
- `duel_v4.py` / `batch_duel_v3.py`：≤3自建房，原生固定逻辑视锥对手、有限完整槽、真实HP/绑定/弹体；全局同分点仅按普通摆位支持作tie-break，差点需视锥内部余量。每点8次，摆位void最多重试一次，战斗失败不补抽。
- `report_zero.py` / `report_duel.py`：只读闭合原件，原生HP确认、source clock归一、严格KO<槽零；按钮/driver退出0不算击杀证明。

例（所有输出用新路径，不覆盖原件）：

```sh
.venv/bin/python -m unittest tools.zipcaster_d4.test_reverse tools.zipcaster_d4.test_model tools.zipcaster_d4.test_model_v2 tools.zipcaster_d4.test_reverse_v2
.venv/bin/python tools/zipcaster_d4/query_v4.py --graph work/d4/graph-v2-Yunohana --enemy-index 772 --heading 0 --speed 40 --out work/d4/new-query
# 只看至少一钩：另加 --min-hooks 1。--top-only 只是top2证明，不是整张热图。
.venv/bin/python tools/zipcaster_d4/enumerate_v4.py --states work/d4/all-enemy-states-v1.json --out work/d4/new-bank --prior work/d4/all-full-v3 --workers 4 --seconds 60
.venv/bin/python tools/zipcaster_d4/batch_duel_v3.py --plan work/d4/calibration-plan-v3.json --out work/d4/new-native --rooms 3 --repeats 8
# 有界停止新增房间：在该输出目录写 STOP_LAUNCH，现有自建房正常收尾。
```

不要与另一个原生批次叠加超过3房；不杀非本任务进程。`prepare.py`覆盖所有已知材料允许竖墙面/双法线3u采样；`flight_v2.py`按训练自己的飞行轨迹拟合后重计时。地面/天花板绑定、完整高差/动态物体/侧球/贴身伤害仍未定。Atlas里有封闭/孤立高度层，全部保留但不能冒称原生可站；普通导航支持只是另一个几何代理。

0钩基线很重要：允许任意开大点时，背后已在刀程内的直接两刀通常最省槽。这不证明飞索自身更强；额外一钩/连钩验证与全局top2地面基线分开。无误差分布的确定性条件模型P为0/1，原生重复率另列。100HP/35+70累计、锥内理想枪口跟瞄是当前明确假设；不把它冒称真实玩家分布。

展示：`showcase/build.py`生成ignored单文件页面。4bit剩槽分档/偷袭热图＋自写WASM同谓词几何＋本地Worker重建选中路线；反查固定S可杀的敌态。仅处理后的数值、自己的BVH/几何标记，不带原始资源文件。浏览器与Python已有1800几何/180查询对照，前缀优化有47496对值/风险一致性对照。生成页、衍生网格/trace、截图和二进制都不提交；只提交生成/计算/测试源码与数值报告。已有v1/v2脚本保留为实验原件，不作当前入口。

`attack_probe.py`固定俯仰/自然HP恢复、`duel_v5.py`成套偏移连招仅诊断；`report_blocker.py --out <新的JSON路径>`复核闭合案例/保护SHA/资源峰值并导出不含网格的数值报告。两轮原件全部保留，不混进正式重复率。

新执行/计算入口（2026-10-22检查点，仍有接触过滤反例，不能作为已签收推荐）：

- `duel_v6.py` / `batch_duel_v4.py`：接触与墨刃生成前分别重瞄；实际姿态预报只记录、不筛掉战斗失败。冻结依赖、每局新进程，`STOP_LAUNCH`只阻止新任务，当前房间自然收尾。
- `query_v7.py`：必要包络＋lazy终点求解＋完整成本序路径。`--top-only`只证明top2，未查格保持未知；未设candidate cap时才允许声明完整。`query_v5/v6`是性能实验历史，不混用其未闭合原件。
- `verify_bound.py --out <新JSON> --poses 100`：固定种子离线可采纳性抽查，结果不等于原生验证。
- `audit_contact_duels.py --results <闭合result.json> ... --out <新JSON>`：实际接触体世界变换/胶囊候选与场地诊断射线。相交不授予伤害，射线是假设而非已确定的原生规则。
- `contact_sensor_v4.h`另读伤害组件，用`build_contact.py --sensor tools/zipcaster_d4/contact_sensor_v4.h --out work/d4/<新私有构建>`构建；不覆盖默认或受保护宿主。

当前记录见`notes/d4-restart-executor-20261022.md`。正式批次12/216后因新的高台接触反例暂停；旧页面Worker仍是远端代理，不能用其交互计算宣称本版模型通过。

本轮最终按两轮未闭合上限停止，见`notes/d4-restart-stop-20261022.md/.json`。`build_contact_transform.py`＋`contact_sensor_v5.h`只用于限定空间gate52的只读消费者区分，私有`OBS_MAX=53`；`audit_contact_transform.py`只接受严格指针归属。实际对照中未见该限定区域的消费者调用，不能据此证明所有物理路径均未更新。所有新增房间已收尾，剩余204正式案与新热图/页面不继续。`report_restart.py --out <新JSON> --status stopped`核对新duel_v6原件、已记录PID/全局宿主、峰值与保护哈希，不导出网格/原始字节。

D4c（2026-10-22）独立入口，当前进行中，非D4签收：

- `contact_hypotheses.py` / `contact_field.py`：旧刀按position_sample_frame去重对齐，三种LOS起点、精确box/finite-cylinder与三角面/法线假设表。`trace_contact_filter.py`核对当前类虚表+248恒返回1，不把注册候选命名为LOS。
- `build_contact_chain.py` / `contact_sensor_v6.h`：新work私有宿主，保留6个保护宿主，扩大gate52并读取接触叶形状、过滤返回和Life pending。阳性刀pending1400已观测；接收/提交候选入口在阳性刀也零调用，观测链仍不完整。
- `inspect_blade_halves.py`、`blade_halves.py`、`halves_hypotheses.py`：横5/纵7球、向外裁剪候选、中心规则显式分开。`build_half_sensor.py` / `contact_sensor_v7.h`读取共享函数前后槽数组；本刀槽为空，不证明物理/特效身份。`half_disagreement_probe.py`是最后一刀固定pitch区分夹具；原件一律新路径，不能自动补抽。
- `contact_chain_report.py`：只导出归一帧、生命队列和叶类型等派生数值，不导出原生内存字节。
- `blade_only.py`、`attack_model_safe.py`、`model_blade_only.py`：接触未知、四帧明确排除接触；整组场地球到首次体积相交均清晰才计墨刃。没有限定路线不等于原生P=0。完整D4/接触规则/游戏全局最优保持未闭合。
- `query_blade_only.py`：0–3钩/全开大点/有限程序的限定查询；`--top-only`仍不是完整热图。`compute_blade_common.py`对9个固定常见敌态批算全起点；不是全部敌人×四向×四手速已完成。
- `calibration_plan_blade_only.py`是解析下界快速计划；达不到同分门就保留partial并失败，不生成伪完整计划。`calibration_plan_blade_bank.py`从完整查询选普通导航支持集合内top2，并同时公开全几何网格top2/排除数量，不偷换成原生全局最优。
- `duel_blade_only.py` / `batch_blade_only.py`：先普通摇杆微调，0.35u/自然满血门，原生接触不改机制。正式新216与资格检查/旧12完全分池；两次setup失败或同敌态两个正例都失败就停止后续发房，当前自建房自然收尾。当前仅一个限定正例资格检查通过；完整冻结/正式批次另见本轮notes，不据此宣称216已完成。

```sh
.venv/bin/python -m unittest tools.zipcaster_d4.test_contact_field tools.zipcaster_d4.test_contact_transform tools.zipcaster_d4.test_blade_halves tools.zipcaster_d4.test_blade_only tools.zipcaster_d4.test_blade_only_bound
.venv/bin/python -m tools.zipcaster_d4.query_blade_only --graph work/d4/graph-v2-Yunohana --enemy-index 637 --heading 2 --speed 40 --out work/d4/new-blade-only-query
```

只读调研/两半检验/资格检查记录：`notes/d4-contact-hypotheses-20261022.md`、`notes/d4-halves-20261022.md`。默认arena、policies、原存档及T1/S1不变。
