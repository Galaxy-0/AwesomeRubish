"""Native proficiency scorecards; unknown/censored observations stay explicit."""
import hashlib
import copy
import json
import math
from pathlib import Path

SCHEMA = 'arena.proficiency.v1'
ROOT = Path(__file__).resolve().parents[1]


def library_hashes():
    # Staging and merged modules have the same logical identity. Refuse an
    # ambiguous duplicate instead of silently choosing a different controller.
    hashes = {}
    for directory in (ROOT/'arena/lib', ROOT/'arena/lib_a6'):
        for path in sorted(directory.glob('*.py')):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if path.name in hashes and hashes[path.name] != digest:
                raise ValueError('staging/public module mismatch: '+path.name)
            hashes[path.name] = digest
    return hashes


def evaluation_hashes():
    paths=[ROOT/'upstream/dm/host/dmhost']+list((ROOT/'rl').glob('*.py'))
    # Hash local licensed assets without copying or publishing their contents.
    paths += [ROOT/'work/data/v720896/ExeFS/main',ROOT/'work/build/patched_v720896/main.patched.bin',
              ROOT/'work/build/patched_v720896/main.gates.tsv',ROOT/'work/build/patched_v720896/main.obs.tsv',
              ROOT/'work/data/v720896/RomFS/Pack/Params.pack.zs',
              ROOT/'work/data/v720896/RomFS/RSDB/WeaponInfoMain.Product.b30.rstbl.byml.zs']
    paths += [ROOT/'arena'/(name+'.py') for name in
              ('proficiency','control_process','proficiency_process','proficiency_worker',
               'policy','process','config','referee','referee_api','native_referee','visibility','geometry')]
    paths += [ROOT/'tests'/name for name in ('benchmark_a6.py','a6_lab.py','a6_metrics.py','a6_motion.py','probe_a6_combat.py')]
    paths += [ROOT/f'work/arena/maps/{stage}/{name}' for stage in ('Yunohana','District00','Yagara') for name in ('navigation.json','sight.npz')]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def approach_summary(rows):
    selected=[r for r in rows if r['scenario']=='approach' and r['status']=='measured']
    downs=sum(r['target_down'] for r in selected)
    reactions=[r['reaction_frames'] for r in selected if r.get('reaction_frames') is not None]
    return dict(approach_downs=downs,approach_trials=len(selected),
                approach_down_rate=downs/len(selected) if selected else None,
                approach_reaction_observations=len(reactions),
                approach_reaction_mean_frames=sum(reactions)/len(reactions) if reactions else None)


