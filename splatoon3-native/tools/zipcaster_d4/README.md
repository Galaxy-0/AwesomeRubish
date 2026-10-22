# D4：给定敌情，反推全图开大点

输入敌人位置/固定世界朝向，查询地面开大点。旧D3-R均匀敌人先验排名不再作主结论。本轮有界停止：近身140遗漏和高差反例两轮仍未闭合，正式三图重复/全量模型未签收。浏览器亮暗/手机原型自查已完成，不能替代机制验证；见`notes/d4-blocker-20261022.md/.json`。下列搜索入口只用于复查旧远端核心代理，不宜继续扩大为最优推荐。测试特殊量/直接瞄准仅测量夹具，默认/正式对战禁用。

当前入口：

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
