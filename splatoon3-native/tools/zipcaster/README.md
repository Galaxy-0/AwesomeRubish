# D2 Zipcaster 测量工具

独立的协调方夹具和离线分析，不是策略实现，不接入正式擂台。当前 **D2B只读传感与侧角高台70+35已通过；实体天花板摆位和护甲倍率仍未定，没有D2全项签收**。最新见 [B报告](../../notes/d2b-20261021.md) 和 [B机器索引](../../notes/d2b-20261021.json)；首轮历史见 [研究报告](../../notes/d2-20261021.md) 和 [机器索引](../../notes/d2-20261021.json)。

## 文件

- `parameters.py`：读取本地11.3.0稀疏参数表，选取数字与源/条目SHA；不把Mission表当Versus缺省值。
- `probe.py`：复用A6原生Lab及版本校验，首轮R保持/松开探索。只对本夹具actor0注入测试meter。
- `serve.py`：两进程原生房间，JSONL输入计划、逐步原包和命令前后读数；EOF不推进fixed60。受控actor通过普通按键行动，除既有测试特殊量补充外不写游戏状态。
- `plans/*.jsonl`：本轮实际执行的控制计划，包含失败的高台方案，**不代表每条技能成功**。`combat-v3`包含20/21帧和中路连招；`hooks`为同一大墙距离对照；`armor`含飞行/到达输入与完整空耗生命周期；`death-long`使用full；`defense-full-v3`使用full；其余infinite。
- `surfaces.py` / `analyze_maps.py`：读取静态碰撞与材料，定向分组挂墙候选，计算视域、目标距离、接近暴露和条件连招。射线不是原生飞索体积查询。
- `measure.py`：从所有本地尝试（包括无有效测量的失败）生成数值归约和证据SHA。
- `export.py`：紧凑派生图层和 `inklab.trace.v1`，只记录实际输入边沿/观测，不补命中事件或缺失轨迹。
- `report.py` / `check.py`：生成可提交的数值证据索引，以及离线来源/导出/判据审计。

## 离线重建（不会启动游戏）

在项目根目录执行，需已有本地提取数据、D1派生数据和本轮原始记录：

```sh
.venv/bin/python tools/zipcaster/parameters.py
.venv/bin/python tools/zipcaster/analyze_maps.py
.venv/bin/python tools/zipcaster/measure.py
.venv/bin/python tools/zipcaster/export.py --layers work/d2/map-analysis-full.json \
  --clip discovery:R-tap --clip hooks:range34 --clip combat-v3:mc \
  --clip high-target:ha --clip armor:idle
.venv/bin/python tools/zipcaster/report.py
.venv/bin/python tools/zipcaster/check.py
```

`work/d2/map-analysis-full.json`约30MB，完整研究数据留本机；`showcase/data/zipcaster-layer.json`约3.9MB；五段trace约76KB，均Git ignored。未修改D1页面、未重新发布预览。数值JSON只含实验结果、参数、计划、来源路径/哈希，没有OBJ内容或图片。`notes/d2-20261021.json`不能替代本地原始证据。

## 原生复现（只在获准测量时执行）

最多3房；每房两端及独立本机空气服务。不要全局export `DM_TEST_SPECIAL`。宿主须为经身份校验的 `test_only/special_meter` 派生版本，默认 `work/a8/dmhost-arena-special-v15`，模块 `work/a7/patched-seeds-v16`。不重编或替换默认宿主。

```sh
mkdir -p work/d2
.venv/bin/python tools/zipcaster/serve.py --name replay-combat \
  --commands work/d2/replay-combat.commands.jsonl
```

等到输出 `D2_READY` 后，在另一个终端把**源计划**追加到已创建的全新空队列：

```sh
cat tools/zipcaster/plans/combat-v3.jsonl >> work/d2/replay-combat.commands.jsonl
```

队列必须不存在才可启动serve；不要把已有原件当输出。`--meter full`只做一次初始补满；`infinite`在当前特殊结束后再补满，不延长当前一轮。读取actor的native own字段，夹具可知道靶位置，这不是向策略开放真值。地图默认温泉，`--stage 2|3`切图但当前计划路线未跨图验证。

固定60Hz由A6 Lab检查原生时间/推进；完整像素渲染。每次step记录输入、两端原包、native frame及position sample frame。两个进程frame原点不同，分析与trace显式保留映射。默认双方均57AP快速超级跳跃，不能把回程/复活结果冒称零配装通则。

