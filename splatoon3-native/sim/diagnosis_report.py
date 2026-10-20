"""Report the scoped route counterexamples, without claiming rank calibration."""
import argparse
import json
from pathlib import Path
import numpy as np

from arena.lib.atlas import MapAtlas
from arena.lib.skills import Skills
from .diagnosis import OUT, WORK, native_trace, records
from .parameters import ROOT, sha256
from .ranking import core_hashes
from .ranking_report import summary, native_game, sim_game


def key(group):return group['pair'],group['stage'],group['swap']


def groups(directory,mode,seeds):
    expected={(pair,stage,swap) for pair in ('A5','R1','R2') for stage in ((3,) if pair=='A5' else (1,2,3))
              for swap in ((False,True) if pair=='A5' or mode=='ground' else (pair=='R1',))}
    found={};files={}
    for path in sorted(Path(directory).glob('*/result.json')):
        g=json.loads(path.read_text())
        if g['mode']!=mode or g['frames']!=10800 or g['seeds']!=seeds:raise ValueError('wrong diagnostic group')
        if key(g) in found:raise ValueError('duplicate group')
        if g['binding']['core']!=core_hashes() or g['binding']['sources']!=sha256(WORK/'sources.json'):
            raise ValueError('diagnostic source binding changed')
        if mode!='ground' and (g['binding'].get('reset_code')!=sha256(ROOT/'sim/horizon.py') or
                                g['binding']['clock_code']!=sha256(ROOT/'sim/observation_clock.py')):
            raise ValueError('conditional protocol/reset binding changed')
        models=dict(motion=ROOT/'work/sim/fidelity/motion.json',weapon=ROOT/'work/sim/fidelity/weapon.json',advanced=ROOT/'work/sim/advanced/model.json')
        if g['binding']['models']!={k:sha256(p) for k,p in models.items()}:raise ValueError('model changed')
        if [r['seed'] for r in g['games']]!=list(range(seeds)):raise ValueError('partial seed grid')
        for game in g['games']:
            trace=path.parent/f'trace-{game["seed"]}.npz'
            if sha256(trace)!=game['trace_sha256']:raise ValueError('trace changed')
        found[key(g)]=g;files[str(path.relative_to(ROOT))]=sha256(path)
    if set(found)!=expected:raise ValueError(f'incomplete {mode} grid: {set(found)^expected}')
    return found,files


def native_navigation(match):
    # Re-execute ONLY the public Skills controller over already-public own
    # observations. The frozen sandbox prefix separately verifies actions.
    output=[]
    for role,rows in enumerate(records(match)):
        nav=Skills(MapAtlas.load(match['stage']));failure_frame=None
        for row in rows:
            obs=row['observation'];own=obs['own']
            if own['position'] is None or own['public']['alive'] is not True:continue
            if own['ink'] is not None and own['ink']<.18:continue
            goal=nav.atlas.region('central_high') if role==1 else nav.objective()
            nav.move_to(obs,goal)
            if nav.failed and failure_frame is None:failure_frame=obs['frame']
        output.append(dict(failed=nav.failed,failure_frame=failure_frame,replans=nav.replans,events=nav.events))
    return output


def first_separation(match,path,start):
    trace=native_trace(match)
    with np.load(path) as data:sim=data['states']
    results=[]
    for role in (0,1):
        ids=trace.samples[role];ids=ids[(ids>=start)&(ids<len(sim))]
        ids=ids[np.isfinite(sim[ids,role,0])]
        error=np.linalg.norm(sim[ids,role,:3]-trace.states[ids,role,:3],axis=1)
        events={}
        for threshold in (1,3,5):
            over=np.flatnonzero(error>threshold)
            j=int(over[0]) if len(over) else None
            events[str(threshold)]=None if j is None else dict(frame=int(ids[j]),
                native=trace.states[ids[j],role,:3].tolist(),simulated=sim[ids[j],role,:3].tolist(),error=float(error[j]))
        results.append(events)
    return results


