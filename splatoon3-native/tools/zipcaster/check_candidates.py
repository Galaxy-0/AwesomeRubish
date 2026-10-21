#!/usr/bin/env python3
"""Independent D2C raw evidence audit, including full-health/clock/phase gates."""
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def main():
    count=0;steps_total=0
    def check(value,message):
        nonlocal count
        count+=1
        if not value:raise AssertionError(message)
    def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    report=json.loads((ROOT/'notes/d2c-20261021.json').read_text())
    check(report==json.loads((ROOT/'work/d2c/results.json').read_text()),'notes and page input identical')
    check(len(report['points'])==24 and len(report['maps'])==3,'24 selected points completed')
    check(all(1<=p['attempts']<=2 for p in report['points']),'at most two native attempts per point')
    check(len(report['attempts'])==sum(p['attempts']for p in report['points']),'no hidden attempts in denominators')
    for path,digest in report['source_provenance'].items():check(sha(ROOT/path)==digest,'current generator source '+path)
    check(sha(ROOT/report['selection']['path'])==report['selection']['sha256'],'selection unchanged')
    protect=json.loads((ROOT/'work/d2b/round2-world-build/provenance.json').read_text())
    for group in ['protected','original_module_sha256']:
        for path,digest in protect[group].items():check(sha(ROOT/path)==digest,'protected runtime '+path)
    for trial in report['attempts']:
        for path,digest in trial['source_sha256'].items():check(sha(ROOT/path)==digest,'closed raw '+path)
        raw=json.loads((ROOT/trial['artifact']).read_text());folder=ROOT/raw['artifacts']
        meta=json.loads((folder/'result.json').read_text());check(meta['driver_completed']and not meta['errors'],'closed valid driver '+trial['id'])
        rows=[json.loads(line)for line in (folder/'steps.jsonl').open()];steps_total+=len(rows)
        base=rows[0]['infos'];previous=None;clock_ok=True
        for row in rows:
            for player,info in row['infos'].items():
                delta=info['frame']-base[player]['frame'];dt=info['guest_time_ns']-base[player]['guest_time_ns']
                clock_ok&=abs(dt*60-delta*1_000_000_000)<=59 and info['phase']==1 and info['pixels_valid']==1
                if previous:clock_ok&=info['frame']-previous[player]['frame']==row['frames']
            previous=row['infos']
        check(clock_ok,'independent fixed60/presents/full-render check '+trial['id'])
        if trial['bound']:
            check(raw['bind']['state_native']in (2,3)and raw['bind']['bind_witness'],'native bind phase')
            check(math.dist(raw['bind']['anchor_world'],raw['point']['requested_anchor'])<=2.5,'native point neighbourhood')
            check(all(math.isfinite(v)for v in raw['bind']['hit_normal_world']),'native normal retained')
        if trial['full_light']:
            before=raw['charge_before']['player_1'];check(before['hp_valid']and before['hp']>=.999 and before['alive'],'full health before sword')
            hp_edges=[]
            for a,b in zip(rows,rows[1:]):
                ia,ib=a['infos']['player_1'],b['infos']['player_1']
                if b['infos']['player_0']['frame']>raw['charge_before']['player_0']['frame']and ia['hp']>ib['hp']:
                    hp_edges.append((b['label'],ia['hp'],ib['hp'],b['infos']['player_0']['frame']))
            full=next((e for e in hp_edges if e[0]=='c-full-release'and .68<e[1]-e[2]<.72),None)
            light=next((e for e in hp_edges if e[0]=='c-light-release'and e[1]>.15 and e[2]==0),None)
            check(full is not None and light is not None and full[3]<light[3],'native70 then light KO, not contact/ink-only KO')
            check(light[3]-raw['charge_before']['player_0']['frame']==trial['frames'],'charge-to-KO timing')
            check(trial['arrival_to_ko_frames']==light[3]-trial['arrival_native_frame'],'arrival-to-KO timing separated')
            check(trial['arrival_to_ko_frames']>=trial['frames'],'waiting/re-aim not hidden')
    for m in report['maps']:
        points=[p for p in report['points']if p['map']==m['id']];ids={p['id']for p in points}
        trials=[r for r in report['attempts']if r['id']in ids]
        check(len(points)==m['selected']==8,'eight points per map')
        check({p['region']for p in points}=={'center','central_high','west_lane','east_lane'},'region coverage')
        check(m['valid_bind_trials']==sum(t['valid_bind']for t in trials)and m['bind_success']==sum(t['bound']for t in trials),'trial binding denominator')
        check(m['combo_success']==sum(t['full_light']for t in trials)and m['valid_combo_trials']==sum(t['valid_combo']for t in trials),'trial combo denominator')
        check(m['points_combo']==sum(p['display_status']=='verified'for p in points),'unique-point combo denominator')
        check(m['fastest_full_light_frames']==min((p['frames']for p in points if p['frames']is not None),default=None),'fastest is actual measured point')
    for p in report['points']:
        raw=json.loads((ROOT/p['selected_attempt']).read_text())
        if p['landing']is not None:
            check(raw['after']['player_0']['referee_motion']['ground_contact']==4 and p['landing']==raw['after']['player_0']['position'],'landing has native ground-contact evidence')
        else:check(p['post_sword_position']is None or raw['after']['player_0']['referee_motion']['ground_contact']!=4,'unconfirmed landing remains unknown')
    check(len(report['armor']['controls'])==5,'three tracking probes plus bounded fixed-aim pair')
    for control in report['armor']['controls']:
        for path,digest in control['source_sha256'].items():check(sha(ROOT/path)==digest,'armor raw '+path)
        check(control['confirmed_body_damage']==(control['before']-control['after']>.001),'no armor-expiry-only hit promotion')
    check(report['armor']['status']=='undetermined','no unsupported universal reduction claim')
    check(sha(ROOT/report['trace_output']['path'])==report['trace_output']['sha256'],'recommended trace artifact')
    clips=json.loads((ROOT/report['trace_output']['path']).read_text())
    check(len(clips)==len(report['recommendations'])==3,'three evidence-backed practice picks')
    for r in report['recommendations']:
        p=next(p for p in report['points']if p['id']==r['id']);check(p['display_status']=='verified'and p['clip_id']==r['clip_id'],'recommendation must have native full-health combo')
    result=dict(passed=True,checks=count,point_attempts=len(report['attempts']),selected_points=len(report['points']),raw_steps=steps_total,
        armor_controls=len(report['armor']['controls']),offline_only=True,full_d2_passed=False)
    (ROOT/'work/d2c/check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