def scorecard(name, source_sha256, loadout, trials, *, library_sha256=None, evaluation_sha256=None,step_frames=None):
    """Each moving trial is a fixed window, NOT an attributed projectile hit."""
    rows = []
    for trial in trials:
        if trial['status'] != 'measured':
            rows.append(dict(scenario=trial['scenario'], distance=trial.get('distance'),
                             status=trial['status'], reason=trial.get('reason'), score=None))
            continue
        budget = trial['budget_frames']
        down = trial['down_frame']
        hit = bool(trial['native_damage_events']) if 'native_damage_events' in trial else trial['target_hp_loss'] > .001
        if not isinstance(budget, int) or budget < 1 or down is not None and not 0 <= down <= budget:
            raise ValueError('invalid trial interval')
        if trial['scenario'] == 'stationary':
            score = 100 * max(0., 1. - down / budget) if down is not None else 0.
        elif trial['scenario'] == 'lateral':
            score = 100. if hit else 0.
        else:
            # The approach must have an independently verified roll witness.
            if trial.get('roll_verified') is not True:
                rows.append(dict(scenario=trial['scenario'], status='unsupported',
                                 reason=trial.get('roll_reason') or 'roll action not independently verified', score=None,
                                 diagnostic=dict(reaction_frames=trial.get('reaction_frames'),target_down=down is not None,
                                                 target_hp_loss=trial['target_hp_loss'],time_to_down_frames=down),
                                 native_evidence=trial['native_evidence'],native_evidence_sha256=trial.get('native_evidence_sha256'),
                                 **{k:trial[k] for k in ('native_run_result','native_run_sha256','roll_proof','roll_calibration','attack_cycles','attack_frames','masked_movement_frames') if k in trial}))
                continue
            score = 100. if down is not None else 0.
        rows.append(dict(scenario=trial['scenario'], distance=trial.get('distance'),
                         nominal_distance=trial.get('nominal_distance'),repeat=trial.get('repeat'),
                         status='measured', budget_frames=budget, score=round(score, 3),
                         target_down=down is not None, time_to_down_frames=down,
                         right_censored=down is None, hit_window=hit,
                         reaction_frames=trial.get('reaction_frames'),
                         native_evidence=trial['native_evidence'],native_evidence_sha256=trial.get('native_evidence_sha256')))
        for key in ('native_run_result','native_run_sha256','released_attack_cycle','target_baseline','source_baseline','roll_proof','roll_calibration','distance_min','distance_max','attack_cycles','attack_frames','masked_movement_frames','time_remaining_at_start'):
            if key in trial:rows[-1][key]=trial[key]
    scores = [r['score'] for r in rows if r['score'] is not None]
    lateral=[r for r in rows if r['scenario']=='lateral' and r['status']=='measured']
    hit_windows=sum(r['hit_window'] for r in lateral)
    by_distance={}
    for row in lateral:
        key=str(row['nominal_distance']);group=by_distance.setdefault(key,dict(hits=0,trials=0,actual_distances=[]))
        group['hits']+=int(row['hit_window']);group['trials']+=1;group['actual_distances'].append(row['distance'])
    for group in by_distance.values():group['rate']=group['hits']/group['trials']
    return dict(schema=SCHEMA, policy=name, source_sha256=source_sha256,policy_step_frames=step_frames,
                library_sha256=library_hashes() if library_sha256 is None else library_sha256,
                evaluation_sha256=evaluation_hashes() if evaluation_sha256 is None else evaluation_sha256,
                loadout=loadout, trials=rows, measured=len(scores), total=len(rows),
                fixture=dict(stage_id=1,weapon=8000,shooter_team=0,clock='fixed60',target_gear='uniform quick_super_jump'),
                fixture_constraints='Shooter translation and R/RS/B/Y masked; camera, ZR main weapon and ZL refill allowed. Lateral windows accept one ZR press/release cycle. Approach target stops within 1.5 units or after passing the shooter. A live target below y=2.5 aborts the flat fixture; environmental downs cannot score. Raw and executed actions retained.',
                lateral_window_hits=hit_windows,lateral_window_trials=len(lateral),
                lateral_window_hit_rate=hit_windows/len(lateral) if lateral else None,
                lateral_by_distance=by_distance,
                **approach_summary(rows),
                aggregate_score=round(sum(scores)/len(scores), 3) if scores else None,
                definitions=dict(stationary='neutral-input target; native knockback retained; 100*(1-down_frames/budget), no down scores zero; censored time remains null',
                                 lateral='100 for >=.29 native HP drop in one fresh sample within the window (filters slow enemy-ink damage); not per-projectile accuracy',
                                 approach='100 for target down after matched-control calibration AND undamaged native boosted-reversal witness in this trial; unverified roll is unsupported',
                                 reaction='first attack input after first CURRENT visible target sample, in presents',
                                 aggregate='mean of measured trials only; compare identical coverage, distances, budgets and gear',
                                 attribution='native local HUD Down=1/HP only; unavailable=2 cannot score; no last-hit ownership inference'))


def write_card(path, card):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data=copy.deepcopy(card)
    for row in data['trials']:
        for key in ('native_evidence','native_run_result'):
            if row.get(key):
                proof=Path(row[key]);proof=proof if proof.is_absolute() else ROOT/proof
                row[key]=str(proof.resolve().relative_to(ROOT))
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')


