"""Derive the native-window comparison from frozen work artifacts, offline."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path

from sim.parameters import ROOT,sha256
from sim.ranking_report import native_game,sim_game,summary,tau_b,sign
from sim.ranking_sources import PAIRS


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
    if not partial:
        model_paths=dict(motion=base/'models-v2/motion.json',opening=base/'models-v2/opening.json',paint=base/'models-v2/paint.json',
            weapon=ROOT/'work/sim/fidelity/weapon.json',advanced=ROOT/'work/sim/advanced/model.json')
        identities=set()
        for path in (base/'ranks-final').glob('*/result.json'):
            r=json.loads(path.read_text());binding=r['binding']
            if binding['sources']!=sha256(sources):raise ValueError('ranking reference source drift')
            if any(sha256(ROOT/name)!=digest for name,digest in binding['code'].items()):raise ValueError('ranking core source drift')
            if binding['models']!={k:sha256(p) for k,p in model_paths.items()}:raise ValueError('ranking calibrated model drift')
            if r['policy_sha256']!=[source['policies'][n]['directory_sha256'] for n in PAIRS[r['pair']]]:
                raise ValueError('ranking frozen policy binding mismatch')
            for g in r['games']:
                identity=r['pair'],g['stage'],g['swap'],g['seed']
                if identity in identities or g['frame']!=10800:raise ValueError('duplicate/incomplete game')
                identities.add(identity)
        if len(identities)!=66:raise ValueError('ranking unique game count')
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
    distributions=[]
    for f in horizons['final']['results']:
        b=next(v for v in horizons['before']['results'] if (v['stage'],v['horizon'])==(f['stage'],f['horizon']))
        distributions.append(dict(stage=f['stage'],horizon=f['horizon'],windows=f['counts']['windows'],
            before=b['all_samples']['position'],after=f['all_samples']['position'],
            window_rmse_p95=f['window_rmse']['position']['p95'],endpoint_p95=f['endpoint_samples']['position']['p95']))
    return dict(schema='sim.native.window.comparison.v1',report_code_sha256=sha256(Path(__file__)),partial=partial,pairs=pairs,common_opponent=tau,primary=primary,
        position_by_map=distributions,input_sha256=inputs,analysis=json.loads((base/'analysis-v2.json').read_text()),audit=json.loads((base/'audit.json').read_text()))


def record(r):
    return f"{r['wins'][0]}:{r['wins'][1]}"+(f" 平{r['draws']}" if r['draws'] else '')


def pair(v,digits=3):return ' / '.join(f'{x:.{digits}f}' for x in v)


def mechanisms(report):
    a=report['analysis'];lines=['### 原生校准项与独立重复','',
        '人形杆量采用径向四次方：AP0满杆约.096，.5杆约.006、.85杆约.050112；(1,.25)方向仍为4:1，不能逐轴取四次方。人形加速/制动为.010/.008；run AP0/19/57锚点速度约.096/.121417/.144，AP3/10/38仅插值，charge/recovery/swim未据此改配装曲线。空中候选由地图1/2角色0的4段、22个自由空中采样拟合，识别时使用过去已交付native yaw以分离相机变化；有效系数不当作游戏C++默认值。', '',
        '| 新原生运动房 | 75帧启动/制动窗口位置RMSE 前→后 | 证据层级 |', '| --- | ---: | --- |']
    for m in a['motion']:
        c=m['comparison'];role='独立AP0房验证' if m['path'].endswith('ap0') else 'AP19过渡/AP57锚点参与拟合，校准重算'
        lines.append(f"| {m['path'].split('/')[-1]} | {c[0]['position']['rmse']:.4f} → {c[1]['position']['rmse']:.4f} | {role} |")
    lines+=['','| 中立首发射（首240帧） | 位置RMSE 前→后 |','| --- | ---: |']
    for stage in (1,2,3):
        b,f=[next(v for v in a['opening'] if v['stage']==stage and v['model']==name) for name in ('before','after')]
        lines.append(f"| 图{stage}双侧 | {b['position']['rmse']:.4f} → {f['position']['rmse']:.4f} |")
    lines+=['','中立验证取新房前240帧；图1/2的房间后来在Judge收集器失败，前缀测量完整，不能把整房标成通过。发射模型包含首次接地后残余推力，不再从atlas地面起跑。', '']
    if a.get('steered_opening'):
        b,f=a['steered_opening'];lines +=[f"**非中立发射仍有反例**：留出图3 role1前推.85，接地前RMSE {f['precontact']['rmse']:.4f}，首240帧整体 {b['position']['rmse']:.4f} → {f['position']['rmse']:.4f}、最大 {f['position']['maximum']:.4f}。目前中立轨迹高度驱动与前推跨过落点后的地形/下落交互不充分，不能用中立低误差签收整个发射模型。",'']
    lines+=['| 真实重生房 | 发射台就绪后位置RMSE 前→后 | alive不一致率 前→后 |', '| --- | ---: | ---: |']
    for r in a['respawn']:
        b,f=r['comparisons'];lines.append(f"| {r['path'].split('/')[-1]} | {b['position_from_ready']['rmse']:.4f} → {f['position_from_ready']['rmse']:.4f} | {b['alive_mismatch']['mean']:.3%} → {f['alive_mismatch']['mean']:.3%} |")
    lines+=['','重生对照以首个原生死亡样本为条件起点，之后只重放输入。两房ready首包均在death首包后392帧；第三房中立900帧仍dead/HP1/墨1，单次ZR才发射。模型采用392帧就绪、460帧解锁候选及有限发射；精确内部锁定、持续按住ZR跨解锁、图2/3真实重生和重生配装未签收。三房接地后均无后续状态注入；前两房参与时序校准，首次发射曲线来源于另三个开局房。', '',
        '| 涂地世界接触扫描 | 独立重复 | 全部已观测点F1 前→后 | 留出两行F1 前→后 |', '| --- | --- | ---: | ---: |']
    for s in a['scans']:
        b,f=s['comparison'];bb={g['scope']:g for g in b['groups']};ff={g['scope']:g for g in f['groups']}
        lines.append(f"| {'轻挥12' if s['hold']==12 else '满蓄21'} | {'是' if s['independent_repeat'] else '首三行拟合，末两行留出'} | {bb['all']['f1']:.3f} → {ff['all']['f1']:.3f} | {bb['heldout_rows']['f1']:.3f} → {ff['heldout_rows']['f1']:.3f} |")
    lines+=['','轻/满脚下墨的粗网格有效半径均为1.5，接触有效出现延迟14/11帧候选，包含传感/采样延迟。按实际XYZ、contact0/4取每世界格首个样本，不把未走过的格补成未涂；每房89个代表点不是完整地面掩码。场景碰撞采用CoreIndex决定整条墨刃终止，非核心球碰场景后永久遮断以防下一帧穿墙复活；此候选在满蓄独立重复改善明显，仍不是原生内部实现证明。', '',
        '| Yagara固定落点涂地 | 原生终局% 两侧 | 旧模型% 两侧 | 本轮% 两侧 |','| --- | ---: | ---: | ---: |']
    for p in a['paint']:
        if p['score_peers'] is None:continue
        settings=p['settings'];label=f"hold{settings['hold']} × {settings['strokes']}";b,f=p['comparison']
        lines.append(f"| {label} | {pair(p['score_peers'][0])} | {pair(b['turf_pp'])} | {pair(f['turf_pp'])} |")
    uv=a.get('uv_control',{}).get('comparison',{})
    if uv:lines+=['',f"中立/仅role0射击纹理对照，新增R通道阈值像素：轻挥 {uv['sole-weak']['new_R_pixels']}、满蓄 {uv['sole-full']['new_R_pixels']}，G均保持192；证实可读到局部原生涂地支持，仍无UV→世界面积/计分域映射。上述世界接触F1与终局%显示局部改善和明显面积低估并存；没有按比分缩放分母或特殊充能。",'']
    lines+=['### 伤害、墨量与未解决的拐角','', '| 新原生房 | 首伤阶段 | 原生首伤区间 | 5帧模型区间越界 前/后 | 相对首个损血包 前/后 |', '| --- | --- | --- | ---: | ---: |']
    for room in a['combat']:
        for c in room['cases']:
            if not c['native_damage']:continue
            b,f=c['comparisons'][1:];lines.append(f"| {room['path'].split('/')[-1]} | {c['case']} | {c['native_damage'][0]['interval']} | {b['first_interval_violation']} / {f['first_interval_violation']} | {b['first_minus_native_latest']} / {f['first_minus_native_latest']}帧 |")
    lines+=['','近距实际1.070单位独立测得20+35=55，支持A1接触起点修正。轻挥原始无延迟模型早6–8帧，原5帧有效HP延迟在三个新房轻挥区间内；本轮未为对齐新房而调公共延迟。满蓄仍晚1–2帧，需要独立首刀/连刀相位与接触骨骼复测；满蓄发生在轻挥之后，原生损血被剩余HP截断，不能拿.45/.675损血当名义满蓄伤害。新轻挥射手墨量MAE约.0003，满蓄约.0033，预扣/退款模型本轮保留。', '',
        '拐角探针并非三图一致改善，`bends-horizon-final.json`保留全部分布。三图新开局左杆(1,.25)、右杆/gyro为零时native view yaw显著变化；经手动align的平地探针没有同样漂移。尚未分离相机初始/跟随状态与身体碰撞，不能据不同坐标的两条路线回调胶囊半径或台阶阈值。完整原生墨图、地形小物体精确支撑和墨色差速仍是P0/P1义务。', '']
    return '\n'.join(lines)


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
    lines+=['','| 图 | N | 位置RMSE 前→后 | 本轮采样P95 | 本轮窗口RMSE P95 | 本轮末端P95 |', '| ---: | ---: | ---: | ---: | ---: | ---: |']
    for d in report['position_by_map']:
        lines.append(f"| {d['stage']} | {d['horizon']} | {d['before']['rmse']:.4f} → {d['after']['rmse']:.4f} | {d['after']['p95']:.4f} | {d['window_rmse_p95']:.4f} | {d['endpoint_p95']:.4f} |")
    lines+=['','每图的采样P95、窗口RMSE P95、末端分布及形态误差在 `horizon-final.json`，不将三图P95再取平均冒充合并分布。HP并非各时域一致改善；排名和涂地不由位置指标自动推定。', '',mechanisms(report),
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
