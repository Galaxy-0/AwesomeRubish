#!/usr/bin/env python3
"""D2C numeric evidence and presentation records from closed point attempts."""
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.zipcaster.export import trace
NAMES=dict(center='中路',central_high='高台',west_lane='西侧通路',east_lane='东侧通路')


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def armor_controls():
    controls=[]
    for result_path in sorted((ROOT/'work/a6').glob('d2-c-armor-*/result.json')):
        result=json.loads(result_path.read_text())
        if not result.get('driver_completed')or not result.get('post_sensor_sha256'):continue
        directory=result_path.parent;commands=[json.loads(line)for line in (directory/'commands.jsonl').open()]
        get=lambda label:next(c['infos']for c in commands if c['command']['label']==label)
        before=get('armor-before');release=get('armor-release-before');after=get('armor-after')
        native=[json.loads(line)for line in (directory/'sensors.jsonl').open()];changes=[];previous=None;contacts=[]
        for r in native:
            if r['process']!=0 or r['native_frame']<before['player_0']['frame']:continue
            signature=(r['body_hp_native'],r['armor_hp_native'],r['armor_flags_native'],r['collision_mask_21d_native'],r['state_native'])
            if signature!=previous:
                changes.append({k:r[k]for k in ['native_frame','body_hp_native','armor_hp_native','armor_flags_native','collision_mask_21d_native','state_native']});previous=signature
        refs={str(p.relative_to(ROOT)):sha(p)for p in [result_path,directory/'commands.jsonl',directory/'steps.jsonl',directory/'sensors.jsonl',directory/'tested-armor_candidates.py',directory/'tested-validate_candidates.py']}
        for i in (0,1):
            log=Path(result['session'])/f'player-{i}/host.log';refs[str(log.relative_to(ROOT))]=sha(log)
        controls.append(dict(id=directory.name,delay=result['release_delay'],aim_mode=result.get('aim_mode','track-current'),
            before=before['player_0']['hp'],after=after['player_0']['hp'],
            confirmed_body_damage=before['player_0']['hp']-after['player_0']['hp']>.001,
            release_actor0_frame=release['player_0']['frame'],release_target_position=release['player_0']['position'],
            shooter_view_at_release=release['player_1']['own_view'],arrival_after_release=after['player_0']['position'],
            native_changes=changes,source_sha256=refs))
    return dict(status='undetermined',controls=controls,
        interpretation='Tracking early probes did not settle elevation before release. Fixed future-aim pair is recorded separately. Body damage confirms a hit; armor300-to0 alone is not a confirmed absorption event because natural expiry also clears it. No universal multiplier or invulnerability claimed.')


def classify(raw):
    bind=raw['bind'];before=raw['charge_before'];after=raw['after']
    normal_match=None
    if bind:
        normal_match=sum(a*b for a,b in zip(bind['hit_normal_world'],raw['point']['normal']))
    # Native swept-contact normals differ from extracted triangle normals at
    # edges. There is no native triangle ID. Certify the measured point's
    # neighbourhood, retain both normals, never invent same-triangle proof.
    bound=bool(bind and raw['requested_anchor_error']<=2.5)
    valid_combo=bool(bound and before and before['player_1']['hp']>=.999)
    decreases=raw['hp_decreases']
    labels={}
    if before:
        with (ROOT/raw['artifacts']/'steps.jsonl').open()as source:
            for line in source:
                r=json.loads(line);labels[r['infos']['player_0']['frame']]=r['label']
    sword=[dict(d,label=labels.get(d['actor0_ack']))for d in decreases if before and d['actor0_ack']>before['player_0']['frame']]
    full_hit=next((d for d in sword if d['label']=='c-full-release'and .68<d['hp_before']-d['hp_after']<.72),None)
    ko=bool(valid_combo and after and not after['player_1']['alive'])
    ko_event=next((d for d in sword if full_hit and d['hp_after']==0 and d['hp_before']>.15 and d['label']in ['c-light','c-light-release']and d['actor0_ack']>full_hit['actor0_ack']),None)
    full_light=bool(ko and full_hit and ko_event)
    arrival=None;seen_attack=False
    if bind:
        with (ROOT/raw['artifacts']/'sensors.jsonl').open()as source:
            for line in source:
                r=json.loads(line)
                if r['process']!=0 or r['native_frame']<bind['native_frame']:continue
                seen_attack|=r['state_native']==3
                if seen_attack and r['state_native']==0:arrival=r['native_frame'];break
    if raw['before']is None or (bind is None and raw['fixture_stage']in ['aim','target_precondition']):return dict(status='incomplete',reason='摆位／瞄准／满血前置未完成',bound=False,valid_bind=False,valid_combo=False,full_light=False,ko=False)
    if not bind:reason='没有本次原生绑定见证';status='failed'
    elif not bound:reason='绑定到旁面／实际锚点偏离预定点';status='failed'
    elif not valid_combo:reason='绑定成功，满血静止靶前置未完成';status='partial'
    elif full_light:reason='点位邻域绑定，满血蓄斩70＋轻斩击倒';status='verified'
    elif ko:reason='满血击倒，但不是已确认70＋35两刀';status='partial'
    else:reason='绑定成功，满血两刀未击倒';status='failed'
    return dict(status=status,reason=reason,bound=bound,normal_dot=normal_match,valid_bind=True,
        valid_combo=valid_combo,full_light=full_light,ko=ko,arrival_native_frame=arrival,
        arrival_to_ko_frames=ko_event['actor0_ack']-arrival if full_light and arrival else None)


