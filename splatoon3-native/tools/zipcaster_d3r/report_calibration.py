"""Finalize fixed D3-R native cohort; train-only calibration and honest holdout.

Does not launch games or refit held-out outcomes. JSON contains numeric evidence,
not mesh/game assets. Before and after are evaluated on identical native cases.
"""
import json,sys,datetime
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.calibration_data import collect
from tools.zipcaster_d3r.analyze_direction import sha
from tools.zipcaster_d3.calibration_stats import spearman,kendall,metrics,fit_reliability,beta_interval
from rl.session import SAVE_HASH

def load(p):return json.loads((ROOT/p).read_text())
def rank(x,y):return dict(n=len(x),spearman=spearman(x,y),kendall_tau_b=kendall(x,y))
def main():
    batches=[ROOT/'work/d3r/calibration-v2/batch.json',ROOT/'work/d3r/calibration-setup-retry-v1/batch.json'];cases,attempts=collect(batches)
    assert len(cases)==54 and len({(c['id'],c['trial'])for c in cases})==54
    assert all(sum(c['map']==m for c in cases)==18 for m in ['Yunohana','District00','Yagara'])
    before=load('work/d3r/conditional-final-before-v1.json');motion=load('work/d3r/conditional-final-motion-v1.json');fit=load('work/d3r/motion-fit-final-v1.json');assert motion['motion_fit_sha256']==sha(ROOT/'work/d3r/motion-fit-final-v1.json')
    b={(c['point'],c['trial']):c for c in before['predictions']};a={(c['point'],c['trial']):c for c in motion['predictions']}
    assert set(b)==set(a)=={(c['id'],c['trial'])for c in cases}
    for data in [before,motion]:
        for p,h in data['source_sha256'].items():assert sha(ROOT/p)==h,p
    for c in cases:
        for pred in [a[c['id'],c['trial']],b[c['id'],c['trial']]]:
            assert pred['source_sha256']==c['artifact_sha256'] and pred['enemy_initial']==c['initial_enemy'] and pred['source_initial']==c['initial_source']
    assert all(t<2 for ident,t in fit['fit_keys']) and fit['uses_enemy_state_or_outcome']is False
    train=[c for c in cases if c['trial']<2];rho=fit_reliability([a[c['id'],c['trial']]['probability']for c in train],[c['kill']for c in train]);train_rate=np.mean([c['kill']for c in train]);met={}
    for split,predicate in [('train',lambda c:c['trial']<2),('held-out',lambda c:c['trial']==2),('all',lambda c:True)]:
        rr=[c for c in cases if predicate(c)];y=[c['kill']for c in rr]
        met[split]=dict(before=metrics([b[c['id'],c['trial']]['probability']for c in rr],y),motion_only=metrics([a[c['id'],c['trial']]['probability']for c in rr],y),after=metrics([a[c['id'],c['trial']]['probability']*rho for c in rr],y),constant_zero=metrics([0]*len(rr),y),constant_train_rate=metrics([train_rate]*len(rr),y))
    points=[];replays=[]
    for ident in sorted({c['id']for c in cases}):
        rr=[c for c in cases if c['id']==ident];assert len(rr)==3
        chosen=next((c for c in rr if c['kill']),next((c for c in rr if c['attacker_down']),rr[0]));clipid='d3r-duel-'+ident
        point=dict(id=ident,map=rr[0]['map'],n=3,kills=sum(c['kill']for c in rr),bind_success=sum(c['bind_success']for c in rr),rate_beta95=beta_interval(sum(c['kill']for c in rr),3),band=rr[0]['band'],global_expected=rr[0]['global_expected'],global_worst=rr[0]['global_worst'],matched_before=float(np.mean([b[c['id'],c['trial']]['probability']for c in rr])),matched_motion=float(np.mean([a[c['id'],c['trial']]['probability']for c in rr])),matched_after=float(np.mean([a[c['id'],c['trial']]['probability']*rho for c in rr])),clip_id=clipid)
        points.append(point);replays.append(dict(artifact=chosen['artifact'],clip_id=clipid,label=f"原生上限 · {ident} · {'击倒'if chosen['kill']else'未击倒'}",description=f"直接瞄准测量夹具 · 40f满蓄＋轻斩 · 试次{chosen['trial']}。.52看见后R18、有限转速；满槽只作夹具预填，不写HP/位置。此片{'击倒'if chosen['kill']else'未击倒'}，不能代表全点成功率。",kind='kill'if chosen['kill']else'loss'))
    counter=next(c for c in cases if c['id']=='District00-b0-c4'and c['attacker_down'])
    replays.append(dict(artifact=counter['artifact'],clip_id='d3r-counter-District00',label='原生上限 · 正面切入被.52反杀',description='直接瞄准夹具；同一个挂点的失败试次2。.52由过滤可见性触发R18/有限转速，原生枪弹体和HP边沿分开保留。成功片段不能替代反杀风险。',kind='counter'))
    native=[p['kills']/p['n']for p in points];rankings=dict(global_prior_vs_native=rank([p['global_expected']for p in points],native),matched_before=rank([p['matched_before']for p in points],native),matched_motion=rank([p['matched_motion']for p in points],native),matched_after=rank([p['matched_after']for p in points],native),held_out=rank([a[c['id'],c['trial']]['probability']*rho for c in cases if c['trial']==2],[int(c['kill'])for c in cases if c['trial']==2]))
    threat=dict(visible_trials=sum(c['visible']for c in cases),fired_trials=sum(c['fired']for c in cases),body_hit_trials=sum(c['body_hit']for c in cases),attacker_down_trials=sum(c['attacker_down']for c in cases),fired_with_min_range_under15_5=sum(c['fired']and c['min_distance']<=15.5 for c in cases),full70_trials=sum(c['full70']for c in cases),light_hit_trials=sum(c['light_hit']for c in cases),meaning='Gun birth, large attacker HP edge and KO separate; not all seen/fired cases are in gun range. Exact threat controls separately prove52+52. HP window is not direct native collision callback.')
    for p,h in load('work/d3r/aim-v1/protected.json').items():assert sha(ROOT/p)==h,p
    for p,h in load('work/d2b/round2-world-build/provenance.json')['original_module_sha256'].items():assert sha(ROOT/p)==h,p
    for p in [ROOT/'work/save_ref/save.dat',ROOT.parent/'splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat']:assert sha(p)==SAVE_HASH
    for r in attempts:
        d=load(r['artifact']);assert d['freeze_before']==d['freeze_after'];assert d['ideal_operation_fixture'] and d['clock']=='fixed60'
        for p,h in d['raw_sha256'].items():assert sha(p)==h,p
    for bp in batches:
        for p,h in json.loads(bp.read_text())['source_sha256'].items():assert sha(p)==h,p
    sources=[Path(__file__),ROOT/'tools/zipcaster_d3r/calibration_data.py',ROOT/'tools/zipcaster_d3r/conditional.py',ROOT/'tools/zipcaster_d3r/conditional_v2.py',ROOT/'tools/zipcaster_d3r/motion_calibration.py',ROOT/'tools/zipcaster_d3/calibration_stats.py']
    fine=[load(f'work/d3r/ideal-fine-v2-stage{s}/result.json')for s in[1,2,3]]+[load(f'work/d3r/sequence-fine-v1-stage{s}/result.json')for s in[1,2,3]];fine_rows=[r for f in fine for r in f['results']]
    search=dict(single_hooks=18,beam_sequences=9,variants=len(fine_rows),episodes=sum(b['episodes']for r in fine_rows for b in r['behaviors']),summed_job_seconds=sum(f['seconds']for f in fine),coarse='all reachable enemy cells x8 heading xvalid forms; range/threat heuristic only',fine='12 near-field enemy cells/tactic x8 heading xvalid form x3 behavior xMC16; near30u mass correction, outside treated zero',optimality='finite measured hook bank plus depth3/beam6; not continuous/global optimum')
    elevation={}
    for kind,flag in [('full','full70'),('light','light_hit')]:
        witnesses=[]
        for c in cases:
            born=c[kind+'_birth']
            if not c[flag]or not born or not born['position']:continue
            samples=[json.loads(line)for line in (ROOT/c['artifact']).with_name('steps.jsonl').open()]
            row=min(samples,key=lambda x:abs(x['infos']['player_0']['frame']-born['frame']));own=row['infos']['player_0'];target=row['infos']['player_1'];x,z=born['position'][0]-target['position'][0],born['position'][2]-target['position'][2]
            witnesses.append(dict(id=c['id'],trial=c['trial'],birth_frame=born['frame'],own_ack_frame=own['frame'],target_ack_frame=target['frame'],actor_above_target=own['position'][1]-target['position'][1],muzzle_above_target=born['position'][1]-target['position'][1],horizontal_distance=float(np.hypot(x,z)),velocity=born['velocity'],artifact=c['artifact']))
        elevation[kind]=dict(n=len(witnesses),actor_above_target_range=[min(v['actor_above_target']for v in witnesses),max(v['actor_above_target']for v in witnesses)],muzzle_above_target_range=[min(v['muzzle_above_target']for v in witnesses),max(v['muzzle_above_target']for v in witnesses)],witnesses=witnesses,scope='Observed HP-compatible hit windows and own/target feet nearest projectile birth. Not a continuous pitch/height boundary; target may be displaced by previous hit, not an independent stationary elevation scan.')
    for c in cases:c.update(probability_before=b[c['id'],c['trial']]['probability'],probability_motion=a[c['id'],c['trial']]['probability'],probability_after=a[c['id'],c['trial']]['probability']*rho)
    summary='54案7次击倒；全图先验与原生站位分布不同。自身轨迹标定只用训练0/1；18留出2次击倒，仍不足证明全图最高挂点。'
    out=dict(schema='inklab.d3r.calibration.v1',date='2026-10-22',full_d3r_passed=False,step4_cohort_completed=True,rate_scope='Ideal-operation upper-bound fixture; target-state oracle/direct native aim; not human or match win rate',native_trials=54,void_attempts=sum(not r['eligible']for r in attempts),kills=sum(c['kill']for c in cases),attacker_down=sum(c['attacker_down']for c in cases),cases=cases,elevation_evidence=elevation,points=points,rankings=rankings,metrics=met,fit=dict(rho=rho,train_keys=[[c['id'],c['trial']]for c in train],motion_points=len(fit['points']),motion_training_cases=len(fit['fit_keys']),motion_fit_sha256=sha(ROOT/'work/d3r/motion-fit-final-v1.json'),method='Training0/1 own free motion, no enemy/outcome used for trajectory. Bernoulli(p*rho) MLE on training0/1 outcomes only. Motion40f/full-light/existing singles only; scalar does not validate global grid or other operation bands.',holdout='trial2 initial-pose/outcomes never fit. Outcomes were visible in batch logs; this is fixed holdout, not a blinded test.'),summary=summary,model_native_rank_proven=False,threat_audit=threat,replay_examples=replays,search=search,attempts=attempts,protection=dict(original_host_modules_saves_unchanged=True,stale_freeze_baseline_equal_before_after=True,max_rooms=3,all_owned_hosts_closed=True),source_sha256={str(p.relative_to(ROOT)):sha(p)for p in sources},input_sha256={str(p.relative_to(ROOT)):sha(p)for p in batches+[ROOT/'work/d3r/conditional-final-before-v1.json',ROOT/'work/d3r/conditional-final-motion-v1.json',ROOT/'work/d3r/motion-fit-final-v1.json']},limits=['54 valid plus4 setup voids; only same fixed setup failures retried, no combat-loss resampling. v5 fixes atlas route projection before R; all post-R code identical to v4.','Native cohort human/stand/R18/40f full-light from R, not activation exposure or global 8heading/forms/moving behavior prior. Uniform atlas targets5..20u from attach,3poses/hook.','Nearest-floor/B model errors remain; learned motion is conditional on16 measured hooks, not novel-source/continuous-surface generalization. Other bands/chains remain kinematic extrapolation.','Exact .52 controller confirmed52+52/KO in2 isolated controls. In cohort16seen/14fired/3largeHPdrop/2KO; do not call all firing trials effective threats.','Native .52 fires after aim alignment even outside15.5; surrogate range gates fire. Timing/scatter, projectile curve/side spheres, knockback/dynamic collision remain approximate.','Flat seven-pitch sword scan and elevated native combos exist; dedicated full high/low stationary elevation-window grid incomplete. No universal high-ground hit-boundary claim.','20f full precharge unsupported by tested program;20f model uses verified light3. 40/60/129 both programs, only40 full-light cohort calibrated.','Finite heatmap remains uncalibrated global prior. Motion/rho after values evaluate matched initial cases only and are never silently multiplied into global heatmap.','New7/54 versus prior1/54 uses different hooks/poses/programs, not a controlled causal improvement ratio.','Best global/human kill-rate ranking not established. No further model fitting on held outcomes. No T1/S1 or policy/default/save modifications.'])
    stem=ROOT/'notes/d3r-calibration-20261022';stem.with_suffix('.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    lines=['# D3-R：理想操作上限分档校准（2026-10-22）','',summary,'','本地直接yaw/pitch夹具，靶位已知；未写HP/位置/伤害。不是玩家胜率，不是正式对战API。全图“最高击杀率挂点”仍未证明，`full_d3r_passed=false`。','', '| 地图 | 有效/作废 | 击倒 | 绑定/到达 |','|---|---:|---:|---:|']
    for m in ['Yunohana','District00','Yagara']:
        rr=[c for c in cases if c['map']==m];void=sum(not r['eligible']and r['map']==m for r in attempts);lines.append(f"| {m} | {len(rr)}/{void} | {sum(c['kill']for c in rr)}/{len(rr)} | {sum(c['bind_success']for c in rr)}/{sum(c['arrival_success']for c in rr)} |")
    lines+=['','高差补充为既有54案的观察包络，不是新开房或极限扫描：满蓄22个70窗口、轻斩10个大幅掉血窗口，其弹体生成附近双方脚点高差/枪口高差/水平距离逐案进入JSON的elevation_evidence。靶可能受前刀位移，不把它当静止高差命中边界。','', '每图6挂点×3预定初态。三图敌人均为人形、静止反应式.52，R18/有限转速；只从R出钩开始反应，不含RS发动暴露。54次全部有效绑定和到达，但仅22次70窗口、10次轻斩伤害窗口；各列可能有接触/剩余HP限制，不把所有掉血算成独立满额刀伤。','', '| 排名口径 | Spearman | Kendall τ-b |','|---|---:|---:|']
    for k,title in [('global_prior_vs_native','全图先验 vs18点原生率'),('matched_before','匹配初态/修正前'),('matched_motion','仅自身轨迹修正'),('matched_after','训练轨迹+ρ修正（含训练点）'),('held_out','18留出初态/修正后')]:
        v=rankings[k];lines.append(f"| {title} | {v['spearman']} | {v['kendall_tau_b']} |")
    lines+=['','全图先验是全格/8朝向/形态/三行为；原生是每挂点3个人形静止初态，两者分母不同。含训练点的相关不代表泛化，留出按试次而非新挂点。每点3次的Beta(1,1)95%区间保留在JSON。','', '| 留出18案 | MAE | Brier | 平均预测 | 实际 |','|---|---:|---:|---:|---:|']
    for k,title in [('before','原近似轨迹'),('motion_only','训练自身轨迹'),('after','轨迹+训练ρ'),('constant_zero','全零基线'),('constant_train_rate','训练击倒率常数基线')]:
        v=met['held-out'][k];lines.append(f"| {title} | {v['mae']:.6f} | {v['brier']:.6f} | {v['mean_predicted']:.6f} | {v['observed']:.6f} |")
    lines+=['',f"第二轮修正：只用试次0/1中无≥18HP受击冲量且100f末高度稳定的自身位置，16点32条轨迹；无敌人状态/结果拟合。ρ={rho:.3f}仅从训练36案拟合，不改热图。18留出2个正例，误差下降仍不等于可靠最高排名。留出日志可见，不称盲测。",'',f".52威胁审计：16案看见，14案弹体开火，3案水刀明显掉血，2案水刀倒下。近距独立控制均52→KO（35f/70f）。射程外开火不算命中；原生脚本射程外也会开火而模型有限程发射，属于尚存近似。",'',f"有限搜索：18单钩+9预测连钩，189合法速度/招式变体，{search['episodes']:,}次MC回合，分任务计算时间合计{search['summed_job_seconds']:.1f}s（不是墙钟）。每挂点精算12敌位，其余空白不插值为概率；深度3/束宽6非全局穷尽。20档三轻斩；40/60/129两种招式。",'','停止边界：已获得绑定与机械执行进展，但模型仍不能证明全图最优。两轮有限模型修正到此，不按留出结果继续调参。页面展示有限模型、原生成功/失败、概率口径与证据，不包装成实战榜。完整高差命中网格、连续表面最优、连钩原生战斗概率仍未完成。','', '4个前置作废原件保留、只补原计划同一案例，战斗失败不重抽。v5只修导航图投影/摆位，R后代码与v4一致。58个尝试116个自建host已结束，分批上限3房；原宿主/模块/存档SHA与stale冻结基线前后相同。T1/S1未恢复，策略目录未改。','', '原件与SHA、每次HP边沿/实际弹体/绑定/概率、每点区间与回放引用见同名JSON；work原件保留，不提交资源/派生网格/生成页。']
    stem.with_suffix('.md').write_text('\n'.join(lines)+'\n');print(json.dumps(dict(kills=out['kills'],rankings=rankings,held=met['held-out'],search=search),indent=2))
if __name__=='__main__':main()
