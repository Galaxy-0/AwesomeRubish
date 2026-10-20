"""Derive the native-window comparison from frozen work artifacts, offline."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path

from sim.parameters import ROOT,sha256
from sim.ranking_report import native_game,sim_game,summary,tau_b,sign


def pooled(rows,name):
    values=[r['all_samples'][name] for r in rows if name in r['all_samples']]
    count=sum(v['samples'] for v in values)
    return dict(samples=count,mean=sum(v['mean']*v['samples'] for v in values)/count,
        rmse=math.sqrt(sum(v['rmse']**2*v['samples'] for v in values)/count))


def matched(native,games):
    strata=Counter((g['stage'],g['swap']) for g in native);counts=Counter((g['stage'],g['swap']) for g in games)
    games=[g for g in games if (g['stage'],g['swap']) in strata]
    weights=[strata[(g['stage'],g['swap'])]/counts[(g['stage'],g['swap'])] for g in games]
    return summary(games,weights)


def load_rank(directory):
    result={}
    for path in sorted(directory.glob('*/result.json')):
        if not any(path.parent.name.startswith(p+'-map') for p in ('A5','R0','R1','R2','R3','R4')):continue
        r=json.loads(path.read_text())
        if 'pair' not in r or 'games' not in r:continue
        if r['frames_per_game']!=10800:raise ValueError('incomplete ranking duration')
        result.setdefault(r['pair'],[]).extend(r['games'])
    return result


def build(base,partial=False):
    sources=ROOT/'work/sim/ranking/sources.json';source=json.loads(sources.read_text())
    old=load_rank(ROOT/'work/sim/ranking');new=load_rank(base/'ranks-final')
    if any(len(old.get(p,[]))!=36 for p in ('A5','R0','R1','R2','R3','R4')):raise ValueError('original216 registered games incomplete')
    expected=dict(A5=12,R1=18,R2=18,R3=18)
    if not partial and {p:len(new.get(p,[])) for p in expected}!=expected:raise ValueError('final66 matches not complete')
    pairs={}
    for pair in expected:
        if not new.get(pair):continue
        ng=[native_game(g) for g in source['references'][pair]['matches'] if pair!='A5' or g['stage']==3]
        a=[sim_game(g) for g in old[pair]];b=[sim_game(g) for g in new[pair]];by=[]
        strata=sorted({(g['stage'],g['swap']) for g in ng})
        for stage,swap in strata:
            ns=[g for g in ng if (g['stage'],g['swap'])==(stage,swap)]
            aa=[g for g in a if (g['stage'],g['swap'])==(stage,swap)];bb=[g for g in b if (g['stage'],g['swap'])==(stage,swap)]
            if not bb:continue
            by.append(dict(stage=stage,swap=swap,native=summary(ns),before=summary(aa),after=summary(bb)))
        complete=len(new[pair])==expected[pair]
        pairs[pair]=dict(complete=complete,native=summary(ng),before=matched(ng,a),after=matched(ng,b),strata=by)
    tau={}
    if all(p in pairs and pairs[p]['complete'] for p in ('R1','R2','R3')):
        strengths={name:[pairs[p][name]['strength'][0] for p in ('R1','R2','R3')] for name in ('native','before','after')}
        tau=dict(strengths=strengths,before=tau_b(strengths['native'],strengths['before']),after=tau_b(strengths['native'],strengths['after']))
    horizons={name:json.loads((base/f'horizon-{name}.json').read_text()) for name in ('before','final')}
    primary=[]
    for n in (30,60,120,300):
        comparisons={}
        for name,report in horizons.items():
            rows=[r for r in report['results'] if r['horizon']==n]
            comparisons[name]=dict(windows=sum(r['counts']['windows'] for r in rows),
                metrics={metric:pooled(rows,metric) for metric in ('position','heading','yaw','ink','hp','squid','submerged')})
        primary.append(dict(horizon=n,**comparisons))
    inputs={p.name:sha256(p) for p in [sources,base/'analysis-v2.json',base/'audit.json',base/'horizon-before.json',base/'horizon-final.json',base/'bends-horizon-final.json']}
    return dict(schema='sim.native.window.comparison.v1',partial=partial,pairs=pairs,common_opponent=tau,primary=primary,
        input_sha256=inputs,analysis=json.loads((base/'analysis-v2.json').read_text()),audit=json.loads((base/'audit.json').read_text()))


def record(r):
    return f"{r['wins'][0]}:{r['wins'][1]}"+(f" 平{r['draws']}" if r['draws'] else '')


def pair(v,digits=3):return ' / '.join(f'{x:.{digits}f}' for x in v)


def markdown(report):
    a=report['audit'];lines=['## 原生 P0 校准窗口（2026-10-21）','',
        f"使用 c0a03e4 签收的 v4 默认宿主 `work/a8/dmhost-arena-v15`，geometry、每案例新进程。共32次房间尝试：22次 collected、10次失败/取消，全部原件保留；并发案例生命周期峰值{a['max_overlapping_case_lifetimes']}房，资源压力最高{a['resource_max']['pressure']}、新增swapout {a['resource_max']['new_swapout_bytes']}字节，关闭后无原生进程。没有改对战/策略目录，没有恢复原生T1；冻结策略仅在离线模拟中调用。",
        '', '收集完成不等于全部 P0 验收。已校准首次发射、按键重生、人形响应/AP锚点、自由空中有效运动及局部脚下墨/墨刃场景碰撞。完整计分域、世界墨图映射、部分拐角/相机状态和蓄力首伤残差仍未签收。派生模型与原件均留在 `work/sim/window-20261021/`，提交不含游戏数据、地图或截图。',
        '', '### 位置与状态短时域：同一历史留出集，因果重置', '',
        '比较当前离线诊断修复后的旧模型与本轮模型，均保留落地包支撑约束，避免把上轮穿地板修复重复算成本轮收益。三图固定 round-001 留出局，N=30/60/120/300；按原生 sample frame、过去可交付包初始化，不复制窗口内状态。统计为按有效采样数合并的 RMSE/MAE，原生墨图/投射物与武器阶段仍不可完全初始化。', '',
        '| N | 窗口数 | 位置RMSE 前→后 | 身体朝向MAE 前→后 | 墨量MAE 前→后 | HP MAE 前→后 |',
        '| ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in report['primary']:
        before,after=row['before']['metrics'],row['final']['metrics']
        lines.append(f"| {row['horizon']} | {row['final']['windows']} | {before['position']['rmse']:.4f} → {after['position']['rmse']:.4f} | {before['heading']['mean']:.4f} → {after['heading']['mean']:.4f} | {before['ink']['mean']:.5f} → {after['ink']['mean']:.5f} | {before['hp']['mean']:.5f} → {after['hp']['mean']:.5f} |")
    lines+=['','每图的采样P95、窗口RMSE P95、末端分布及形态误差在 `horizon-final.json`，不将三图P95再取平均冒充合并分布。HP并非各时域一致改善；排名和涂地不由位置指标自动推定。', '',
        '### 冻结策略排名：66局完整10800帧预测对局', '',
        '本轮只重跑反例所需分层：A5 Yagara双侧12局，R1/R2/R3各三图原生观测侧18局。每层seed0固定，seed1..5为±.15 XZ、±.03rad yaw敏感性；不是原生独立随机试验。首次发射由独立P0中立房拟合，观测使用通用4帧采样/1帧交付假设，**不注入历史策略开局观测、轨迹或逐局时钟**。出生偏移保持在有限发射模型中，不因第一帧重置丢失。R0/R4与A5其它两图没有重跑，不把子集结果冒充全量132局重验。', '',
        '| 对阵/图/侧 | 原生A:B | 旧216局同分层A:B | 本轮A:B | 占地% 原生A/B | 本轮A/B | HUD倒下计数 原生A/B | 本轮A/B |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for label,p in report['pairs'].items():
        for s in p['strata']:
            n,b,f=s['native'],s['before'],s['after']
            lines.append(f"| {label}/{s['stage']}/{int(s['swap'])} | {record(n)} | {record(b)} | {record(f)} | {pair(n['turf_pp'])} | {pair(f['turf_pp'])} | {pair(n['hud_downs'],2)} | {pair(f['hud_downs'],2)} |")
    if report['common_opponent']:
        c=report['common_opponent'];lines+=['',f"共同bravo-v1对手下，alpha v1/v2/v3的原生强度为{c['strengths']['native']}，旧模拟为{c['strengths']['before']}，本轮为{c['strengths']['after']}；Kendall tau-b **{c['before']['tau_b']:.6f} → {c['after']['tau_b']:.6f}**。保留原生v1/v2的BO3并列，不为断开的A5/R0/T1对阵图制造统一排名。BO3样本很小，tau与点胜率方向只作有效性诊断。"]
    lines+=['','本轮完整原件：`comparison.json`、`analysis-v2.json`、`horizon-{before,final}.json`、`bends-horizon-{before,final}.json`、`ranks-final/*/{plan,result}.json`、`audit.json`。首轮66局 `ranks/` 作为发射/人形/涂地消融保留；最终模型在 `models-v2/`，首轮模型在 `models/`，不覆盖旧216局。','']
    return '\n'.join(lines)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=ROOT/'work/sim/window-20261021');p.add_argument('--partial',action='store_true');a=p.parse_args()
    r=build(a.directory,a.partial);stem='comparison-partial' if a.partial else 'comparison'
    (a.directory/(stem+'.json')).write_text(json.dumps(r,indent=2)+'\n');(a.directory/(stem+'.md')).write_text(markdown(r)+'\n')
    print(json.dumps(dict(pairs={p:dict(native=v['native']['wins'],after=v['after']['wins']) for p,v in r['pairs'].items()},tau=r['common_opponent']),indent=2))
