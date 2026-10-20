"""Write aggregate comparison documentation, never export game tables/traces."""
import json
import math
from collections import Counter

from .corpus import WORK
from .parameters import ROOT, sha256


def merged(rows, horizon, metric, statistic='mean'):
    values = [row['all_samples'][metric] for row in rows if row['horizon']==horizon]
    count = sum(v['samples'] for v in values)
    if statistic == 'rmse':
        return math.sqrt(sum(v['rmse']**2*v['samples'] for v in values)/count)
    return sum(v[statistic]*v['samples'] for v in values)/count


def document(baseline, final, motion, weapon, speed, corpus):
    before, after = baseline['results'], final['results']
    splits = Counter(g['split'] for g in corpus['games'])
    samples = sum(g['samples'] for g in corpus['games'])
    lines = ['# S1 保真度第二阶段对照（2026-10-20）', '',
        '本轮完成因果短时域评估、历史移动辨识、预扣/退款与受击时间区间校准，以及完整判定核心的批量运动/地面查询。原生一致性仍未签收；按要求在报告完成后停止。所有运行均为离线Python，没有启动游戏。', '',
        '## 评估口径与数据边界', '',
        f"- 语料{len(corpus['games'])}场有效非空会话、{samples:,}个唯一原生位置包；{splits['train']}训练、{splits['validation']}验证、{splits['test']}测试。T1作为整个测试家族留出，拟合/选择均不使用测试值。最终有效转移为训练{motion['split_segments']['train']:,}、验证{motion['split_segments']['validation']:,}、测试{motion['split_segments']['test']:,}。",
        '- 主报告固定T1第1轮三图；每隔N=30/60/120/300帧重置一次，连续预测随后N帧。死者/发射台及未知/过期形态锚点排除并计数。所有采样、窗口RMSE分布和窗口末端误差分别保存；末端指窗口内最后一个有效原生样本，不虚构整N帧末端测量。',
        '- 初始化仅取锚点时已到达的包；位置按过去两包速度传播包龄，武器阶段由过去输入估计。窗口内不使用原生真值纠正模型。未来包不可参与初始化。位置/HP/墨量/朝向/形态比较都使用该宿主独立原点和包采样时刻，重复包去重。',
        '- 原生世界墨图、投射物、精确武器/恢复阶段未知。仅在观察到真实潜墨时初始化脚下己墨近似。不能声称把未观测的全部游戏内部状态精确重置。',
        '- 与已签收原生适配器一致，乌贼contact=0为潜墨，4为非潜墨，5为空中。修复了第一阶段初始化的0/4误用；辨识也显式排除-1未知码。',
        '- 位置单位是原生世界单位；HP/墨量为0..1；角度误差为圆周最短距离（rad）。全局RMSE按采样数合并平方误差，不平均各图RMSE或P95。', '',
        '## 主指标：位置误差分布', '',
        '| 地图 | N | 有效窗口 | RMSE 原模型→本轮 | 本轮采样P95 | 本轮窗口RMSE P95 | 本轮末端P95 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for old, new in zip(before, after):
        assert (old['stage'],old['horizon'])==(new['stage'],new['horizon'])
        p, q = old['all_samples']['position'], new['all_samples']['position']
        lines.append(f"| {new['stage']} | {new['horizon']} | {new['counts']['windows']} | {p['rmse']:.4f} → {q['rmse']:.4f} | {q['p95']:.4f} | {new['window_rmse']['position']['p95']:.4f} | {new['endpoint_samples']['position']['p95']:.4f} |")
    lines += ['', '图1=Yunohana（温泉峡谷）、图2=District00、图3=Yagara。图2 N30/60略退化，仍原样报告，没有据测试集反向挑参。原始JSON另含水平/垂直误差及“窗口含移动输入”的分布，避免只给被静止样本稀释的单一均值。', '',
        '| N | 全图位置RMSE 原→本轮 | 下降比例 | 身体朝向MAE 原→本轮 | 相机yaw MAE 原→本轮 |',
        '| ---: | ---: | ---: | ---: | ---: |']
    for n in (30,60,120,300):
        a,b=merged(before,n,'position','rmse'),merged(after,n,'position','rmse')
        lines.append(f"| {n} | {a:.4f} → {b:.4f} | {100*(1-b/a):.1f}% | {merged(before,n,'heading'):.4f} → {merged(after,n,'heading'):.4f} | {merged(before,n,'yaw'):.4f} → {merged(after,n,'yaw'):.4f} |")
    lines += ['', '| N | 墨量MAE 原→本轮 | HP MAE 原→本轮 | 乌贼形态不一致率（本轮） | 潜墨不一致率（本轮） |',
              '| ---: | ---: | ---: | ---: | ---: |']
    for n in (30,60,120,300):
        lines.append(f"| {n} | {merged(before,n,'ink'):.5f} → {merged(after,n,'ink'):.5f} | {merged(before,n,'hp'):.5f} → {merged(after,n,'hp'):.5f} | {100*merged(after,n,'squid'):.2f}% | {100*merged(after,n,'submerged'):.2f}% |")
    lines += ['', 'HP没有跨时域一致改善；未知投射物/恢复阶段、ZL动作过渡及初始墨图仍限制主评估。形态只统计已知原生枚举，-1/NaN不补成布尔值；早期基线形态列未排除未知码，故不用于前后比较。不能以局部武器夹具改进替代这些残差。', '',
        '## 系统辨识与未辨识项', '',
        '| 模式 | 有效自由速度系数 | 加速 / 制动 | 轴死区 / 指数 | 验证选择 |',
        '| --- | ---: | ---: | ---: | --- |']
    for name,p in motion['modes'].items():
        lines.append(f"| {name} | {p['speed']:.6f} | {p['acceleration']:.4f} / {p['braking']:.4f} | {p['deadzone']:.2f} / {p['exponent']:.1f} | {'候选采纳' if motion['validation_selection'][name]['selected'] else '保留原先验'} |")
    c,j=motion['camera'],motion['jump']
    lines += ['',
        f"相机杆死区{c['stick_deadzone']:.2f}、杆yaw系数{c['stick_gain']:.6f}、gyro yaw系数{c['gyro_gain']:.6f}、pitch系数{c['pitch_gain']:.6f}。有效重力{j['gravity']:.6f}、跳跃冲量{j['jump_speed']:.6f}，由{j['gravity_samples']}个有效空中样本和{j.get('launch_segments',0)}个地→空B边沿估计。这些系数对应当前记录分布；未提取的游戏默认值仍保留未知。", '',
        '- 自由速度用稳定杆量桶的85%上包络拟合，避免堵墙/停杆主导最大速度；加速/制动用短段位移损失拟合。验证集逐模式拒绝退化候选，蓄力/非潜墨乌贼保留先验。',
        '- 大部分旧对局没有冻结AP配置，不能拆出完整装备曲线；有历史冻结config的对局按角色映射读取，只读配置而不读策略源码。己墨游速激励不足以同时识别死区和最大速度，最大游速保留A2独立先验。',
        '- 人形脚下己墨/敌墨/无墨不可由现有形态包可靠区分，保留unknown，不把速度慢自动标成敌墨。',
        '- 支撑坡面与墙分离，沿用A4法线.7/台阶.2阈值，修复脚球碰支撑面即堵住的错误。记录能给出dy/dXZ分布，但稀疏包不能可靠区分一段坡和一次台阶，未声称拟合出材质/台阶上限。', '',
        '## 武器：独立夹具与校准重算', '',
        '| 近距combat场景（独立验证） | 首伤相对首次原生包 原→本轮 | 超出原生时间区间 | 射手墨量MAE |',
        '| --- | ---: | ---: | ---: |']
    for old_delay,row in zip((-7,-7,-5),weapon['validation']):
        lines.append(f"| {row['case']} | {old_delay} → {row['first_sample_delay']}帧 | {row['interval_violation']}帧 | {row['ink']['mean']:.8f} |")
    timing=weapon['timing']
    lines += ['',
        f"用另一射程房5个命中样本的区间拟合对端HP生效延迟：5和6帧均满足训练区间，选择较小5；9个命中/未中分类保留。这里建模的是观察到的peer HP生效，不能分解物理命中、网络与编码采样延迟，没有移动原生时间戳。", '',
        f"预扣/退款来自RomFS 5/20内部计数、.035/.117成本及首帧边界。时序记录66个唯一样本的墨量MAE由{timing['legacy']['mean']:.6f}降至{timing['fitted']['mean']:.9f}，最大差{timing['fitted']['maximum']:.9f}。该时序记录参与结构构建，是校准重算；上表combat的墨量才是独立房验证。", '',
        'A1接触坐标起点候选将slash局部偏移相对muzzle而非脚底，两次脚本重建均产生20+35=55直接伤害；总损血56 vs原生55，保留1点持续敌墨残差。A1参与接触起点校准，真实骨骼关节变换尚未观测，不能当独立证明。', '',
        '## 批量向量化与CPU吞吐', '',
        '计时执行完整判定核心：NumPy向量化运动与按空间桶分组的地面射线；接近墙时回退同一标量扫掠；武器、涂地和伤害保留原实现。每环境帧代表一局双方各前进1/60游戏秒。', '',
        '| 负载 | CPU worker | 实现 | 每worker局数 / 每局帧数 | 计算环境帧/秒 | 含进程启动环境帧/秒 |',
        '| --- | ---: | --- | ---: | ---: | ---: |']
    for row in speed['single_worker']:
        lines.append(f"| {row['workload']} | 1 | {row['kind']} | {row['games']} / {row['frames_per_game']} | {row['environment_frames_per_second']:.1f} | — |")
    for row in speed['multi_worker']:
        lines.append(f"| {row['workload']} | {row['workers']} | vector | {row['games_per_worker']} / {row['frames_per_game']} | {row['compute_environment_frames_per_second']:.1f} | {row['end_to_end_environment_frames_per_second']:.1f} |")
    lines += ['', '单worker为单Python进程，BLAS线程设1，未做OS核绑定；双worker上限2，未扩大到占满机器。计时循环不含策略子进程、可见性投影与序列化，初始化时间另保存在JSON。CPU性能仍可能受另一个A7/A8会话影响。', '',
        '标量/批量最终状态容差1e-8，伤害和击倒事件数一致；回归还逐帧比较随机移动、跳跃、实际接触/墨刃伤害、墨量与形态。三图短时域由同一批量核心重跑。', '',
        '## 复现与证据', '',
        '```sh', '.venv/bin/python -m sim.corpus', '.venv/bin/python -m sim.identify',
        '.venv/bin/python -m sim.calibrate_weapon', '.venv/bin/python -m sim.horizon  # 原模型基线，较慢',
        '.venv/bin/python -m sim.horizon --model work/sim/fidelity/motion.json --weapon-model work/sim/fidelity/weapon.json --vector-batch 16 --out work/sim/fidelity/horizon-final.json',
        '.venv/bin/python -m sim.speed --games 16 --frames 600 --out work/sim/fidelity/speed-final.json',
        '.venv/bin/python -m sim.fidelity_report',
        '.venv/bin/python -m unittest sim.test_core sim.test_replay sim.test_horizon sim.test_motion sim.test_weapon sim.test_batch -v', '```', '',
        '原件/冻结config/缓存来源哈希在corpus及每个trace JSON；模型含语料及拟合源码哈希，最终短时域含启动时sim源码哈希，速度报告绑定模型哈希。本报告汇总与原始逐窗口分布仅由work/sim/fidelity派生，提交不含原生轨迹、RomFS、地图或游戏画面。', '',
        '## 次指标：第一阶段整局开环（历史保留，非本轮主指标）', '',
        '| 图 | 第一阶段位置RMSE（双方） | 原生最终涂地% | 第一阶段模拟涂地% |',
        '| --- | ---: | ---: | ---: |',
        '| 1 | 62.129 / 50.135 | 12.000 / 11.700 | .753 / .441 |',
        '| 2 | 68.797 / 39.076 | 14.150 / 7.650 | 2.974 / 5.210 |',
        '| 3 | 54.746 / 50.123 | 4.300 / 9.700 | 1.317 / .509 |', '',
        '这些为71b1a00阶段历史开环结果（初始速度/墨图未知、未绑定旧配装），保留用于说明误差累积，没有用新短时域改善推断整局胜率或最终占地已可信。', '',
        '## 未完成的保真义务与停止边界', '',
        '三图位置均非全时域一致改善；HP和形态还存在残差。完整原生墨图、关节变换、装备曲线、精确输入/武器相位和动态碰撞仍缺少证据；乌贼滑/墙蓄跳/冲刺斩/炸弹/触手喷射效果没有在本轮扩展。实机清单保留在notes/PROGRESS.md，等待A7/A8空档统一调度。本轮完成离线改进与报告后停止，不启动原生校准。', '']
    return '\n'.join(lines)


def main():
    names=('horizon-baseline.json','horizon-final.json','motion.json','weapon-comparison.json','speed-final.json','corpus.json')
    data=[json.loads((WORK/name).read_text()) for name in names]
    baseline,final,motion,weapon,speed,corpus=data
    if final['model'] != motion or speed['models']['motion.json'] != sha256(WORK/'motion.json'):
        raise RuntimeError('stale evaluation/benchmark model; reproduce final outputs first')
    if motion['corpus_sha256'] != sha256(WORK/'corpus.json'):
        raise RuntimeError('motion model references another corpus version')
    if speed['models']['weapon.json'] != sha256(WORK/'weapon.json'):
        raise RuntimeError('stale weapon benchmark')
    weapon_profile=json.loads((WORK/'weapon.json').read_text())
    if final['weapon_model'] != weapon_profile or weapon['model'] != weapon_profile:
        raise RuntimeError('stale weapon comparison/evaluation')
    text=document(*data)
    (WORK/'COMPARISON.md').write_text(text)
    evidence={name:sha256(WORK/name) for name in names}
    (WORK/'evidence.json').write_text(json.dumps(dict(schema='sim.fidelity.evidence.v2',sources=evidence,
        code={p.name:sha256(p) for p in (ROOT/'sim').glob('*.py')}),indent=2)+'\n')
    print(WORK/'COMPARISON.md')


if __name__ == '__main__':
    main()