def table(card):
    score=card['aggregate_score']
    lines = [f'策略 `{card["policy"]}`；源码 `{card["source_sha256"]}`。', '',
             f'调用间隔：{card.get("policy_step_frames") if card.get("policy_step_frames") is not None else "—"} present。', '',
             f'已测 {card["measured"]}/{card["total"]} 项；均分 {score if score is not None else "—"}；unsupported 不进入均分。', '',
             '| 场景 | 距离 | 状态 | 分数 | 击倒帧 / 截尾 | 窗口命中 | 开火周期 | 反应帧 |',
             '| --- | ---: | --- | ---: | --- | --- | ---: | ---: |']
    for row in card['trials']:
        distance = row.get('distance')
        distance = f'{distance:.2f}' if distance is not None else '—'
        ttk = row.get('time_to_down_frames')
        time = str(ttk) if ttk is not None else (f'>{row["budget_frames"]}' if row.get('right_censored') else '—')
        reaction=row.get('reaction_frames')
        hit=('是' if row['hit_window'] else '否') if row.get('status')=='measured' else '—'
        lines.append(f'| {row["scenario"]} | {distance} | {row["status"]} | {row["score"] if row["score"] is not None else "—"} | {time} | {hit} | {row.get("attack_cycles","—")} | {reaction if reaction is not None else "—"} |')
    lines+=['','横移采用单次ZR按/松周期的窗口命中率，不是逐弹丸准确率；每窗口90present。']
    for distance,group in sorted(card['lateral_by_distance'].items(),key=lambda item:float(item[0])):
        lines.append(f'- {distance}单位：{group["hits"]}/{group["trials"]}，{group["rate"]:.1%}。')
    if card['approach_trials']:
        reaction=card['approach_reaction_mean_frames']
        lines+=['',f'滑行接近目标倒下率：{card["approach_downs"]}/{card["approach_trials"]}（{card["approach_down_rate"]:.1%}）；反应均值 {f"{reaction:.1f}" if reaction is not None else "—"} present（{card["approach_reaction_observations"]}次有观测）。']
    for row in card['trials']:
        if row['status']!='measured':lines+=['',f'{row["scenario"]}：{row.get("reason") or row["status"]}。']
    lines+=['','静止靶中立输入，保留原生击退；240present内未倒下的用时为右截尾。',
            '测量原act在此夹具中的响应；零分也可能包含选择不攻击/等待战术状态的影响，不能据此单独归因擂台胜负。',
            '配装与完整分数定义、公共库/评测程序/原生轨迹SHA256见同名JSON。']
    return '\n'.join(lines)+'\n'


