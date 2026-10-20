"""Verify registered matches and report native/sim rank agreement honestly.

Incomplete matchup graphs cannot identify a global order across A5/R0/T1.
Primary outputs are observed-edge direction agreement, matched map/seat margins,
and tie-aware Kendall tau for alpha versions against the SAME bravo-v1 opponent.
"""
import argparse
from collections import Counter
import itertools
import json
import math
from pathlib import Path
import re

import numpy as np

from .parameters import ROOT,sha256
from .ranking_sources import WORK,PAIRS


def tau_b(x,y):
    if len(x)!=len(y) or len(x)<2:raise ValueError('paired rank vectors')
    concordant=discordant=tied_x=tied_y=tied_both=0
    for a,b in itertools.combinations(range(len(x)),2):
        sx=sign(x[a]-x[b]);sy=sign(y[a]-y[b])
        if sx==0 and sy==0:tied_both+=1
        elif sx==0:tied_x+=1
        elif sy==0:tied_y+=1
        elif sx==sy:concordant+=1
        else:discordant+=1
    denominator=math.sqrt((concordant+discordant+tied_x)*(concordant+discordant+tied_y))
    return dict(tau_b=(concordant-discordant)/denominator if denominator else None,
                concordant=concordant,discordant=discordant,tied_native=tied_x,tied_simulated=tied_y,tied_both=tied_both)


def sign(value,tolerance=1e-12):
    return int(value>tolerance)-int(value < -tolerance)


def native_game(raw):
    winner={'a':0,'b':1,'draw':None,None:None}[raw['outcome']]
    return dict(stage=raw['stage'],swap=raw['role_to_policy'][0]==1,winner=winner,
                turf_pp=raw['turf_pp'],hud_downs=raw['hud_downs'],environmental_downs=raw['environmental_downs'])


def sim_game(raw):
    return dict(stage=raw['stage'],swap=raw['swap'],winner=raw['winner'],
                turf_pp=[100*x for x in raw['turf_ratio_by_role']],hud_downs=raw['hud_downs'],
                environmental_downs=raw['environmental_downs'])


def summary(games,weights=None):
    if not games:raise ValueError('empty summary')
    weights=np.ones(len(games)) if weights is None else np.array(weights,float)
    if (weights<0).any() or not weights.sum():raise ValueError('invalid weights')
    weights/=weights.sum()
    wins=[sum(g['winner']==i for g in games) for i in range(2)]
    rate=[min(1.,max(0.,float(sum(w*(g['winner']==i) for g,w in zip(games,weights))))) for i in range(2)]
    draw=min(1.,max(0.,float(sum(w*(g['winner'] is None) for g,w in zip(games,weights)))))
    result=dict(games=len(games),wins=wins,draws=sum(g['winner'] is None for g in games),win_rate=rate,
                draw_rate=draw,strength=[r+.5*draw for r in rate])
    for name in ('turf_pp','hud_downs','environmental_downs'):
        result[name]=np.average([g[name] for g in games],axis=0,weights=weights).tolist()
    return result