def horizon_means(path):
    data=json.loads(path.read_text());output=[]
    for group in data['results']:
        row=dict(pair=group['pair'],stage=group['stage'],metrics={})
        for h in ('30','60','120'):
            for metric in ('position','horizontal','vertical','ink','hp','yaw'):
                errors=[w['errors'][h][i][metric] for w in group['windows'] if 'errors'in w for i in (0,1)]
                n=sum(e['samples'] for e in errors)
                row['metrics'][f'{h}_{metric}_rmse']=float(np.sqrt(sum(e['rmse']**2*e['samples'] for e in errors)/n)) if n else None
        output.append(row)
    return output


def build(baseline,prefix,clock,seeds):
    source=json.loads((WORK/'sources.json').read_text());native=json.loads((OUT/'native.json').read_text())
    base,files=groups(baseline,'ground',1);warm,more=groups(prefix,'prefix',1);files.update(more)
    sampled,more=groups(clock,'prefix-clock',seeds);files.update(more)
    reproduced=0
    for (pair,stage,swap),g in base.items():
        prior=[]
        for file in WORK.glob(f'{pair}-map{stage}-batch[0-9][0-9]/result.json'):
            prior.extend(json.loads(file.read_text())['games'])
        old=next(r for r in prior if r['swap']==swap and r['seed']==0);new=g['games'][0]
        for field in ('winner','turf_ratio_by_role','hud_downs','environmental_downs','mechanics'):
            if old[field]!=new[field]:raise ValueError('instrumentation changed fixed baseline: '+field)
        reproduced+=1
    for p,h in source['public_library_sha256'].items():
        if sha256(ROOT/p)!=h:raise ValueError('public library drift')
    evidence=[]
    for label in ('A5','R1','R2'):
        for match in source['references'][label]['matches']:
            if label=='A5' and match['stage']!=3:continue
            for filename in ('result.json','inputs-per-present.jsonl','native-barriers.jsonl','policy-0.jsonl','policy-1.jsonl'):
                path=ROOT/match['source']/filename
                expected=next(n for n in native['games'] if n['source']==match['source'])['source_sha256'][str(path.relative_to(ROOT))]
                if sha256(path)!=expected:raise ValueError('native recording drift')
            hud_path=ROOT/match['source']/'hud-events.json'
            hud=json.loads(hud_path.read_text())
            evidence.append(dict(pair=label,source=match['source'],stage=match['stage'],
                role_to_policy=match['role_to_policy'],hud_events=hud,hud_sha256=sha256(hud_path),
                navigation=native_navigation(match) if label=='A5' else None))
    rows=[];details=[]
    for k,conditional in sampled.items():
        pair,stage,swap=k
        matches=[m for m in source['references'][pair]['matches'] if m['stage']==stage and (m['role_to_policy'][0]==1)==swap]
        original=[]
        for p in sorted(WORK.glob(f'{pair}-map{stage}-batch[0-9][0-9]/result.json')):
            g=json.loads(p.read_text());original.extend(r for r in g['games'] if r['swap']==swap)
        if len(original)!=6:raise ValueError('missing original ranking reference')
        n=summary([native_game(m) for m in matches]);o=summary([sim_game(g) for g in original]);b=base[k]['games'][0];w=warm[k]['games'][0];c=conditional['games'][0]
        rows.append(dict(pair=pair,stage=stage,swap=swap,native=n,original=o,
                         ground_fixed=sim_game(b),prefix_fixed=sim_game(w),clock_fixed=sim_game(c),
                         conditional=summary([sim_game(g) for g in conditional['games']])))
        match=matches[0];representative=next(g for g in native['games'] if g['source']==match['source'])
        # Compare release opportunities over the common simulated suffix;
        # the prefix is replayed to workers, not simulated as physics.
        trace=native_trace(match)
        native_routes=[dict(r) for r in representative['routes']]
        for role in (0,1):
            release=np.flatnonzero(np.diff(trace.actions[:,role,7],prepend=0)<0)
            native_routes[role]['release_inputs']=int(np.count_nonzero(release>=120))
        name=f'{pair}-map{stage}-side{int(swap)}'
        clock_trace=Path(clock)/(name+'-prefix-clock')/'trace-0.npz'
        with np.load(clock_trace) as data:sim_states=data['states']
        events=[]
        for event in c['events']:
            record=dict(event);frame=event['frame']
            for field in ('target','attacker'):
                role=event.get(field)
                if role in (0,1):record[field+'_position']=sim_states[frame,role,:3].tolist()
            events.append(record)
        details.append(dict(pair=pair,stage=stage,swap=swap,representative_source=match['source'],
            native=native_routes,ground=b['routes'],prefix=w['routes'],clock=c['routes'],
            ground_first_separation=first_separation(match,Path(baseline)/(name+'-ground')/'trace-0.npz',120),
            clock_first_separation=first_separation(match,Path(clock)/(name+'-prefix-clock')/'trace-0.npz',120),
            native_hud=next(g['hud_events'] for g in evidence if g['source']==match['source']),
            simulated_events=events))
    aggregates={}
    for pair in ('A5','R1','R2'):
        selected=[r for r in rows if r['pair']==pair]
        ng=[native_game(m) for m in source['references'][pair]['matches'] if pair!='A5' or m['stage']==3]
        cg=[sim_game(g) for k,v in sampled.items() if k[0]==pair for g in v['games']]
        aggregates[pair]=dict(native=summary(ng),conditional=summary(cg))
    vision_path=OUT/'vision-parity.json';vision=json.loads(vision_path.read_text())
    report=dict(schema='sim.route.diagnosis.v1',rows=rows,aggregates=aggregates,details=details,native_evidence=evidence,
        vision=vision,vision_sha256=sha256(vision_path),
        fixed_baselines_exactly_reproduced=reproduced,
        horizon_files_sha256={name:sha256(OUT/name) for name in ('early-horizon-before.json','early-horizon.json')},
        horizon_before=horizon_means(OUT/'early-horizon-before.json'),horizon_after=horizon_means(OUT/'early-horizon.json'),
        experiment_files=files,source_sha256=sha256(WORK/'sources.json'),native_inventory_sha256=sha256(OUT/'native.json'),
        prefix_checks=sum(g['prefix_action_checks'] for g in sampled.values()),
        prefix_action_max_error=max(g['prefix_action_max_error'] for g in sampled.values()),
        conditions=['First120 policy observations replayed; single observable state reset at120; no native state after120.',
            'Clock mode reuses only native packet timestamps, projects past SIMULATED state.',
            'Initial world paint/projectiles/phase unknown; own submerged patch and past velocity/weapon phase are estimates.',
            'A5 reuses first recorded opening per side. Seeds1..5 perturb the120 boundary, not an identified native stochastic distribution.',
            'Unobserved T1 seats excluded. Conditional results cannot replace the216-game predictive ranking baseline.'])
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    (OUT/'report.md').write_text(render(report))
    return report


