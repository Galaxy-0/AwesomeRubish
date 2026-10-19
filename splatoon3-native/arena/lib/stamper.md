# A6 工作刮水刀技能

8000 / Splatana Stamper；普通游戏输入，不改武器规则。T1 冻结期间只在
`arena/lib_a6/` 新增代码；协调器退出且36项冻结核对全通过后，已合入本目录。
目前原生调研、逐项支持状态见 `notes/PROGRESS.md`，组件测试成功不能代替实机证据。

`stamper.py` 只依赖公共 `skills.py` 和 Python 标准库。策略只能传入
`arena.policy.v1` 的白名单观测，不能传裁判 HP、原生内存、宿主日志或敌人真值。

```python
from stamper import charge_slash, emerge_charge, light_combo, PredictiveAim

# 策略 config.toml 声明 step_frames = 1，最短松键边界需要一帧。
plan = charge_slash(obs, hold_frames=24, dash=True, after=(-1., 0.))
result = plan.tick(obs)
action = result.action
# 每帧重调 tick。直接驱动环境时一次最多执行 result.frames 帧。
# result.done=True 后中立，检查 status == 'complete'。
```

- `charge_slash(obs, hold_frames, dash=False, after=(x,y), after_frames=14)`：ZR按住、松开、恢复期移动。dash 使用前推满杆跨过释放边界。
- `emerge_charge(...)`：必须从实际己墨潜游开始，第一帧释放ZL并按ZR；与 `Skills.swim_to` 接近组合。**不支持潜墨保存蓄力**，原生 `IsEnableChargeKeep=false`。
- `light_combo(obs, count=3, period=30, after=(x,y))`：单帧轻挥、松键间隔、移动。26帧输入周期在实机吞掉第二刀，30帧三次成本.156已验证；移动是相机坐标，向量需在单位圆内。
- `squid_roll(obs, direction=(0,-1), approach_frames=30)`：己墨前游后反向杆+B，ZL保持。`squid_surge(obs, charge_frames=60)`：先在己墨墙建立攀爬，再停左杆、ZL+B蓄跳后松B前推；墙上状态不能用地面潜墨标记代替。动作是否已通过原生识别必须看支持表，不能把普通跳跃计为成功。
- `burst_bomb(obs)`：R按住后松开投快速炸弹，起始至少.45墨量。
- `zipcaster(obs)`：**实验候选，挂钩位移 unsupported**。自身特殊明确满槽才RS，随后尝试R；未知量/不足拒绝。普通涂地积满后的RS已实测启动并消耗特殊量，但60帧R未产生水平位移，不能声称钩索已验证。`own.special` 仅来自自身新鲜HUD反馈。
- `PredictiveAim().aim(obs, enemy_id, fast=True)`：只由连续、新鲜、当前可见采样估速度；遮挡、潜墨隐藏、换局、瞬移会清空速度。`target` 为预测世界坐标，`velocity` 单位为世界单位/present。预测包括当前可见样本年龄、出刀等待和飞行时间；弹速/出刀等待可配置，默认对应满蓄墨刃的近似参数。
- `FastTurn().aim(obs, target)`：以自身反馈校准虚拟控制器Z轴，粗转右杆+陀螺仪、近处停右杆作比例细调。首次6present短脉冲+8present中立等待，自动学习方向/增益；无响应回退已验证的右杆方法。返回Result，**每次只执行1present**；初次校准成本包含在实机用时中。
- `fast_turn(obs, target)`：兼容的无状态大偏差满右杆闭环，返回与基础aim_at相同的SkillResult，同样只执行1present。连续调用与“1输入+3中立”配方的到位时间不同，具体比较见PROGRESS。