def compare_pair(native,simulated):
    n=[native_game(g) for g in native];s=[sim_game(g) for g in simulated]
    baseline=summary(n);balanced=summary(s)
    strata=Counter((g['stage'],g['swap']) for g in n)
    counts=Counter((g['stage'],g['swap']) for g in s)
    weights=[strata[(g['stage'],g['swap'])]/counts[(g['stage'],g['swap'])] for g in s]
    weighted=summary(s,weights)
    fixed=summary([sim_game(g) for g in simulated if g['cohort']=='fixed'])
    rows=[]
    for stage in (1,2,3):
        ng=[g for g in n if g['stage']==stage];sg=[g for g in s if g['stage']==stage]
        a,b=summary(ng),summary(sg)
        w=[strata[(g['stage'],g['swap'])]/counts[(g['stage'],g['swap'])] for g in sg]
        matched=summary(sg,w)
        rows.append(dict(stage=stage,native=a,simulated=b,simulated_native_strata_weighted=matched,
                         same_direction=sign(a['strength'][0]-.5)==sign(matched['strength'][0]-.5),
                         same_direction_balanced=sign(a['strength'][0]-.5)==sign(b['strength'][0]-.5),
                         margin_error_pp=(matched['turf_pp'][0]-matched['turf_pp'][1])-(a['turf_pp'][0]-a['turf_pp'][1])))
    strata_results=[]
    for stage,swap in sorted(strata):
        a=summary([g for g in n if (g['stage'],g['swap'])==(stage,swap)])
        b=summary([g for g in s if (g['stage'],g['swap'])==(stage,swap)])
        strata_results.append(dict(stage=stage,swap=swap,native=a,simulated=b))
    matched_fixed=[]
    for raw,game in zip(native,n):
        candidate=next(g for g in simulated if g['stage']==game['stage'] and g['swap']==game['swap'] and g['seed']==0)
        matched_fixed.append(dict(stage=game['stage'],swap=game['swap'],native_winner=game['winner'],
                                  simulated_winner=candidate['winner'],agree=game['winner']==candidate['winner']))
    return dict(native=baseline,simulated_balanced=balanced,simulated_native_strata_weighted=weighted,
                simulated_fixed=fixed,by_map=rows,by_observed_native_seat=strata_results,
                fixed_native_game_agreement=summary_agreement(matched_fixed),
                strength_difference_pp=100*(weighted['strength'][0]-baseline['strength'][0]),
                same_direction=sign(baseline['strength'][0]-.5)==sign(weighted['strength'][0]-.5),
                same_direction_balanced=sign(baseline['strength'][0]-.5)==sign(balanced['strength'][0]-.5),
                turf_difference_pp=[b-a for a,b in zip(baseline['turf_pp'],weighted['turf_pp'])],
                hud_down_difference_per_game=[b-a for a,b in zip(baseline['hud_downs'],weighted['hud_downs'])],
                distinct_trajectories=len({g['trajectory_sha256'] for g in simulated}),
                distinct_final_outcomes=len({(g['winner'],tuple(g['turf_ratio_by_role']),tuple(g['hud_downs'])) for g in simulated}),
                mechanics=dict(sum((Counter(g['mechanics']) for g in simulated),Counter())),
                unsupported=dict(sum((Counter(g['unsupported']) for g in simulated),Counter())))


def summary_agreement(rows):
    return dict(comparisons=len(rows),agreements=sum(r['agree'] for r in rows),
                note='Native games reuse the same fixed simulation within a map/seat; not independent simulation repeats.')


def collect(out):
    plan_path=out/'plan.json';source_path=out/'sources.json'
    plan=json.loads(plan_path.read_text());source=json.loads(source_path.read_text())
    if plan['sources_sha256']!=sha256(source_path):raise ValueError('source reference drift')
    for path,digest in source['public_library_sha256'].items():
        if sha256(ROOT/path)!=digest:raise ValueError('public library changed')
    by_pair={k:[] for k in PAIRS};evidence={};seconds=0.;group_count=0
    for file in sorted(out.glob('*-map*-batch*/result.json')):
        if not re.fullmatch(r'(A5|R[0-4])-map[123]-batch\d{2}',file.parent.name):continue
        group=json.loads(file.read_text());pair=group['pair']
        if (group['frames_per_game']!=plan['frames'] or group['model_sha256']!=plan['model_sha256']
                or group['sim_source_sha256']!=plan['sim_source_sha256']
                or group['policy_sha256']!=[source['policies'][name]['directory_sha256'] for name in PAIRS[pair]]):
            raise ValueError('group experiment binding mismatch: '+str(file))
        by_pair[pair].extend(group['games']);seconds+=group['wall_seconds'];group_count+=1
        evidence[str(file.relative_to(ROOT))]=sha256(file)
    expected={(p['stage'],p['swap'],p['seed'],p['cohort']) for p in plan['scenarios']}
    for pair,games in by_pair.items():
        keys=[(g['stage'],g['swap'],g['seed'],g['cohort']) for g in games]
        if len(keys)!=len(expected) or set(keys)!=expected or len(keys)!=len(set(keys)):
            raise ValueError(f'{pair}: incomplete/duplicate scenario grid ({len(keys)}/{len(expected)}); no final rank report')
        if any(g['frame']!=plan['frames'] for g in games):raise ValueError('partial match in results')
    return plan,source,by_pair,evidence,seconds,group_count