def render(report):
    fmt=lambda v:'—' if v is None else str(v)
    wl=lambda s:f"{s['wins'][0]}:{s['wins'][1]} ({s['draws']})"
    out=['# 离线反例诊断：A5 Yagara / R1 / R2','',
        'A/B顺序分别为rush/high-ground、alpha/bravo。以下是固定历史开局与包时钟条件下的诊断干预，不是已识别的发射/重生/网络模型。',
        '原生只在自己的采样帧统计位置；停留用≤16帧间隔左保持估计。ZR时长/松开只代表涂地输入机会，不能观测原生真实涂地面积/时长。','',
        '| 对阵/图/出生侧 | 原生 A:B（平） | 原216局同分层 A:B（平） | 开局重建+采样时钟 A:B（平） | 固定起点赢家 地面→前缀→前缀+时钟 |',
        '| --- | ---: | ---: | ---: | --- |']
    for r in report['rows']:
        winners=' → '.join(fmt(r[k]['winner']) for k in ('ground_fixed','prefix_fixed','clock_fixed'))
        out.append(f"| {r['pair']}/{r['stage']}/{int(r['swap'])} | {wl(r['native'])} | {wl(r['original'])} | {wl(r['conditional'])} | {winners} |")
    out+=['','赢家0=A，1=B；侧=policy A在物理出生侧1时为1。T1只列原生实际观测侧，没有镜像伪造另一侧。',
          '',f"前缀逐次动作核对{report['prefix_checks']}次，最大差{report['prefix_action_max_error']}；原策略、配装、调用周期和超时均保留。",'',
          '| 固定代表局 | 角色 | 高台首次到达 原生/地面/条件 | 高台停留帧 原生/条件 | 高台ZR输入帧 原生/条件 | 首次可见帧 原生/条件 | 120帧后松ZR次数 原生/条件 |',
          '| --- | --- | --- | --- | --- | --- | --- |']
    for d in report['details']:
        for role in (0,1):
            n,b,c=(d[k][role] for k in ('native','ground','clock'))
            out.append(f"| {d['pair']}/{d['stage']}/{int(d['swap'])} | {'AB'[role]} | "+'/'.join(fmt(r['high_first_frame']) for r in (n,b,c))+f" | {n['high_dwell_sample_hold_frames']}/{c['high_dwell_sample_hold_frames']} | {n['high_ZR_sample_hold_frames']}/{c['high_ZR_sample_hold_frames']} | {fmt(n['first_visible_frame'])}/{fmt(c['first_visible_frame'])} | {n['release_inputs']}/{c['release_inputs']} |")
    out+=['','| 固定代表局 | 条件模拟首次位置误差>1单位 A/B | 原生自身HUD倒下：角色@帧 (XYZ) | 条件模拟倒下：角色@帧 (XYZ) |',
          '| --- | --- | --- | --- |']
    def event_label(role,frame,position):
        return f"{'AB'[role]}@{frame} ("+','.join(f'{v:.2f}' for v in position)+')' if position is not None else f"{'AB'[role]}@{frame} (unknown)"
    for d in report['details']:
        if d['pair']=='A5':continue
        native=[event_label(int(e['victim'].split('_')[-1])^int(d['swap']),e['detected_frame'],e['classification_position'])
                for e in d['native_hud'] if e['observer']==e['victim']]
        simulated=[event_label(e['target'],e['frame'],e.get('target_position')) for e in d['simulated_events'] if e['kind']=='knockdown']
        separation='/'.join(fmt(e['1']['frame'] if e['1'] else None) for e in d['clock_first_separation'])
        out.append(f"| {d['pair']}/{d['stage']} | {separation} | {'; '.join(native) or '无'} | {'; '.join(simulated) or '无'} |")
    out+=['','HUD位置是历史分类所用的采样位置，不是精确命中点；原生attacker/weapon保持unknown。模拟位置取事件帧双方状态。']
    out+=['','| 早期原输入短窗口（重置间隔120） | N30位置RMSE 前→后 | N120位置RMSE 前→后 |', '| --- | ---: | ---: |']
    for before,after in zip(report['horizon_before'],report['horizon_after']):
        out.append(f"| {before['pair']}/{before['stage']} | {before['metrics']['30_position_rmse']:.4f} → {after['metrics']['30_position_rmse']:.4f} | {before['metrics']['120_position_rmse']:.4f} → {after['metrics']['120_position_rmse']:.4f} |")
    out+=['','逐帧模拟NPZ含位置/身体朝向/相机/HP/墨量/形态/contact/存活/特殊、输入、可见性及网格占地；JSON包含首次超过1/3/5单位位置偏差的双方坐标、HP下降区间、原生HUD事件位置与模拟伤害/击倒事件。',
          '原生HUD事件的attacker/weapon仍unknown；不把sim归属当原生归属。最终网格百分比与原生有效计分域不同，分差只作诊断。','']
    out.extend('- '+c for c in report['conditions'])
    return '\n'.join(out)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,default=OUT/'ground-v2');p.add_argument('--prefix',type=Path,default=OUT/'prefix-v2')
    p.add_argument('--clock',type=Path,default=OUT/'clock-six');p.add_argument('--seeds',type=int,default=6)
    a=p.parse_args();r=build(a.baseline,a.prefix,a.clock,a.seeds)
    print(json.dumps(r['aggregates'],indent=2))


if __name__=='__main__':main()