所有宏会在自身死亡/过期、换局或调用方跳过输入边界时中立停止。
`complete` 仅表示输入序列正确执行，不表示命中、乌贼滑身份或钩索附着已确认。
预测默认等待6帧对应已经蓄好的松键出刀；若瞄准后才开始蓄力，应把
`windup_frames` 设为蓄力帧数+6（参考策略如此设置）。
预测的fast模式使用自身独立的FastTurn实例，首次也包含上述校准；
普通模式沿用A4的aim_at。
`stamper_data.py` 提供版本标识、21/26帧最短观测、保守24/30默认、
35/70伤害、实测射程区间及副/特殊配置；参数伤害与原生伤害分列。

## 原生支持范围

版本11.3.0、fixed60、温泉峡谷指定夹具；世界单位不是米。
每项原始证据及SHA256由 `arena/results/a6-acceptance.json` 索引，详细实验与失败留在PROGRESS。

| 操作 | 当前状态 | 原生证据与边界 |
| --- | --- | --- |
| 蓄力斩 | supported | 20帧35伤害、21帧70；默认保守24 |
| 潜游接近后出墨蓄斩 | supported | 出墨输入至满蓄释放最短观测26；实际出墨反馈至释放25–26；默认30 |
| 潜墨保持蓄力 | unsupported by design | IsEnableChargeKeep=false；下潜会取消蓄力 |
| 冲刺斩 | supported | 满HP靶倒下，释放附近至结束位移3.37；未隔离140接触伤害 |
| 轻挥连斩及斩后位移 | supported | 30帧周期三挥成本.156并有位移；26帧吞第二挥 |
| 乌贼滑 | supported motion witness | 同速反向+B比前向跳/反向不跳有额外跃高及反向位移；不声称减伤或内部枚举 |
| 乌贼冲刺 | supported motion witness | 停杆墙蓄60后释放跃升5.25，对照B1为3.03；最短蓄跳时间未测 |
| 快速炸弹 | supported | R按/松，成本.45；6.17距离总伤害60（25+35包） |
| 触手喷射 | activation verified; hook unsupported | 普通涂地满槽后RS启动并消耗特殊量；当前R钩索候选水平位移0 |
| 预判瞄准 | supported camera lead | 51条非零速度样本，最小原生相机预测方向误差.0288rad；不表示全部弹丸命中 |
| 快速转向 | supported | 冷启动180度87帧，含14帧校准；匹配普通右杆对照176帧 |

轻挥/满蓄墨刃伤害分别35/70；接触伤害20/140仅为参数，未各自独立测量。
平地站立人形靶射程：轻挥最远命中18.7897、最近未中19.5619；满蓄21.7824/22.5553。
这些是指定角度、站姿和采样条件下的区间，不作为所有高度/姿态的精确最大射程。

## 熟练度基准

macOS长批次可用 `caffeinate -i <命令>` 临时防止空闲休眠；这不会修改系统电源配置。
机器休眠后墙钟看门狗可能中止宿主，受影响整房必须重跑。

每个命令只启动一个双端房间，按顺序执行。策略通过与正式擂台相同的
文件/网络隔离运行，目标HP只供裁判评分；不需要阅读另一份策略代码。

```sh
.venv/bin/python tests/benchmark_a6.py --policy arena/proficiency-reference --scenario stationary --out work/a6/reference-stationary.json
.venv/bin/python tests/benchmark_a6.py --policy arena/proficiency-reference --scenario lateral --out work/a6/reference-lateral.json
.venv/bin/python tests/benchmark_a6.py --policy arena/proficiency-reference --scenario approach --out work/a6/reference-approach.json
.venv/bin/python -m arena.proficiency --merge work/a6/reference-stationary.json work/a6/reference-lateral.json work/a6/reference-approach.json --out arena/results/proficiency/proficiency-reference.json
```

若九个横移窗口及布靶超过原生180秒局时长，保留失败房的诊断，按距离顺序重跑；
不能将未完成房间的试验并入正式分母。相同代码、配装及完整覆盖仍可合表：

