"""D3 presentation compiler: numerical estimates and auditable native traces only."""
import json,math
from pathlib import Path
from derive_traces import COLUMNS,clean

DETAILS=['work/d3/fine-v2-stage1/result.json','work/d3/fine-v2-stage2/result.json','work/d3/fine-v2-resumed-stage3/result.json']

def native_trace(root,source,relative,clip_id,label):
    path=Path(relative);run=json.loads(source(path/'result.json').read_text());rows=[json.loads(l)for l in source(path/'steps.jsonl').open()]
    rs=next(i for i,r in enumerate(rows)if r['label'].endswith('-RS'));start=rows[rs-1]['infos']['player_0']['frame'];end=rows[-1]['infos']['player_0']['frame'];first=rows[rs];players=[]
    for n,who in enumerate(['alpha','bravo']):
        role=f'player_{n}';offset=first['infos']['player_0']['frame']-first['infos'][role]['frame'];states=[];events=[];aim_states=[];previous=[0]*6;held={}
        for r in rows[rs-1:]:
            info=r['infos'][role];f=info['frame']+offset;b=r['actions'][role]['buttons']
            motion=info.get('referee_motion',{});squid=motion.get('form_squid');form='human'if squid==0 else('submerged'if motion.get('ground_contact')==0 else'squid')if squid==1 else None
            if (f-start)%6==0 or r is rows[-1]:
                states.append([f,info.get('position_sample_frame',info['frame'])+offset,*[clean(v,2)for v in info['position']],clean(info.get('heading'),4),form,clean(info.get('hp')),bool(info.get('alive')),clean(info.get('ink'))])
                view=info.get('own_view',{})
                if view.get('valid'):aim_states.append([f,clean(view['yaw'],4),clean(view['pitch'],4)])
            for index,name in [(0,'ZR'),(2,'R'),(3,'RS'),(4,'B')]:
                if b[index]and not previous[index]:held[index]=f;events.append(dict(frame=f,type=name+'_down',evidence='recorded_input_edge'))
                if not b[index]and previous[index]:events.append(dict(frame=f,type=name+'_release',hold_frames=f-held.get(index,f),evidence='recorded_input_edge'))
            previous=list(b)
        players.append(dict(id=who,role=role,states=states,events=events))
        if run.get('ideal_operation_fixture'):players[-1]['aim_states']=aim_states
    annotations=[dict(frame=start+1,label='满槽按RS',kind='activate',evidence='recorded input')];prior=None;attack=False
    for event in players[0]['events']:
        if event['type']=='R_release':annotations.append(dict(frame=event['frame'],label='松R / 出钩输入',kind='hook_input',evidence='recorded release, effect phase sampled separately'))
    sensors=path/'sensors.jsonl'
    if (root/sensors).exists():
        for l in source(sensors).open():
            s=json.loads(l);phase=s['state_native'];f=s['native_frame']
            if not start<=f<=end:continue
            if phase!=prior:
                if phase==1:annotations.append(dict(frame=f,label='出钩',kind='hook',evidence='native SuperHook Shot'))
                if phase==2 and s['bind_witness']:annotations.append(dict(frame=f,label='挂住',kind='bind',evidence='native anchor+matrix'))
                if phase==3:attack=True
                if phase==0 and attack:annotations.append(dict(frame=f,label='到达',kind='arrive',evidence='first sampled Attack→Wait'));attack=False
            prior=phase
    for a,b in zip(rows,rows[1:]):
        f=b['infos']['player_0']['frame'];label2=b['label']
        if not start<=f<=end:continue
        if label2.endswith('-charge')and a['label']!=label2:annotations.append(dict(frame=f,label='开始蓄力',kind='charge',evidence='recorded ZR input start'))
        if label2.endswith('-B')and a['label']!=label2:annotations.append(dict(frame=f,label='B跳离输入',kind='jump',evidence='recorded B input'))
        if a['infos']['player_1']['hp']-b['infos']['player_1']['hp']>.65:annotations.append(dict(frame=f,label='命中70',kind='hit',evidence='native HP decrease70',target_ack_frame=b['infos']['player_1']['frame']+offset,raw_target_native_frame=b['infos']['player_1']['frame']))
        for n,who in enumerate(['alpha','bravo']):
            if a['infos'][f'player_{n}']['alive']and not b['infos'][f'player_{n}']['alive']:annotations.append(dict(frame=f,label='击倒.52'if n==1 else'水刀倒下',kind='down',evidence='native own alive edge',who=who))
    first_seen=None;history=run.get('reactive_history',[]);base=next((e['infos']['player_0']['frame']for e in run.get('events',[])if e['event']=='before-R'),None)
    if base is not None:
        first_visible=next((h['t']for h in history if h['visible']),None)
        if first_visible is not None:first_seen=base+first_visible-1;annotations.append(dict(frame=first_seen,label='被.52看见',kind='seen',evidence='filtered GeometricVision observer tick, not native camera sight flag'))
    if run.get('ideal_operation_fixture'):
        for event in annotations:
            if event['kind']=='hit':event.update(label='靶HP下降≥70',evidence='native HP readback, source not inferred from value alone')
        labels={'charge-start':('开始蓄力 / 持ZR','charge'),'full-release':('满蓄松ZR','slash'),'B-end':('B跳离输入结束','jump')}
        for event in run.get('events',[]):
            if event['event'] in labels:
                label2,kind=labels[event['event']];annotations.append(dict(frame=event['infos']['player_0']['frame'],label=label2,kind=kind,evidence='recorded fixture input boundary, not native hit'))
            elif event['event'].startswith('light-input'):
                annotations.append(dict(frame=event['infos']['player_0']['frame'],label='轻斩按ZR',kind='slash',evidence='recorded input boundary'))
        fired=next((h['t']for h in history if h['fired']),None)
        if base is not None and fired is not None:annotations.append(dict(frame=base+fired-1,label='.52首次开火输入',kind='fire',evidence='recorded filtered reactive action, not proof of hit'))
        for a,b in zip(rows,rows[1:]):
            delta=a['infos']['player_0']['hp']-b['infos']['player_0']['hp'];f=b['infos']['player_0']['frame']
            if start<=f<=end and .45<=delta<=.55:annotations.append(dict(frame=f,label='水刀HP −52',kind='damage',evidence='native own HP readback edge'))
        annotations=list({(e['frame'],e['kind'],e['label']):e for e in annotations if start<=e['frame']<=end}.values())
    annotations.sort(key=lambda a:a['frame'])
    return dict(schema='inklab.trace.v1',id=clip_id,label=label,short_label=label.split('·')[-1].strip(),source_kind='native_observation',map=run.get('point',run.get('d3_point',{})).get('map','Yunohana'),fps=60,start_frame=start,end_frame=end,stride=6,columns=COLUMNS,players=players,annotations=annotations,first_seen_frame=first_seen,description='原生控制夹具，QS57AP；步骤区分输入、SuperHook传感和HP确认。首次可见来自过滤观测，不是游戏原生视线标志。'+(' 本组唯一击倒案；防守脚本可见但未出枪，不能拿该单案证明顶住了.52火力。另看反杀片段。'if clip_id=='d3-native-ranked'else''),evidence=dict(raw_steps=str(path/'steps.jsonl'),result=str(path/'result.json')),position_semantics='Each player own state, beta native timestamp offset to alpha clock; six-present selection, quantized. No missing samples synthesized.')

