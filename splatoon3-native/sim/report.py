"""Reproduce S1 comparison from local records only; all raw outputs in work/."""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import time

import numpy as np

from .engine import Assumptions, Simulator, neutral
from .parameters import Parameters, ROOT, sha256
from .replay import a6_case, initialize, provenance, read_jsonl, tournament
from .terrain import Terrain


def compact(report):
    result = {k: v for k, v in report.items() if k != 'sampled_curves'}
    result['players'] = {}
    for key, values in report['players'].items():
        result['players'][key] = {k: v for k, v in values.items() if k not in (
            'native_direct_damage_samples', 'simulated_damage', 'native_knockdown_sample_frames',
            'simulated_knockdown_frames')}
        result['players'][key]['damage_event_counts_native_sim'] = [
            len(values['native_direct_damage_samples']), len(values['simulated_damage'])]
        result['players'][key]['knockdown_counts_native_sim'] = [
            len(values['native_knockdown_sample_frames']), len(values['simulated_knockdown_frames'])]
    return result


def a1(parameters, terrain, weapon_model=None):
    path = ROOT / 'work/tests/a4-stage1-20261018-231611-601829/result.json'
    sources = provenance([path, path.with_name('steps.jsonl')])
    data = json.loads(path.read_text())
    rows = read_jsonl(path.with_name('steps.jsonl'))
    reports = []
    for label, expected in zip(('damage-continuous', 'damage-paused'), data['damage']):
        index = next(i for i, row in enumerate(rows) if row['label'] == label)
        before = dict(frame=0, infos=rows[index-1]['infos'])
        origins = {k: v['frame'] for k, v in before['infos'].items()}
        env = Simulator(parameters=parameters, terrain=terrain, duration_frames=60, weapon_model=weapon_model)
        initialize(env, before, origins, own_ink_fixture=True)
        for index, count in enumerate((1, 7, 7, 15, 15, 15)):
            a = neutral()
            if index == 0:
                a['buttons'][0] = 1
            env.step({'player_0': a, 'player_1': neutral()}, count, observe=False)
        reports.append(dict(label=label, native_loss=expected['loss'], simulated_loss=1-env.players[1].hp,
                            simulated_direct_damage=sum(v['amount'] for v in env.events if v['kind'] == 'damage'),
                            script_frames=env.frame, native_hud_seconds=expected['hud_seconds']))
    return dict(kind='A1 reconstructed script / scalar comparison', cases=reports,
                sources=sources,
                limitation='Legacy steps do not store actions. Script 1+7+7+15+15+15 follows accepted PROGRESS; '
                           'this is not a recorded-input replay. Pause consumes no sim time.')


