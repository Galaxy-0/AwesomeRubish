"""Compile D3-R numeric predictions and own-state native traces for the board.

Never embeds collision/source assets or raw memory. Generated page/data ignored.
"""
import json,math,sys
from pathlib import Path
from d3 import native_trace
from projectiles import augment

def compile_d3r(root,source):
    def read(p):return json.loads(source(p).read_text())
    plan=read('work/d3r/ideal-plan-v1.json');chain_path=root/'work/d3r/sequence-plan-v2.json';chain=read(chain_path)if chain_path.exists()else dict(points=[])
    point_inputs={p['id']:p for p in plan['points']+chain['points']};rows=[]
    paths=[root/f'work/d3r/ideal-fine-v2-stage{s}/result.json'for s in[1,2,3]]+[root/f'work/d3r/sequence-fine-v1-stage{s}/result.json'for s in[1,2,3]]
    for path in paths:
        if path.exists():rows.extend(read(path)['results'])
    report_path=root/'notes/d3r-calibration-20261022.json';cal=read(report_path)if report_path.exists()else None
    mechanics=read('notes/d3r-mechanics-20261022.json');mapping=read('notes/d3r-mapping-20261022.json');maps=[]
    for name in['Yunohana','District00','Yagara']:
        points=[]
        for p in point_inputs.values():
            if p['map']!=name:continue
            variants=[]
            for r in rows:
                if r['id']!=p['id']:continue
                events=r['budget']['events'];variants.append(dict(speed=r['speed'],style=r['style'],expected=r['expected'],worst=r['worst'],local=r['local_expected'],local_worst=r['local_worst'],spent=min(1.,r['budget']['spent']+.04),events=events,enemy=[[round(e['position'][0],1),round(e['position'][1],1),round(e['position'][2],1),round(e['expected'],4),round(e['worst'],4)]for e in r['enemy_results']],sampled_enemy_nodes=r['sampled_enemy_nodes'],reachable_enemy_nodes=r['reachable_enemy_nodes'],near_prior_mass=r['near_prior_mass'],mc_per_scenario=r['samples'],requires_precharge=False))
            if not variants:continue
            native=next((q for q in cal.get('points',[])if q['id']==p['id']and q['map']==name),None)if cal and len(p.get('sequence',[p['id']]))==1 else None
            path=p['native_flight'];model_path=[[round(v,2)for v in q]for q in path[::3]]
            if path[-1]!=path[::3][-1]:model_path.append([round(v,2)for v in path[-1]])
            points.append(dict(id=p['id'],hook_id=p.get('original_id',p['id']),source=p['source'],position=p['anchor'],landing=p['landing'],sequence=p.get('sequence',[p['id']]),anchors=p.get('sequence_anchors',[p['anchor']]),path=model_path,variants=variants,native=native,source_kind='measured-single'if'sequence'not in p else'predicted-chain',native_link_validated=False if'sequence'in p else True))
        maps.append(dict(id=name,points=points))
    # Controls are not the combat cohort. Labels explicitly separate passive
    # targets and direct-aim upper-bound versus the legacy stick experiments.
    clips=[];controls=read('work/d3r/passive-pilot-v3b/batch.json')['results']
    for r in controls:
        cid='d3r-control-'+r['map'];path=Path(r['artifact']).parent;clip=native_trace(root,source,path,cid,{'Yunohana':'原生上限 · 温泉峡谷 · 静止靶两刀','District00':'原生上限 · District00 · 静止靶两刀','Yagara':'原生上限 · Yagara · 静止靶两刀'}[r['map']]);clip['description']='直接瞄准测量夹具；静止靶不还击。原生21f蓄力、70＋35收尾，未改HP/位置/伤害。不是对练击杀率。';clip['ideal_operation_fixture']=True;clips.append(clip)
        witness=next(q for q in mechanics['passive_combo_controls']if q['map']==r['map'])
        for event in clip['annotations']:
            if event['kind']=='hit'and event['frame']>=witness['full_projectile']['frame']:
                event.update(label='满蓄70窗口 / HP确认',evidence='verified native full projectile and isolated passive control HP edge')
    light=mechanics['twenty_light3']['artifact']['path'];clip=native_trace(root,source,Path(light).parent,'d3r-control-light3','原生上限 · 20f档 · 三轻斩');clip.update(description='直接瞄准夹具、静止靶。到达确认20f后横斩，30f间隔三连；35＋35＋剩余30击倒。20f满蓄预蓄试验只出轻斩，未当作满蓄成立。',ideal_operation_fixture=True);clips.append(clip)
    if cal:
        for item in cal.get('replay_examples',[]):
            clip=native_trace(root,source,Path(item['artifact']).parent,item['clip_id'],item['label']);clip.update(description=item['description'],ideal_operation_fixture=True);clips.append(clip)
    compact_cal=None
    if cal:compact_cal={k:cal[k]for k in['native_trials','void_attempts','kills','attacker_down','points','rankings','metrics','fit','summary','model_native_rank_proven','threat_audit','replay_examples']}
    for clip in clips:
        clip['short_label']=clip['label'].replace('原生上限 · ','').replace(' · ',' / ')
        augment(root,source,clip)
    return dict(schema='showcase.d3r.v1',maps=maps,speeds=[20,40,60,129],scope='理想操作上限 · 本地直接瞄准夹具；仅比较声明动作库/行为分布。不是实战胜率或全图最优证明。',native_rank_proven=False,calibration=compact_cal,mapping=dict(casts=mapping['native_casts'],metrics=mapping['sweep_metrics']['confirmatory'],walls=mapping['confirmatory_by_kind']['sampled-wall']),mechanics=dict(birth_delays=mechanics['physical_birth_delay_frames'],twenty_full_supported=False,twenty_light3_native=True,reactive_threat=mechanics['exact_reactive52_controls']),search=dict(single_tactics=sum(len(p['sequence'])==1 for m in maps for p in m['points']),sequence_tactics=sum(len(p.get('sequence',[]))>1 for m in maps for p in m['points']),fine_variants=len(rows),sampled_nodes_per_tactic=12,mc_per_scenario=16,finite_only=True),limits=['从已发动、可出钩时开始，.52从R输入起反应；不计算开大发动暴露期。','全可达格粗筛，近场每路径12个敌位精算×8朝向×有效形态×3行为×MC16。空白格未精算。','连钩用≤3深度/束宽6的预测图，不是完整全局最优或原生连钩击杀率。','40f满蓄+轻斩的人形静止反应校准，不能外推到其它档/三轻斩/移动潜墨对手。','20f只比较实测三轻斩；满蓄预蓄控制未成立。']),clips