```sh
.venv/bin/python tests/benchmark_a6.py --policy arena/policies/alpha --scenario lateral --distances 6 12 --out work/a6/alpha-lateral-6-12.json
.venv/bin/python tests/benchmark_a6.py --policy arena/policies/alpha --scenario lateral --distances 18 --out work/a6/alpha-lateral-18.json
# 与同版本的 stationary、approach 表一起传给 --merge，保留每距离3次。
```

替换 `--policy` 可以跑任意符合策略配置的目录。输出JSON及同名Markdown表。
静止靶240present窗口；横移靶约6/12/18单位、各90present窗口，记录实际距离。
JSON还保留窗口内距离最小/最大值；静止靶中立输入，保留原生击退。
反应/击倒帧以首次采到原生反馈为界，受原生包/HUD采样粒度影响。
每个窗口新建策略子进程，因此包含该窗口的策略冷启动/校准成本；布靶导航和预对准不计入窗口。
静止/横移默认每项/每距离3次（`--repeats 1..3`），接近项因单局铺道预算默认1次；
分母明确，不由单次结果推断稳定胜率。接近项从目标反向+B那帧开始计反应，
此前30帧助跑为夹具准备；须通过同速前向跳/反向不跳/反向+B的原生对照校准，
并在每次试验受到任何伤害前观察到额外跃高和反向位移，才计作滑行接近。
无法建立运动证据时保留诊断反应/击倒记录，该项为unsupported并排除分数；
不由按键、未经命名的网络字段或伤害击退认定滑行动作，不声称验证减伤。
训练夹具固定射手平移，屏蔽R/RS/B/Y，只保留相机、ZR主武器与ZL回墨；
原策略输出和实际执行输入都留档，避免把冲近/副特殊伤害混入瞄准成绩。
分数定义在JSON中，只有相同覆盖/距离/时间/配装的表可直接比较。
未知/unsupported不补零、不进入均分；未击倒的时间保留null和右截尾。
横移“命中率”是**测试窗口命中率**，不提供无法归因的逐发弹丸命中率。

## 自动门禁

特殊量测试使用独立宿主，构建及单房验证命令：

```sh
.venv/bin/python tools/build_a6_test_host.py
caffeinate -i .venv/bin/python tests/probe_a6_test_special.py
```

输出为 `work/a6/dmhost-test-special`，不重编或替换默认dmhost。
只有该测试构建启用 `DM_TEST_SPECIAL=full|infinite`：full在受控局开始
填满一次，infinite在特殊实际剩余计时归零后补满。开关修改活Player的
规范编码字段，沿用游戏自身满槽写法；不写网络观测/HUD副本，不保存到存档。
验证脚本在同一个房间给两个座位分别设置full/infinite，全部控制输入为
中立或单帧RS，检查初始满槽、消耗和第二次启动。其它测试驱动也必须显式
选用该另路径可执行文件及对应开关。普通擂台协调器发现非空
`DM_TEST_SPECIAL` 即在开局前拒绝；本轮39项手法表均使用原默认宿主和自然状态。

`bash tests/run_all.sh --milestone a6 --components-only` 可在T1冻结期运行，
明确输出 `full_a6_passed=false`。完整 `--milestone a6` 读取
`arena/results/a6-acceptance.json`（可用 `--evidence PATH` 指定），重新运行组件/
实际策略沙箱/统计反例测试，并按SHA256核对原生实验、支持或unsupported
证据、熟练度表与A1–A5回归，另核验测试宿主full/infinite的原始中立/RS输入、
自然消耗、补满次数、宿主/源码/启动模式哈希，检查T1退出和公共库已合入。
缺少任何必要证据均失败，不会调用默认dmhost的make目标。

T1退出后可用 `caffeinate -i .venv/bin/python tests/regress_a6.py` 串行重跑A1–A4原生门禁、
严格复核已签收A5的70局，再通过新协调器跑2局换边。它只构建独立C测试输出，
不会重编默认dmhost；新2局不冒称新跑70局。完整A6入口核对这些已完成记录及其哈希。