def main():
    selection=json.loads((ROOT/'work/d2c/selection.json').read_text());runs=[];points=[]
    for point in selection['points']:
        attempts=[]
        for path in sorted((ROOT/'work/a6').glob(f'd2-c-{point["id"]}-a*-*/point.json')):
            raw=json.loads(path.read_text());verdict=classify(raw)
            # Runtime source is the copy captured at Lab construction. Early
            # controller versions also listed the mutable entry path; archive
            # identity always comes from tested-validate_candidates.py/result.
            directory=ROOT/raw['artifacts'];runtime=json.loads((directory/'result.json').read_text())
            tested=directory/'tested-validate_candidates.py'
            entry=next(v for k,v in runtime['code_sha256'].items()if k.endswith('/validate_candidates.py'))
            assert sha(tested)==entry
            refs=dict(raw['source_sha256']);refs.pop('tools/zipcaster/validate_candidates.py',None)
            refs[str(tested.relative_to(ROOT))]=entry
            refs[str(path.relative_to(ROOT))]=sha(path)
            for name,digest in refs.items():assert sha(ROOT/name)==digest,name
            run=dict(id=point['id'],attempt=raw['attempt'],**verdict,raw_outcome=raw['outcome'],
                requested_anchor_error=raw['requested_anchor_error'],observed_landing_error=raw['observed_landing_error'],
                full_health_before_charge=raw['charge_before']['player_1']['hp']if raw['charge_before']else None,
                frames=raw['charge_to_ko_frames'],artifact=str(path.relative_to(ROOT)),source_sha256=refs)
            attempts.append((run,raw));runs.append(run)
        if not attempts:continue
        # Best outcome is explicit; every attempt remains in the denominator
        # table. Selecting a best trial is not a statistical success estimate.
        chosen,raw=max(attempts,key=lambda a:(a[0]['full_light'],a[0]['bound'],a[0]['valid_combo'],a[0]['ko'],a[0]['valid_bind'],-(a[0]['frames']or 100000)))
        bind=raw['bind'];arrival=raw['attached'];after=raw['after'];actual_source=raw['before']['player_0']['position']if raw['before']else raw['point']['source']
        target=(raw['charge_before']or raw['before']or{}).get('player_1',{}).get('position',point['target'])
        frames=chosen['frames']if chosen['full_light']else None
        grounded=bool(after and after['player_0'].get('referee_motion',{}).get('ground_contact')==4)
        actual_landing=after['player_0']['position']if grounded else None
        points.append(dict(id=point['id'],map=point['map'],region=point['region'],
            label=NAMES[point['region']]+' · '+point['id'].split('-')[-1],display_status=chosen['status'],
            outcome=chosen['reason'],attempts=len(attempts),sample_scope=f'{len(attempts)}次夹具尝试 · 满血前置单独核验',
            requested_anchor=point['requested_anchor'],requested_normal=point['normal'],anchor=bind['anchor_world']if bind else None,
            normal=bind['hit_normal_world']if bind else None,source=actual_source,target=target,
            arrival_pose=arrival['player_0']['position']if arrival else None,landing=actual_landing,
            post_sword_position=after['player_0']['position']if after else None,
            landing_error=math.dist(actual_landing,point['estimated_landing'])if actual_landing else None,
            arrival_semantics='arrival_pose: after90 R-release presents, may hang. landing: post-sword foot sample only when native ground_contact=4, otherwise null. Arrival-to-KO starts at first sampled Attack-to-Wait, not necessarily ground contact.',
            frames=frames,arrival_to_ko_frames=chosen.get('arrival_to_ko_frames'),view_percent=point['view_percent'],exposure_fraction=point['approach_exposure_fraction'],
            selected_attempt=chosen['artifact'],
            caveat=chosen['reason']+'。两刀帧数从蓄力开始；到达→KO另列且含观察等待/重瞄。到达位置可能仍挂墙；每点1–2次，非实战安全或成功概率。'+('灰色仅为夹具未完成，不能判挂面失败。'if chosen['status']=='incomplete'else'')))
    maps=[]
    for name in ['Yunohana','District00','Yagara']:
        selected=[p for p in selection['points']if p['map']==name];ps=[p for p in points if p['map']==name];ids={p['id']for p in ps};rs=[r for r in runs if r['id']in ids]
        maps.append(dict(id=name,selected=len(selected),completed_points=len(ps),attempts=len(rs),
            valid_bind_trials=sum(r['valid_bind']for r in rs),bind_success=sum(r['bound']for r in rs),
            valid_combo_trials=sum(r['valid_combo']for r in rs),combo_success=sum(r['full_light']for r in rs),
            setup_failed=sum(r['status']=='incomplete'for r in rs),
            points_bound=sum(any(r['bound']for r in rs if r['id']==p['id'])for p in ps),
            points_combo=sum(p['display_status']=='verified'for p in ps),
            fastest_full_light_frames=min((p['frames']for p in ps if p['frames']is not None),default=None),
            fastest_arrival_to_ko_frames=min((p['arrival_to_ko_frames']for p in ps if p['arrival_to_ko_frames']is not None),default=None)))
    recommendations=[];clips=[]
    texts=[('Yunohana-hook-0532','西侧高柱下落斩','队友压住中路时，从高台挂西侧高柱，边落边纵斩，再横斩收侧路。'),
        ('District00-hook-0585','东侧墙点，落地补刀','从右路内侧挂高墙，纵斩压外侧通路，落地后横斩收尾，别在墙上久留。'),
        ('Yagara-hook-0821','高台前矮墙起跳','上钩后小跳，再用纵斩接横斩压高台；本轮只验证了这套输入，别直接省掉小跳。')]
    for ident,title,description in texts:
        p=next((p for p in points if p['id']==ident and p['display_status']=='verified'),None)
        if not p:continue
        run=(ROOT/p['selected_attempt']).parent;clip=trace(run,'c');clip.update(id='zipcaster-batch-'+p['map'].lower(),label=p['map']+' · '+title,short_label=title,
            description=f'{description} 静止满血靶；蓄力→KO {p["frames"]}f，到达→KO {p["arrival_to_ko_frames"]}f（含观察等待/重瞄），非最短。')
        p['clip_id']=clip['id'];clips.append(clip)
        recommendations.append(dict(id=ident,map=p['map'],title=title,description=description,frames=p['frames'],arrival_frames=p['arrival_to_ko_frames'],clip_id=clip['id']))
    trace_path=ROOT/'work/d2c/traces/recommended.json';trace_path.parent.mkdir(parents=True,exist_ok=True)
    trace_path.write_text(json.dumps(clips,ensure_ascii=False,separators=(',',':'))+'\n')
    result=dict(schema='inklab.d2c.report.v1',date='2026-10-21',maps=maps,points=points,attempts=runs,armor=armor_controls(),recommendations=recommendations,
        trace_output=dict(path=str(trace_path.relative_to(ROOT)),sha256=sha(trace_path)),
        full_d2_passed=False,ceiling='known_undetermined_deferred_by_user',
        binding_gate='Native bind witness plus world anchor within2.5u of selected point. Point-neighbourhood validation, not same mesh-triangle proof. Both normals retained; swept contact normal differs near edges; actor ID alone insufficient.',
        combo_gate='nearby expected anchor, 100HP before charge, native70 decrease then later KO; prior special contact damage excluded',
        rate_semantics='Observed trial fractions and unique-point counts at N1–2. Not a real-combat success probability.',
        selection=dict(path='work/d2c/selection.json',sha256=sha(ROOT/'work/d2c/selection.json')),
        source_provenance={str(p.relative_to(ROOT)):sha(p)for p in [Path(__file__).resolve(),ROOT/'tools/zipcaster/validate_candidates.py',ROOT/'tools/zipcaster/armor_candidates.py',ROOT/'tools/zipcaster/sensor.h']})
    (ROOT/'work/d2c/results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'notes/d2c-20261021.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(maps,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