def matching_card(path, spec):
    """Report integration fails closed when policy source/loadout changed."""
    path = Path(path)
    if not path.is_file():
        return dict(status='unavailable', reason='run proficiency benchmark for this policy revision')
    card = json.loads(path.read_text())
    if card.get('schema') != SCHEMA or card.get('policy') != spec.name or card.get('source_sha256') != spec.source_sha256 or card.get('loadout') != spec.loadout or card.get('policy_step_frames')!=spec.step_frames or card.get('library_sha256') != library_hashes() or card.get('evaluation_sha256') != evaluation_hashes():
        return dict(status='unavailable', reason='scorecard source/loadout mismatch')
    return dict(status='available', scorecard=card, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def report_cards(specs,directory=None):
    """Optional report metadata never changes native validity or win scoring."""
    directory=Path(directory) if directory is not None else ROOT/'arena/results/proficiency'
    cards={}
    for spec in specs:
        try:cards[spec.name]=matching_card(directory/(spec.root.name+'.json'),spec)
        except (OSError,ValueError,KeyError,TypeError):
            cards[spec.name]=dict(status='unavailable',reason='invalid or incompatible scorecard')
    return cards


def report_markdown(cards):
    lines=['熟练度基准：同一策略源码版本在固定姿态训练夹具中的测量。','']
    for name,item in cards.items():
        lines.extend(['## '+name,''])
        if item['status']=='available':
            card=item['scorecard'];score=card['aggregate_score']
            lines.extend([f'已测 {card["measured"]}/{card["total"]} 项；均分 {score if score is not None else "—"}。','',table(card),''])
        else:lines.extend(['未提供匹配成绩：'+item['reason'],''])
    return '\n'.join(lines)


def attach_report(source,out,paths=None):
    source,out=Path(source),Path(out)
    if source.resolve()==out.resolve():raise ValueError('attachment must use a new output path')
    report=json.loads(source.read_text());names=report['policies'];hashes=report['source_hashes']
    paths=paths or [ROOT/'arena/results/proficiency'/(name+'.json') for name in names]
    if len(paths)!=len(names):raise ValueError('one scorecard per tournament policy required')
    cards={}
    for name,digest,path in zip(names,hashes,paths):
        try:
            card=json.loads(Path(path).read_text())
            if card['schema']!=SCHEMA or card['policy']!=name or card['source_sha256']!=digest or card['library_sha256']!=library_hashes() or card['evaluation_sha256']!=evaluation_hashes():
                raise ValueError('incompatible source/runtime')
            cards[name]=dict(status='available',scorecard=card,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
        except (OSError,ValueError,KeyError,TypeError):
            cards[name]=dict(status='unavailable',reason='no scorecard matching this tournament policy revision')
    report['proficiency_by_policy']=cards
    report['proficiency_scope']='post-hoc fixed-pose benchmark of matching policy source revisions'
    report['proficiency_source_report']=dict(path=str(source.resolve().relative_to(ROOT)),sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    out.with_suffix('.md').write_text(report_markdown(cards))
    return report


def merge_cards(paths):
    cards=[json.loads(Path(p).read_text()) for p in paths]
    if not cards:raise ValueError('no scorecards')
    first=cards[0]
    for card in cards:
        if any(card.get(k)!=first.get(k) for k in ('schema','policy','source_sha256','policy_step_frames','loadout','library_sha256','evaluation_sha256','definitions','fixture_constraints','fixture')):
            raise ValueError('incompatible scorecards')
    rows=[row for card in cards for row in card['trials']]
    proofs=[row['native_evidence'] for row in rows if row.get('native_evidence')]
    if len(proofs)!=len(set(proofs)):
        raise ValueError('duplicate native trial cannot increase the denominator')
    scores=[row['score'] for row in rows if row['score'] is not None]
    lateral=[row for row in rows if row['scenario']=='lateral' and row['status']=='measured']
    hits=sum(row['hit_window'] for row in lateral)
    by_distance={}
    for row in lateral:
        key=str(row['nominal_distance']);group=by_distance.setdefault(key,dict(hits=0,trials=0,actual_distances=[]))
        group['hits']+=int(row['hit_window']);group['trials']+=1;group['actual_distances'].append(row['distance'])
    for group in by_distance.values():group['rate']=group['hits']/group['trials']
    return dict(first,trials=rows,measured=len(scores),total=len(rows),
                lateral_window_hits=hits,lateral_window_trials=len(lateral),
                lateral_window_hit_rate=hits/len(lateral) if lateral else None,
                lateral_by_distance=by_distance,
                **approach_summary(rows),
                aggregate_score=round(sum(scores)/len(scores),3) if scores else None)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Combine sequential native proficiency scenarios')
    operation=parser.add_mutually_exclusive_group(required=True)
    operation.add_argument('--merge',type=Path,nargs='+')
    operation.add_argument('--tournament',type=Path,help='Attach profiles to a new copy of a completed tournament report')
    parser.add_argument('--scorecards',type=Path,nargs='+')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.tournament:attach_report(args.tournament,args.out,args.scorecards)
    else:
        card=merge_cards(args.merge)
        write_card(args.out,card);args.out.with_suffix('.md').write_text(table(card))
