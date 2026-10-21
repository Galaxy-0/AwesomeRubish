#!/usr/bin/env python3
"""D2C coordinator fixtures. Ordinary inputs, private read-only sensors, <=3 rooms.

Each point uses fresh hosts: no 180s match exhaustion or target respawn bias.
Failures in placement are not converted into native bind failures.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import traceback
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
from probe import open_lab,NativeSession
from serve import run
from decode_sensors import SNAP,decode
from sensor_evidence import reduce_group
import rl.session as session_module
from arena.lib.atlas import MapAtlas
from tools.zipcaster.surfaces import load_surfaces,first_hit
import numpy as np

HOST=ROOT/'work/d2b/round2-world-build/dmhost-sensors'
MODULES=HOST.parent/'modules'
REGIONS=['center','central_high','west_lane','east_lane']


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):Path(p).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def select(args):
    source=ROOT/'work/d2/map-analysis-full.json';data=json.loads(source.read_text());chosen=[]
    for stage,m in enumerate(data['maps'],1):
        atlas=MapAtlas.load(stage);used=[]
        @lru_cache(None)
        def snap(position):return atlas.points[atlas.nearest(position)]
        for region in REGIONS:
            pool=[]
            for c in m['candidates']:
                target=next(t for t in c['targets']if t['target']==region)
                if target['landing_distance']is None or not 4<=target['landing_distance']<=24:continue
                if any(f in c['material_flags']for f in ['KeepOut','Fence','SuperHookCantBind']):continue
                for a in c['approaches']:
                    src=snap(tuple(a['source']));dst=snap(tuple(target['position']))
                    if math.dist(src,a['source'])>3 or math.dist(dst,target['position'])>3:continue
                    delta=[c['anchor'][i]-src[i]for i in range(3)];pitch=math.atan2(delta[1]-1.1,math.hypot(delta[0],delta[2]))
                    if not -.8<pitch<.83:continue
                    exposure=sum(e['visible_sample_fraction']for e in a['potential_exposure'])/len(a['potential_exposure'])
                    score=100*target['full_plus_light_geometry_candidate']+(c['landing_view_percent']or 0)-12*exposure-.12*a['eye_to_anchor']
                    pool.append((score,c,a,target,src,dst,exposure))
            count=0
            for score,c,a,target,src,dst,exposure in sorted(pool,key=lambda r:-r[0]):
                if any(math.dist(c['anchor'],v)<3.5 for v in used):continue
                used.append(c['anchor']);count+=1
                chosen.append(dict(id=c['id'],map=m['id'],stage=stage,region=region,
                    requested_anchor=c['anchor'],normal=c['normal'],estimated_landing=c['landing_estimate'],
                    source=list(src),target=list(dst),named_target=target['position'],
                    source_region=a['start'],view_percent=c['landing_view_percent'],
                    approach_exposure_fraction=exposure,static_full_light=target['full_plus_light_geometry_candidate'],score=round(score,4),
                    source_snap_distance=math.dist(src,a['source']),target_snap_distance=math.dist(dst,target['position']),
                    material_flags=c['material_flags']))
                if count==2:break
            if count!=2:raise ValueError(f'not enough distinct eligible candidates for {m["id"]} {region}')
    write(args.selection,dict(schema='inklab.d2c.selection.v1',source=str(source.relative_to(ROOT)),
        source_sha256=sha(source),points=chosen,criteria='Two distinct points per named region, prefer full-light static; fallback <=24u, exclude Fence/KeepOut, view minus exposure/range. Snapped setup goals are disclosed, not native reachability.'))
    print(json.dumps([dict(map=m['id'],points=[p['id']for p in chosen if p['map']==m['id']])for m in data['maps']],indent=2))


def read_sensors(session):
    image=(ROOT/'work/d2b/main.bin').read_bytes();output=[]
    for player in (0,1):
        base=0;key=None;group=[]
        with (Path(session)/f'player-{player}/host.log').open(errors='replace')as stream:
            for line in stream:
                if 'D2B_SENSOR readonly=1 main='in line:base=int(line.split('main=')[1].split()[0],16)
                match=SNAP.search(line)
                if not match or match[2]not in ('superhook','surface_matrix','component_3ae8','damage','component_11cc0'):continue
                row=decode(match,player,base,image);newkey=row['native_frame']
                if key!=newkey:
                    item=reduce_group(group)
                    if item:output.append(item)
                    group=[];key=newkey
                group.append(row)
        item=reduce_group(group)
        if item:output.append(item)
    return output


def point(args):
    selection=json.loads(args.selection.read_text());p=next(p for p in selection['points']if p['id']==args.point)
    # The activation/zip contact may hurt a nearby dummy before the sword.
    # Preserve selected anchors, but move the source to another documented
    # eligible approach when source and target would overlap.
    if math.dist(p['source'],p['target'])<9 or args.attempt==2:
        data=json.loads((ROOT/'work/d2/map-analysis-full.json').read_text())
        candidate=next(c for m in data['maps']for c in m['candidates']if c['id']==p['id'])
        atlas=MapAtlas.load(p['stage']);alternatives=[]
        for a in candidate['approaches']:
            position=list(atlas.points[atlas.nearest(a['source'])])
            if math.dist(position,p['target'])>=9 and math.dist(position,a['source'])<3 and (args.attempt==1 or math.dist(position,p['source'])>3):
                alternatives.append((a['eye_to_anchor'],position,a['start']))
        if alternatives:
            _,position,region=min(alternatives)
            p=p|dict(requested_source=p['source'],source=position,source_region=region,source_adjustment='Avoid activation contact with static target; alternate existing candidate approach')
        else:
            tri,_,_,_=load_surfaces(ROOT/f'work/arena/maps/{p["map"]}')
            origin=p['source'];normal=np.array(p['normal']);anchor=np.array(p['requested_anchor'])
            if np.dot(np.array(origin)-anchor,normal)<0:normal=-normal
            local=sorted((q for q in atlas.points if abs(q[1]-origin[1])<1.5 and 10<=math.dist(q,p['target'])and math.dist(q,origin)<=18),key=lambda q:math.dist(q,origin))
            for q in local:
                eye=np.array(q)+[0,1.1,0];delta=eye-anchor
                if not 3<np.linalg.norm(delta)<34 or np.dot(delta,normal)<.3:continue
                if abs(math.atan2(delta[1],math.hypot(delta[0],delta[2])))>.82:continue
                hit=first_hit(tri,eye,anchor)
                if hit is not None and np.linalg.norm(hit[1]-anchor)<.75:
                    p=p|dict(requested_source=origin,source=list(q),source_region='separated-local-node',source_adjustment='Native target kept stationary; local atlas node >=10u away, first static hit at selected wall. Not a native reachability guarantee.')
                    break
    args.suite=f'c-{args.point}-a{args.attempt}';args.stage=p['stage'];args.host=HOST;args.patched=MODULES
    lab=open_lab(args);lab.result.update(d2c_point=p,attempt=args.attempt,full_d2_passed=False)
    original=NativeSession.host_options;original_env=session_module.host_environment;records=[];stage='startup';error=None
    def options(self,player):return original(self,player)|dict(DM_D2B_SENSOR='1',DM_RL_STALL_SECONDS='120')|({'DM_TEST_SPECIAL':'infinite'}if player==0 else{})
    def environment(*a,**kw):
        result=original_env(*a,**kw);result.pop('DM_WATCH',None);result.pop('DM_WATCH_STALL',None);return result
    def command(op,label,**kw):
        record=run(lab,dict(op=op,label=label,**kw));records.append(record)
        with (lab.out/'commands.jsonl').open('a')as f:f.write(json.dumps(record)+'\n')
        return record
    try:
        with patch.object(NativeSession,'host_options',options),patch.object(session_module,'host_environment',environment):
            lab.start();stage='setup'
            # Retry is a distinct fresh-process experiment. The first accepted
            # intermediate hub avoids demanding an arbitrary endpoint at spawn.
            if args.attempt==2:
                hub=[0,3,8]if p['stage']==1 else list(lab.atlas.points[lab.atlas.nearest(lab.atlas.region('center'))])
                command('navigate','c-hub',goals={'0':hub,'1':hub})
            command('navigate','c-setup',goals={'0':p['source'],'1':p['target']})
            command('assert','c-health',healthy=[0,1])
            stage='aim'
            aim=list(p['requested_anchor'])
            if args.attempt==2:
                # Bounded local pitch correction only, never change a surface
                # or teleport an actor. Native requested-hit error stays visible.
                aim[1]-=.03*math.dist(lab.info(0)['position'],aim)
            command('align','c-hook-aim',target=aim,fast=True)
            before=command('status','c-before')['infos']
            command('step','c-RS',frames=1,actions={'player_0':{'buttons':[0,0,0,1,0,0]}})
            command('step','c-startup',frames=30)
            stage='target_precondition'
            command('status','c-after-activation-health')
            stage='hook'
            command('step','c-R',frames=1,actions={'player_0':{'buttons':[0,0,1,0,0,0]}})
            stage='hook'
            command('step','c-release',frames=90)
            attached=command('status','c-attached')['infos']
            sensors=read_sensors(lab.result['session'])
            binds=[s for s in sensors if s['process']==0 and s['native_frame']>=before['player_0']['frame']and s['bind_witness']]
            lab.result['native_bind_witnesses']=binds
            if not binds:
                lab.result['outcome']='bind_failed';raise AssertionError('no native PreAttack/Attack anchor witness')
            stage='combo'
            if lab.info(1)['hp']<.999:
                # Hook contact is not a sword combo. Heal the stationary dummy
                # through ordinary own-ink inputs, then require full HP again.
                q=lab.info(1)['position']
                command('align','c-target-heal-aim',player=1,target=[q[0],q[1]-.5,q[2]+1],fast=True,budget=90)
                command('step','c-target-heal-paint',frames=1,actions={'player_1':{'buttons':[1,0,0,0,0,0]}})
                command('step','c-target-heal-paint-release',frames=30)
                command('refill','c-target-heal',player=1,frames=150)
                command('assert','c-target-recovered',healthy=[1])
            command('align','c-target-aim',target_player=1,offset=[0,1.1,0],fast=True,require_active=True)
            command('step','c-face',frames=6,actions={'player_0':{'sticks':[0,.85,0,0]}},require_active=True)
            command('step','c-settle',frames=8)
            if args.attempt==2:
                command('step','c-jump-clearance',frames=1,actions={'player_0':{'buttons':[0,0,0,0,1,0]}})
                command('step','c-rise-clearance',frames=10)
                lab.result['retry_combo_variant']='single jump for muzzle clearance; no additional hook firing'
            command('assert','c-charge-health',healthy=[1])
            command('status','c-charge-before')
            for label,frames,buttons in [('charge21',21,[1,0,0,0,0,0]),('full-release',36,[0]*6),('light',1,[1,0,0,0,0,0]),('light-release',42,[0]*6)]:
                command('track_step','c-'+label,frames=frames,player=0,target_player=1,offset=[0,1.1,0],buttons=buttons,require_active=True)
            command('status','c-combo-after')
            lab.result['outcome']='combo_ko'if not lab.info(1)['alive']else'combo_missed'
            stage='complete'
            lab.result.update(passed=True,driver_completed=True)
    except AssertionError as caught:
        error=repr(caught);lab.result.update(passed=True,driver_completed=True,
            outcome=lab.result.get('outcome','setup_failed'if stage=='setup'else'aim_failed'if stage=='aim'else'combo_unavailable'),fixture_error=error)
    except BaseException as caught:
        error=repr(caught);lab.result['errors'].append(error);lab.result['traceback']=traceback.format_exc();lab.result['outcome']='runtime_error'
    finally:lab.close()
    sensors=read_sensors(lab.result['session'])if lab.result.get('session')else[]
    (lab.out/'sensors.jsonl').write_text(''.join(json.dumps(s,separators=(',',':'))+'\n'for s in sensors))
    rows=[json.loads(l)for l in (lab.out/'steps.jsonl').open()];decreases=[]
    for a,b in zip(rows,rows[1:]):
        if b['label'].startswith('c-')and a['infos']['player_1']['hp']>b['infos']['player_1']['hp']:
            decreases.append(dict(actor0_ack=b['infos']['player_0']['frame'],target_ack=b['infos']['player_1']['frame'],hp_before=a['infos']['player_1']['hp'],hp_after=b['infos']['player_1']['hp']))
    get=lambda label:next((r['infos']for r in records if r['command']['label']==label),None)
    charge=get('c-charge-before');ko=next((r for r in decreases if r['hp_after']==0),None)
    bind=lab.result.get('native_bind_witnesses',[])
    result=dict(schema='inklab.d2c.point.v1',point=p,attempt=args.attempt,outcome=lab.result['outcome'],
        fixture_stage=stage,error=error,artifacts=str(lab.out.relative_to(ROOT)),session=lab.result.get('session'),
        before=get('c-before'),attached=get('c-attached'),charge_before=charge,after=get('c-combo-after'),
        bind=bind[0]if bind else None,requested_anchor_error=math.dist(bind[0]['anchor_world'],p['requested_anchor'])if bind else None,
        observed_landing_error=math.dist(get('c-attached')['player_0']['position'],p['estimated_landing'])if get('c-attached')else None,
        hp_decreases=decreases,charge_to_ko_frames=ko['actor0_ack']-charge['player_0']['frame']if ko and charge else None,
        source_sha256={str(path.relative_to(ROOT)):sha(path)for path in [lab.out/'tested-validate_candidates.py',args.selection,lab.out/'result.json',lab.out/'steps.jsonl',lab.out/'sensors.jsonl',*([lab.out/'commands.jsonl']if records else[])]})
    if lab.result.get('session'):
        for i in (0,1):
            log=Path(lab.result['session'])/f'player-{i}/host.log';result['source_sha256'][str(log.relative_to(ROOT))]=sha(log)
    write(lab.out/'point.json',result);print('D2C_RESULT '+str(lab.out/'point.json'),flush=True)
    return 1 if result['outcome']=='runtime_error'else 0


def batch(args):
    args.out=args.out.resolve()
    points=json.loads(args.selection.read_text())['points']
    if args.limit:points=points[:args.limit]
    if args.ids:points=[p for p in points if p['id']in args.ids.split(',')]
    args.out.mkdir(parents=True,exist_ok=False)
    def execute(p):
        log=args.out/(p['id']+f'-a{args.attempt}.log')
        cmd=[sys.executable,str(Path(__file__).resolve()),'point','--selection',str(args.selection.resolve()),'--point',p['id'],'--attempt',str(args.attempt)]
        with log.open('w')as f:completed=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env={k:v for k,v in os.environ.items()if not k.startswith('DM_')})
        lines=[line for line in log.read_text().splitlines()if line.startswith('D2C_RESULT ')]
        return dict(point=p['id'],exit_code=completed.returncode,log=str(log.relative_to(ROOT)),result=lines[-1].split(' ',1)[1]if lines else None)
    results=[]
    with ThreadPoolExecutor(max_workers=args.rooms)as pool:
        for task in as_completed([pool.submit(execute,p)for p in points]):
            result=task.result();results.append(result);write(args.out/'batch.json',dict(results=results,rooms=args.rooms));print(json.dumps(result),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['select','point','batch'])
    parser.add_argument('--selection',type=Path,default=ROOT/'work/d2c/selection.json')
    parser.add_argument('--point');parser.add_argument('--attempt',type=int,choices=[1,2],default=1)
    parser.add_argument('--rooms',type=int,choices=[1,2,3],default=3);parser.add_argument('--limit',type=int)
    parser.add_argument('--ids');parser.add_argument('--out',type=Path,default=ROOT/'work/d2c/batch1');parser.add_argument('--timeout',type=float,default=1800)
    args=parser.parse_args();raise SystemExit({'select':select,'point':point,'batch':batch}[args.mode](args))
