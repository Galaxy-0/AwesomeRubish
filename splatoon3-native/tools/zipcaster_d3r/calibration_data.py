"""Closed native cohort reduction. No outcome filtering beyond pre-R validity."""
import json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import PAT,sha

def projectiles(d,start,end,role):
    offset=d['initial_offsets'][role];births=[];speed={}
    for line in (Path(d['session'])/f'player-{role}/host.log').open(errors='replace'):
        m=PAT.search(line)
        if not m:continue
        f=int(m[1])+offset;vt=m[4]
        if not start<=f<=end or vt not in(['5c76df0','5c75510']if role==0 else['5c79398']):continue
        v=list(map(float,m[5].split(',')));norm=math.sqrt(sum(x*x for x in v));key=(m[3],vt);old=speed.get(key,-1.);threshold=.75 if vt=='5c76df0'else 2.7 if vt=='5c75510'else 2.8
        if m[2]=='setter_input'and norm>=threshold and old<threshold:
            births.append(dict(frame=f,kind={'5c76df0':'full','5c75510':'light','5c79398':'gun'}[vt],velocity=v,position=(lambda p:p if all(math.isfinite(x)and abs(x)<1000 for x in p)else None)(list(map(float,m[6].split(','))))))
        speed[key]=norm
    return births

def reduce(path):
    d=json.loads(path.read_text());assert d['calibration_eligible']and'freeze_after'in d
    point=d['point'];initial=next(e['infos']for e in d['events']if e['event']=='before-R');start=initial['player_0']['frame'];end=d['events'][-1]['infos']['player_0']['frame'];d['initial_offsets']=[0,start-initial['player_1']['frame']];born=projectiles(d,start,end,0);gun=projectiles(d,start,end,1);full=next((b for b in born if b['kind']=='full'),None);light=next((b for b in born if b['kind']=='light'),None);edges=[[],[]];last=[initial[f'player_{n}']['hp']for n in(0,1)];ranges=[];positions=[]
    for line in path.with_name('steps.jsonl').open():
        r=json.loads(line);infos=r['infos'];f=infos['player_0']['frame']
        if not start<f<=end:continue
        positions.append((f,infos['player_0']['position'],infos['player_1']['position']))
        if all(infos[f'player_{n}']['alive']for n in[0,1]):ranges.append(math.dist(infos['player_0']['position'],infos['player_1']['position']))
        for n in[0,1]:
            info=infos[f'player_{n}'];drop=last[n]-info['hp']
            if drop>1e-6:edges[n].append(dict(frame=f,native_frame=info['frame'],damage_hp=round(drop*100,5),remaining_hp=info['hp']))
            last[n]=info['hp']
    sensor=path.with_name('sensors.jsonl');binds=[];arrived=any(e['event']=='arrival'for e in d['events'])
    if sensor.exists():
        for line in sensor.open():
            row=json.loads(line)
            if row['process']==0 and start<row['native_frame']<=end and row['state_native']in[2,3]and row['bind_witness']:binds.append(row)
    history=d['reactive_history'];first_seen=next((r['t']for r in history if r['visible']),None);first_fired=next((r['t']for r in history if r['fired']),None);body_hit=bool(gun and any(18<=e['damage_hp']<=56 for e in edges[0]));full70=bool(full and any(65<=e['damage_hp']<=75 and full['frame']<=e['frame']<(light['frame']if light else end+1)for e in edges[1]));light_hit=bool(light and any(20<=e['damage_hp']<=40 and light['frame']<=e['frame']<=light['frame']+40 for e in edges[1]));pre_damage=sum(e['damage_hp']for e in edges[1]if full and e['frame']<full['frame'])
    return dict(id=point['id'],map=point['map'],stage=point['stage'],trial=d['trial'],split=point['split'],band=point['band'],global_expected=point['global_expected'],global_worst=point['global_worst'],artifact=str(path.relative_to(ROOT)),artifact_sha256=sha(path),kill=bool(d['outcome']['kill']),attacker_down=bool(d['outcome']['attacker_down']),bind_success=bool(binds),arrival_success=arrived,actual_anchor=binds[0]['anchor_world']if binds else None,anchor_error=float(np.linalg.norm(np.array(binds[0]['anchor_world'])-point['anchor']))if binds else None,initial_source=initial['player_0']['position'],initial_enemy=initial['player_1']['position'],enemy_heading=initial['player_1']['heading'],visible=first_seen is not None,fired=bool(gun),fired_input=first_fired is not None,first_seen_tick=first_seen,first_fired_tick=first_fired,gun_births=len(gun),body_hit=body_hit,min_distance=min(ranges)if ranges else None,full_birth=full,light_birth=light,full70=full70,light_hit=light_hit,pre_full_damage_hp=pre_damage,damage_edges=dict(alpha=edges[0],bravo=edges[1]),raw_sha256={str(Path(p).relative_to(ROOT)):h for p,h in d['raw_sha256'].items()},sensor_sha256=sha(sensor)if sensor.exists()else None,sequence_scope='single hook /40f full-light / stationary human .52 /R18 fromR; direct aim known target; no activation exposure.')

def collect(batches):
    attempts=[];valid={}
    for p in batches:
        b=json.loads(p.read_text())
        for r in b['results']:
            attempts.append(r)
            if r['eligible']:
                key=(r['map'],r['point'],r['trial'])
                if key in valid:raise ValueError('duplicate valid native outcome '+str(key))
                valid[key]=reduce(ROOT/r['artifact'])
    return sorted(valid.values(),key=lambda r:(r['stage'],r['id'],r['trial'])),attempts