def render(report):
    lines=['\n## 第三阶段最终有效性检验：策略排名\n',
        '所有对阵使用同一冻结模型，三图、两出生侧、六组起点，每对阵36局，共216局；每局10800帧。'
        '原策略代码、配装、调用频率与沙箱超时保留。seed0为固定起点，另五组为预先登记的±.15单位XZ、±.03rad yaw敏感性。'
        '后者不是已辨识的原生随机分布，不作独立二项胜率区间。没有启动游戏。\n',
        '| 对阵（顺序A/B） | 原生A胜:B胜 | 模拟A胜:B胜（平） | 固定起点A胜:B胜（平） | ΔA强度 pp¹ | 方向一致 匹配/均衡 |',
        '| --- | ---: | ---: | ---: | ---: | --- |']
    def wl(s):return f"{s['wins'][0]}:{s['wins'][1]} ({s['draws']})"
    for label,row in report['pairs'].items():
        a,b=row['policies'];r=row['native'];s=row['simulated_balanced'];f=row['simulated_fixed']
        direction='/'.join('是' if row[key] else '否' for key in ('same_direction','same_direction_balanced'))
        lines.append(f"| {label} {a} / {b} | {r['wins'][0]}:{r['wins'][1]} | {wl(s)} | {wl(f)} | {row['strength_difference_pp']:+.2f} | {direction} |")
    rank=report['ranking'];lines.extend(['',
        '¹强度=胜率+半数平局率；Δ及主方向指标使用原生地图/出生侧频数重加权。胜负计数列为均衡三图双侧原始计数，均衡方向另列。R1–R4原生每图仅一个出生侧，不能把原生版本变化和轮间换侧完全分离。',
        f"匹配原生地图/侧后，六条实测对阵边方向一致 **{rank['agree_edges']}/6**；逐地图 **{rank['agree_map_edges']}/18**。均衡全部侧的对阵方向一致{rank['agree_edges_balanced']}/6。",
        f"同一bravo-v1对手下，alpha v1/v2/v3的原生强度为{rank['common_opponent']['native']}，模拟为{rank['common_opponent']['simulated']}；Kendall tau-b = **{rank['common_opponent']['kendall']['tau_b']}**。",
        f"共同对手tau采用原生地图/侧频数匹配；均衡全部侧的模拟强度另为{rank['common_opponent']['simulated_balanced']}，对应tau-b={rank['common_opponent']['kendall_balanced']['tau_b']}。",
        'A5、R0和后续T1属于三个断开的对阵图；不为它们编造统一全局排名。tau只比较有共同对手的三版alpha；原生v1/v2同为1/3，保留并列。'
        'R1–R4各仅BO3，原生胜率本身不确定，不能把点估计方向或tau当严格强弱证明。',
        '', '| 对阵 | 原生平均占地% A/B | 模拟平均网格% A/B¹ | Δ占地pp A/B | 原生HUD敌倒/局 A/B | 模拟敌倒/局 A/B¹ |',
        '| --- | ---: | ---: | ---: | ---: | ---: |'])
    def fmt(xs):return ' / '.join(f'{x:.3f}' for x in xs)
    for label,row in report['pairs'].items():
        n=row['native'];s=row['simulated_native_strata_weighted']
        lines.append(f"| {label} | {fmt(n['turf_pp'])} | {fmt(s['turf_pp'])} | {fmt(row['turf_difference_pp'])} | {fmt(n['hud_downs'])} | {fmt(s['hud_downs'])} |")
    lines.extend(['',
        '¹模拟均值按原生地图/侧频数加权。网格分母是A3导航可潜节点，原生结算分母/涂墨传播仍不同，因此Δ是诊断差，不是占地等价误差验收。'
        '模拟“敌倒”统计对手全部死亡，与原生观察者HUD口径靠近；原生没有最后一击归属，模拟归属击倒另外保存在JSON，不能混作同一实测指标。',
        '', '| 对阵/图 | 原生A胜:B胜 | 模拟均衡A胜:B胜（平） | 匹配侧后的占地差值(A-B)误差pp |',
        '| --- | ---: | ---: | ---: |'])
    for label,row in report['pairs'].items():
        for m in row['by_map']:
            n,s=m['native'],m['simulated']
            lines.append(f"| {label} / {m['stage']} | {n['wins'][0]}:{n['wins'][1]} | {wl(s)} | {m['margin_error_pp']:+.3f} |")
    lines.extend(['',
        report['conclusion'],
        '', '| 对阵 | roll / surge / dash / bomb / zip事件（216局中的该对阵） | 未支持配装（每局初始化计数合计） |',
        '| --- | --- | --- |'])
    for label,row in report['pairs'].items():
        counts=row['mechanics']
        used=' / '.join(str(counts.get(k,0)) for k in ('squid_roll','squid_surge','dash','burst_bomb_throw','zip_activate_simplified'))
        gear=', '.join(f"{k.removeprefix('gear:')}:{v}" for k,v in sorted(row['unsupported'].items()) if k.startswith('gear:')) or '无'
        lines.append(f'| {label} | {used} | {gear} |')
    lines.extend(['',
        '该实验检验当前简化模型的策略外部有效性，没有按胜者反向校准。出生发射/重生过程、原生墨图与可涂分母、配装曲线和攀爬仍存在缺口；'
        '高级机制的A6同房重算不能替代策略胜负验证。详细逐图/实测出生侧/固定起点对照、机制使用与unsupported计数见JSON。',
        f"纯离线双worker以内执行；已完成组计算墙钟累计{report['group_wall_seconds']:.1f}秒，含策略/可见性/序列化的加总吞吐{report['aggregate_environment_fps']:.1f}环境帧/秒。"
        '累计组墙钟会把两个并发worker的时间相加，不能当实际总耗时；不等于第二阶段纯核心性能。',
        '', '复现：`python -m sim.ranking_sources` → `python -m sim.advanced` → `python -m sim.ranking` → `python -m sim.ranking_report`。'
        '默认单模拟worker，可将互斥对阵集合分别用`--pairs`交给最多两个worker；同一组禁止并发写。核心/模型/策略/公共库/参考SHA和完整情景网格均校验后才输出最终排名。\n'])
    return '\n'.join(lines)