def a2(parameters, terrain):
    path = ROOT / 'work/tests/a2-20261018-193938-145424/result.json'
    sources = provenance([path])
    data = json.loads(path.read_text())
    reports = []
    for round_ in data['rounds']:
        env = Simulator(parameters=parameters, terrain=terrain, loadouts=round_['loadouts'], duration_frames=3000)
        for p in env.players:
            p.pitch = .9
        counts, costs = [0, 0], [[], []]
        dry = [False, False]
        for _ in range(40):
            actions = {f'player_{i}': neutral() for i in range(2)}
            before = [p.ink for p in env.players]
            for i in range(2):
                actions[f'player_{i}']['buttons'][0] = int(not dry[i])
            env.step(actions, 1, observe=False)
            env.step({f'player_{i}': neutral() for i in range(2)}, 29, observe=False)
            for i, p in enumerate(env.players):
                if not dry[i]:
                    if any(v['kind'] == 'dry' and v['player'] == i for v in env.events):
                        dry[i] = True
                    else:
                        counts[i] += 1
                        costs[i].append(before[i] - p.ink)
            if all(dry):
                break
        env.reset()
        first = round_['swim']['trajectory'][0]['infos']
        starts = []
        for i, p in enumerate(env.players):
            info = first[f'player_{i}']
            p.position = np.array(info['position'], float)
            p.yaw = p.heading = info['heading']
            p.squid = p.submerged = True
            starts.append(p.position.copy())
            direction = np.array([math.sin(p.yaw), 0., math.cos(p.yaw)])
            for distance in np.arange(-2, 13, .5):
                env.paint.disk(p.position + direction * distance, 1.5, i)
        crossings = [{}, {}]
        previous_d = [0., 0.]
        for frame in range(1, 121):
            actions = {f'player_{i}': neutral() for i in range(2)}
            for i in range(2):
                actions[f'player_{i}']['buttons'][1] = 1
                actions[f'player_{i}']['sticks'][1] = float(9 not in crossings[i])
            env.step(actions, observe=False)
            for i, p in enumerate(env.players):
                d = float(np.linalg.norm((p.position-starts[i])[[0, 2]]))
                for threshold in (3, 9):
                    if threshold not in crossings[i] and previous_d[i] < threshold <= d:
                        crossings[i][threshold] = frame - 1 + (threshold-previous_d[i]) / (d-previous_d[i])
                previous_d[i] = d
        sim_frames = [c[9]-c[3] if 3 in c and 9 in c else None for c in crossings]
        native_frames = [round_['swim']['frames'][f'player_{i}'] for i in range(2)]
        native_cost = [float(np.median(round_['air_slashes']['costs'][f'player_{i}'][:10])) for i in range(2)]
        # Full-cost counts, not the two native tail deductions (old 21/33).
        native_counts = []
        for i in range(2):
            key = f'player_{i}'
            history = round_['air_slashes']['history']
            nominal = float(np.median([v['losses'][key] for v in history[:3]]))
            count = 0
            for row in history:
                if row['before'][key] < nominal * .999:
                    break
                if abs(row['losses'][key] - nominal) > .002:
                    raise ValueError('native air-swing history has unexpected recovery/cadence')
                count += 1
            else:
                raise ValueError('native history ends before first insufficient remainder')
            native_counts.append(count)
        reports.append(dict(swapped=round_['swapped'], native_full_cost_counts=native_counts,
                            simulated_full_cost_counts=counts, native_cost=native_cost,
                            simulated_cost=[float(np.median(v)) for v in costs],
                            native_swim_frames=native_frames, simulated_swim_frames=sim_frames))
    return dict(kind='A2 reconstructed script / calibration anchors', rounds=reports,
                sources=sources,
                limitation='AP19 speed and AP38 ink are calibration inputs, not held-out validation. '
                           'Trajectory record has no actions/view; reconstruct full-forward ZL per accepted fixture. '
                           'Route is seeded own ink; native paint unavailable.')


def benchmark(parameters, terrains):
    results = []
    for stage, terrain in terrains.items():
        env = Simulator(stage, parameters=parameters, terrain=terrain, duration_frames=600)
        actions = {f'player_{i}': neutral() for i in range(2)}
        start = time.perf_counter()
        env.step(actions, 600, observe=False)
        elapsed = time.perf_counter() - start
        results.append(dict(stage=stage, frames=600, wall_seconds=elapsed,
                            frames_per_second=600/elapsed, workload='idle core; no policy/observations'))
    return results