长时间暂停测量时，**只在测量子进程环境里省略**通用 `DM_WATCH` / `DM_WATCH_STALL`；crash.c把值0解释为15秒默认值，并非关闭。原生active-present停帧保护仍120秒。标准对局环境/拒绝测试开关的逻辑未改。`AssertionError`记录为fixture_failed，后续命令可继续，但依赖失败站位的科学试验无效；原生异常则整房清理。每房 `result.passed`仅表示driver正常结束，`full_d2_passed`始终false。

## 数据与下一步

三图输出818 / 1327 / 1035个定向静态候选；“常驻点”是D1命名区域/伏击候选代理，不是敌人行为统计。垂直面带宽、入射角和附着偏移都是采样假设。参数35作为保守眼点半径；原生大墙眼点成功约37.40、失败38.25的结果说明不能直接把相机射线当飞索枪口射程。

首轮曾缺少实际hook命中点/面、special action和armor观测；B已补充，详见下节。两次旧高台满蓄有墨耗无伤害，不能从动画/瞄准推断命中；新侧角落格栅方案实际70+35通过。天花板仍不能宣称普遍可挂或不可挂。飞行R2房间曾触发RL_STALL，保留保护和失败原件；按本轮用户指示不追此支。不要把静态Top5写成已验证攻略，不自动转D3或恢复T1/S1。

## D2B：只读原生证据工具

- `build_sensors.py`：从版本绑定special测量宿主派生独立host/modules，全部输出要求新建在`work/`，禁止覆盖默认宿主。原父源码／宿主／模块前后SHA校验；新增观察门46/47仅在私有重写模块。46定位原生更新入口；47候选入口未产生live样本，实际对象发现采用受保护的vtable+owner只读扫描。
- `sensor.h`：读取受控own Player对应SuperHook、actor矩阵、PlayerArmor和PlayerCollision；native帧4间隔私有快照。首次有界VM扫描≤64MiB，缓存须再次校验vtable与owner。只读；既有meter测试写入保持独立。`hook_bullet`是早期诊断名称，未证明是实际弹体，不能使用其位置作锚点。
- `sensor_lab.py`：复用原D2夹具，只给本次进程设置传感开关，不改变正式host选项或policy协议。
- `inspect_native.py`：本机NSO解压、Build ID／类型／观察门原指令验证，私有image只能输出到`work/`；不要提交image、静态指令输出或内存快照。
- `decode_sensors.py`：解码原生快照与RTTI；字段名保留candidate语义。必须给本地image才能验证关联组件类型并导出armor字段。
- `sensor_evidence.py`：同process/native frame归并；Shot仅为tip，PreAttack/Attack+matrix才为bind witness；Wait残留点无效。3×4矩阵变换位置，法线不加平移，actor ID不当静态face index。armor／collision输出原始值，不冒充减伤倍率。
- `report_sensors.py` / `check_sensors.py`：从本轮关闭后的原件归约数值JSON、来源SHA和失败前置，审计真实HP、armor、矩阵、stale字段、运行时保护及D1 trace。没有启动游戏的副作用。

重建私有传感宿主（需要用户授权运行时才执行；当前任务已结束）：

```sh
.venv/bin/python tools/zipcaster/build_sensors.py --out work/d2b/rebuild-new
.venv/bin/python tools/zipcaster/sensor_lab.py --name sensors-replay \
  --commands work/d2/sensors-replay.commands.jsonl \
  --host work/d2b/rebuild-new/dmhost-sensors --patched work/d2b/rebuild-new/modules
```

另一个终端等`D2_READY`后，将`plans/sensor-b2-world.jsonl`追加到新空队列即可复现侧角高台方案。`sensor-b1-survey`与`sensor-b2-ceiling`包括失败站位，是证据重放，不是保证合法的夹具。不得同时超过3房；本轮峰值2房，现已全部关闭。

离线验证／归约（不启动游戏）：

```sh
.venv/bin/python tools/zipcaster/inspect_native.py --image work/d2b/reconstructed-main.bin
.venv/bin/python tools/zipcaster/decode_sensors.py \
  --session work/tests/m6-2p-20261021-143014-022434 \
  --out work/d2b/b2-armor-final --image work/d2b/reconstructed-main.bin
.venv/bin/python tools/zipcaster/sensor_evidence.py \
  --source work/d2b/b2-armor-final/sensors.jsonl --out work/d2b/b2-armor-final/evidence.jsonl
.venv/bin/python tools/zipcaster/report_sensors.py
.venv/bin/python tools/zipcaster/check_sensors.py
.venv/bin/python tools/zipcaster/check.py
```

`report_sensors.py`使用报告中指定的五个历史关闭run和四份decode目录，不能在仍运行的日志上生成最终哈希。其它decode目录以JSON所列session同法生成。新高台D1通用trace保存在`work/d2b/traces/high-side.json`，未修改旧`showcase/data/zipcaster-traces.json`或已发布页面。