def compile_d3(root,source):
    report=json.loads(source('notes/d3-model-v2-20261021.json').read_text());maps=[]
    calibration_path=root/'notes/d3-calibration-v2-20261021.json';calibration=json.loads(source(calibration_path).read_text())if calibration_path.exists()else None
    corrected=[]
    for stage in [1,2,3]:
        path=root/f'work/d3/fine-corrected-r3-stage{stage}/result.json'
        if path.exists():corrected.extend(m for m in json.loads(source(path).read_text())['maps'])
    for path in DETAILS:
        detail=json.loads(source(path).read_text())
        for m in detail['maps']:
            points=[]
            for p in m['points']:
                point=dict(id=p['id']+'-'+p['start_region']+'-'+str(len(p.get('sequence',[p['id']]))),hook_id=p['id'],source=p['source'],position=p['anchor'],landing=p['landing'],sequence=p.get('sequence',[p['id']]),anchors=p.get('sequence_anchors',[p['anchor']]),expected=p['expected_kill_probability'],worst=p['worst_behavior_kill_probability'],local=p['local_expected'],local_worst=p['local_worst'],spent=min(1,p['events'][-1]['spent']+.04),events=p['events'],enemy=[[round(e['position'][0],1),round(e['position'][1],1),round(e['position'][2],1),round(e['expected'],4),round(e['worst'],4)]for e in p['enemy_results']],native=None)
                if calibration and len(point['sequence'])==1:point['native']=next((x for x in calibration.get('points',[])if x['id']==p['id']and x['map']==m['id']),None)
                cp=next((c for cm in corrected if cm['id']==m['id']for c in cm['points']if c['id']==p['id']and c['start_region']==p['start_region']and c.get('sequence',[c['id']])==p.get('sequence',[p['id']])),None)
                if cp:
                    point['corrected']=dict(expected=cp['expected_kill_probability'],worst=cp['worst_behavior_kill_probability'],local=cp['local_expected'],local_worst=cp['local_worst'],spent=min(1,cp['events'][-1]['spent']+.04),events=cp['events'],feasibility_factor=cp['feasibility_factor'],enemy=[[round(e['position'][0],1),round(e['position'][1],1),round(e['position'][2],1),round(e['expected'],4),round(e['worst'],4)]for e in cp['enemy_results']])
                points.append(point)
            maps.append(dict(id=m['id'],points=points))
    clips=[]
    cohort=[('work/a6/d3-hint-duel-Yunohana-hook-0532-0-20261021-184326-866575','d3-native-win','原生D3 · 水刀射程外侧收尾'),('work/a6/d3-hint-duel-District00-hook-0585-3-20261021-190038-862174','d3-native-loss','原生D3 · 正面切入被.52反杀'),('work/a6/d3-hint-sequence-preaim-20261021-184230-425909','d3-native-chain','原生D3 · 预瞄后B跳离续钩')]
    cohort[0]=(cohort[0][0],cohort[0][1],'原生D3 · 对手射程外侧收尾')
    cohort.append(('work/a6/d3-hint-cal-v2-final-Yagara-hook-0448-0-20261021-203752-541376','d3-native-ranked','原生D3 · Yagara两刀收尾（对手未出枪）'))
    for path,cid,label in cohort:clips.append(native_trace(root,source,path,cid,label))
    controls=json.loads(source('notes/d3-reactive-controls-20261021.json').read_text())
    jointpath=root/'notes/d3-joint-20261021.json';joint=json.loads(source(jointpath).read_text())if jointpath.exists()else None
    return dict(schema='showcase.d3.v1',maps=maps,scale=report['scale'],calibration=calibration,joint=joint,controls=controls,has_corrected=len(corrected)==3,scope='有限模型估计 · 只对已枚举动作与声明分布成立；控制修正来自稀疏人形/静止反应夹具，不等于实战胜率。',model_calibrated=False),clips
