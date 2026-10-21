# D2 Zipcaster 测量工具

独立的协调方夹具和离线分析，不是策略实现，不接入正式擂台。当前 **D2 部分完成、遇到观测卡点；没有全项签收**。数值与边界见 [研究报告](../../notes/d2-20261021.md) 和 [机器可读索引](../../notes/d2-20261021.json)。

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

继续前应先增加只读原生观测：实际hook命中点/面、special action/attack-ready状态、armor字段。两次高台满蓄有墨耗但无伤害，不能从动画/瞄准推断命中。天花板实际终点不符，不能宣称可挂或不可挂。飞行R2房间曾在剩约23.9秒触发RL_STALL，保留保护和失败原件，先最小重放诊断。不要把静态Top5写成已验证攻略，不自动转D3或恢复T1/S1。