def main(out=WORK):
    plan,source,games,evidence,seconds,groups=collect(out)
    pairs={key:dict(policies=PAIRS[key],**compare_pair(source['references'][key]['matches'],games[key])) for key in PAIRS}
    common_keys=('R1','R2','R3')
    x=[pairs[k]['native']['strength'][0] for k in common_keys]
    y=[pairs[k]['simulated_native_strata_weighted']['strength'][0] for k in common_keys]
    balanced=[pairs[k]['simulated_balanced']['strength'][0] for k in common_keys]
    ranking=dict(agree_edges=sum(p['same_direction'] for p in pairs.values()),
                 agree_edges_balanced=sum(p['same_direction_balanced'] for p in pairs.values()),
                 agree_map_edges=sum(m['same_direction'] for p in pairs.values() for m in p['by_map']),
                 common_opponent=dict(opponent='bravo-v1',policies=['alpha-v1','alpha-v2','alpha-v3'],
                                      native=x,simulated=y,kendall=tau_b(x,y),
                                      simulated_balanced=balanced,kendall_balanced=tau_b(x,balanced)))
    conclusion=('当前模拟器未通过策略排名一致性检验，不能据此替代原生策略淘汰或配装选择。'
                if ranking['agree_edges']<6 else
                '六个观察到的对阵方向一致；BO3样本量、未验证初值分布及占地/机制残差仍不足以签收原生等价。')
    report=dict(schema='sim.ranking.comparison.v1',pairs=pairs,ranking=ranking,
                sources_sha256=sha256(out/'sources.json'),plan_sha256=sha256(out/'plan.json'),
                group_results_sha256=evidence,groups=groups,group_wall_seconds=seconds,
                aggregate_environment_fps=sum(len(g)*plan['frames'] for g in games.values())/seconds,
                conclusion=conclusion)
    (out/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    section=render(report)
    (out/'comparison.md').write_text(section)
    print(section)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=WORK)
    a=p.parse_args();main(a.out)