def markdown(report):
    lines = ['# S1 核心机制与历史同输入对照（2026-10-20）', '',
             '核心模拟已完成；原生一致性尚未达到可用于策略强弱判断的程度。全部实验为本机历史记录读取和 Python 模拟，没有启动游戏。', '',
             '## 方法与证据范围', '',
             '- A6：三个已完成伤害场景各自从攻击前一次初始化，按原记录动作连续步进；不逐帧纠正模拟状态。',
             '- T1：第1轮三图各一局，从双方首次共同落地记录开始，一直执行到双方原生计时归零；省略发射台飞行。记录双方全部输入，不调用策略重新决策。',
             '- 各宿主独立以 `info.frame - common_frame` 对齐时间，再按自身 `position_sample_frame` 计算轨迹/HP/墨量误差，重复包不重复计样本。初始化样本可能落后1–4帧，速度/武器中间态未知并置零。',
             '- A1/A2旧记录缺少完整输入，单列为按已签收脚本重建的标量比较；不能冒称原始逐输入回放。A2已用于调参的两点不算独立验证。',
             '- 坐标单位是世界单位；HP/墨量误差为0..1归一化值。原生伤害/死亡时刻是首次包采样界限，非逐帧命中真值。', '',
             '## A6 原始输入回放', '',
             '| 场景 | 模拟直接伤害 | 原生直接伤害采样 | 首次命中时差（模拟−原生，帧） | 目标轨迹RMSE | 射手墨量MAE / 最大差 |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for r in report['a6']:
        target, own = r['players']['player_1'], r['players']['player_0']
        sim_damage = sum(v['amount'] for v in r['_damage'])
        native_damage = sum(v['hp_drop'] for v in r['_native_damage'])
        lines.append(f"| {r['case']} | {sim_damage*100:.1f} | {native_damage*100:.1f} | {target['first_direct_damage_delay_frames']} | {target['position_world_units']['rmse']:.4f} | {own['ink_fraction']['mean']:.4f} / {own['ink_fraction']['maximum']:.4f} |")
    lines += ['', '时差包含出刀、投射物、受击同步和包采样相位差；不把其中任一项单独认定为根因。墨量差包含原生蓄力预扣/退款而模拟仅释放扣款的已知遗漏。', '',
              '## T1 三图到计时归零的连续回放', '',
              '| 地图 | 模拟帧数 | 位置RMSE（0 / 1） | 墨量MAE（0 / 1） | 击倒数 原生→模拟（0 / 1） | 首次击倒时差（0 / 1） | 帧/秒 |',
              '| --- | ---: | ---: | ---: | --- | --- | ---: |']
    for r in report['t1']:
        a, b = (r['players'][f'player_{i}'] for i in range(2))
        lines.append(f"| {r['stage']} | {r['frames']} | {a['position_world_units']['rmse']:.3f} / {b['position_world_units']['rmse']:.3f} | {a['ink_fraction']['mean']:.4f} / {b['ink_fraction']['mean']:.4f} | {a['knockdown_counts_native_sim']} / {b['knockdown_counts_native_sim']} | {a['first_knockdown_delay_frames']} / {b['first_knockdown_delay_frames']} | {r['frames_per_second']:.1f} |")
    lines += ['', '地图1=Yunohana（温泉峡谷）、2=District00、3=Yagara。击倒列按受害者计；`None`表示没有双方均可匹配的首次事件，不补零。完整事件与采样曲线留在本机 work/sim/comparison/。', '',
              '| 地图 | ≥29伤害采样数 / 模拟伤害事件数（受害者0 / 1） | 首次伤害时差（0 / 1，帧） |',
              '| --- | --- | --- |']
    for r in report['t1']:
        a, b = (r['players'][f'player_{i}'] for i in range(2))
        lines.append(f"| {r['stage']} | {a['damage_event_counts_native_sim']} / {b['damage_event_counts_native_sim']} | {a['first_direct_damage_delay_frames']} / {b['first_direct_damage_delay_frames']} |")
    lines += ['', '原生列只统计单包HP下降≥.29以排除慢速掉血；模拟列保留全部直接武器事件。两个事件计数定义不同，不能解释为逐发命中率。', '',
              '| 地图 | 原生最终涂地%（0 / 1） | 模拟最终涂地%（0 / 1） | 差值pp（0 / 1） |',
              '| --- | ---: | ---: | ---: |']
    for r in report['t1']:
        n, s, delta = r['native_final_turf_ratio'], r['simulator']['turf_ratio_by_role'], r['turf_error_pp']
        lines.append(f"| {r['stage']} | {n[0]*100:.3f} / {n[1]*100:.3f} | {s[0]*100:.3f} / {s[1]*100:.3f} | {delta[0]:+.3f} / {delta[1]:+.3f} |")
    lines += ['', '涂地差值仅作诊断：导航节点近似可涂域、初始原生墨图未知、出生飞行省略、每局历史配装未写在单局result中（因此用AP0），无法据此验收原生占地一致。原生世界墨图仍是unknown；模拟墨图不回填为A3b证据。', '',
              '## A1 / A2 标量与脚本重建', '',
              '| A1 场景 | 原生损血 | 模拟损血 | 模拟直接伤害 | 游戏时长 |',
              '| --- | ---: | ---: | ---: | ---: |']
    for r in report['a1']['cases']:
        lines.append(f"| {r['label']} | {r['native_loss']:.6f} | {r['simulated_loss']:.6f} | {r['simulated_direct_damage']:.6f} | {r['script_frames']/60:.1f}s |")
    lines += ['', '| A2 配装交换 | 完整挥刀数 原生→模拟（0 / 1） | 6单位潜游 原生帧（0 / 1） | 模拟帧（0 / 1） |',
              '| --- | --- | ---: | ---: |']
    for r in report['a2']['rounds']:
        fmt = lambda values: ' / '.join('None' if v is None else f'{v:.4f}' for v in values)
        lines.append(f"| {r['swapped']} | {r['native_full_cost_counts']} → {r['simulated_full_cost_counts']} | {fmt(r['native_swim_frames'])} | {fmt(r['simulated_swim_frames'])} |")
    lines += ['', 'A2使用严格完整成本19/31口径；不使用含尾段小扣墨的旧21/33。AP曲线只有这两个经验锚点，其余技能未实现并在unsupported中列出。', '',
              '## 性能与复现', '',
              '| 工作负载 | 图 | 帧数 | 墙钟秒 | 模拟帧/秒 |',
              '| --- | ---: | ---: | ---: | ---: |']
    for r in report['benchmarks']:
        lines.append(f"| idle core（不含策略/观测） | {r['stage']} | {r['frames']} | {r['wall_seconds']:.3f} | {r['frames_per_second']:.1f} |")
    lines += ['', 'T1回放的吞吐包含物理、武器、涂地、每帧状态留存；不含文件读入和地图加载，未运行策略/可见性投影。idle只作低成本基准，不等于实战或批量吞吐。每模拟帧仍为1/60游戏秒。单CPU串行运行，无渲染、无GPU调用。', '',
              '```sh', '.venv/bin/python -m unittest sim.test_core sim.test_replay -v',
              '.venv/bin/python -m sim.report', '# 原始曲线/报告：work/sim/comparison/',
              '# 小窗口也可单独复放：',
              '.venv/bin/python -m sim.replay work/arena/t1/round-001/game-0-attempt-000 --frames 600', '```', '',
              '每次报告保存参数来源哈希、地图/导航哈希、原始记录哈希与sim源码哈希；复核输入文件结束时未变化。报告是历史观测对照，没有新实机校准。三图源记录均为 work/arena/t1/round-001/game-N-attempt-000（N=0/1/2）。', '',
              '原始曲线JSON的 sampled_curves 含每个唯一采样帧的 native/sim XYZ、HP、墨量和存活列；只保存在 work/，不随文档提交轨迹或游戏资产。', '',
              '## 结论与停止边界', '',
              '35/70与蓄力边界等局部机制有对照基础；轨迹、事件时刻、原生墨量中间态与最终占地仍有明显差异。当前仅适用于调试判定链路和快速筛查策略接口，不能用模拟胜率替代原生擂台结论。', '',
              '按本轮要求在核心机制和对照报告完成后停止。乌贼滑、墙蓄跳、冲刺斩、快速炸弹、触手喷射效果、完整技能曲线及官方Gym/PettingZoo spaces/合规适配均未签收；统一实机校准清单在 notes/PROGRESS.md。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'work/sim/comparison')
    args = parser.parse_args()
    out = args.out.resolve()
    if ROOT / 'work' not in out.parents:
        parser.error('raw comparison artifacts must stay under work/')
    out.mkdir(parents=True, exist_ok=True)
    code_sources = provenance(list((ROOT / 'sim').glob('*.py')))
    params = Parameters.local()
    terrains = {i: Terrain.load(i) for i in (1, 2, 3)}
    report = dict(schema='sim.comparison.v1', assumptions=asdict(Assumptions()),
                  parameter_sources=params.data['sources'], a6=[], t1=[])
    report['a1'], report['a2'] = a1(params, terrains[1]), a2(params, terrains[1])
    for prefix in ('minimum-predecessor-damage', 'minimum-full-damage', 'emerge-full-damage'):
        raw = a6_case(ROOT / 'work/a6/combat-20261019-131326-782403', prefix, parameters=params, terrain=terrains[1])
        (out / (prefix + '.json')).write_text(json.dumps(raw) + '\n')
        summary = compact(raw)
        summary['_damage'] = raw['players']['player_1']['simulated_damage']
        summary['_native_damage'] = raw['players']['player_1']['native_direct_damage_samples']
        report['a6'].append(summary)
        print('A6', prefix, 'complete', flush=True)
    for stage in (1, 2, 3):
        print('T1 map', stage, 'starting offline replay', flush=True)
        raw = tournament(ROOT / f'work/arena/t1/round-001/game-{stage-1}-attempt-000', frames=None,
                         parameters=params, terrain=terrains[stage])
        (out / f't1-stage-{stage}.json').write_text(json.dumps(raw) + '\n')
        report['t1'].append(compact(raw))
        print('T1 map', stage, 'complete', round(raw['frames_per_second'], 1), 'frames/s', flush=True)
    report['benchmarks'] = benchmark(params, terrains)
    paths = list((ROOT / 'sim').glob('*.py'))
    paths += [ROOT / f'work/arena/maps/{name}/{file}' for name in ('Yunohana', 'District00', 'Yagara')
              for file in ('human.npz', 'sight.npz', 'navigation.json')]
    report['code_and_map_sources'] = provenance(paths)
    if any(report['code_and_map_sources'].get(path) != digest for path, digest in code_sources.items()):
        raise RuntimeError('simulator source changed during report')
    for item in [report['a1'], report['a2'], *report['a6'], *report['t1']]:
        for relative, digest in item['sources'].items():
            if sha256(ROOT / relative) != digest:
                raise RuntimeError('source changed during replay: ' + relative)
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    (out / 'COMPARISON.md').write_text(markdown(report))
    print(out / 'COMPARISON.md', flush=True)


if __name__ == '__main__':
    main()
