"""Zero-new-experiment contact hypotheses with native position-sample clocks.

Output geometry is diagnostic. Repeated public readbacks are deduplicated;
interpolation brackets and movement are retained, never called independent
native samples. No inferred LOS/height cutoff is silently adopted by planner.
"""
import argparse,bisect,json,math,re,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d4.analyze_contact import SNAP
from tools.zipcaster_d4.attack_geometry import contact_overlap,xyz,basis
from tools.zipcaster_d4.contact_shape import native_shape
from tools.zipcaster_d4.contact_field import shape_field,closest_witness
from tools.zipcaster_d4.query_model import World
from tools.zipcaster_d3r.analyze_direction import sha


def aligned_series(steps,role,start):
    samples={};offsets=set();duplicates=0;disagreement=0.
    for row in steps:
        infos=row['infos'];p=infos['player_0'];q=infos['player_1']
        if p['frame']<start:continue
        offset=p['frame']-q['frame'];offsets.add(offset)
        info=infos['player_'+str(role)];frame=info['position_sample_frame']+(offset if role else 0)
        position=np.asarray(info['position'],float)
        if not info.get('position_valid'):continue
        if frame in samples:
            duplicates+=1;disagreement=max(disagreement,float(np.linalg.norm(samples[frame]-position)))
        samples[frame]=position
    times=sorted(samples)
    return times,samples,dict(offsets=sorted(offsets),unique_samples=len(times),duplicate_readbacks=duplicates,
                              duplicate_max_position_disagreement=disagreement)


def at_frame(series,frame):
    times,samples,_=series
    i=bisect.bisect_right(times,frame)-1
    if i<0 or i>=len(times)-1 and times[i]!=frame:return None
    lo=times[i];hi=lo if lo==frame else times[i+1]
    fraction=0. if lo==hi else(frame-lo)/(hi-lo)
    position=samples[lo]*(1-fraction)+samples[hi]*fraction
    return dict(position=position.tolist(),sample_frames=[lo,hi],interpolated=lo!=hi,
                bracket_motion=float(np.linalg.norm(samples[hi]-samples[lo])))


def audit(path,worlds):
    d=json.loads(path.read_text());assert d['freeze_before']==d['freeze_after']
    if not d.get('session')or not any(e['event']=='before-RS'for e in d['events']):return []
    graph=d['point']['graph']
    if graph not in worlds:worlds[graph]=World(ROOT/graph)
    world=worlds[graph];steps=[json.loads(l)for l in (path.parent/'steps.jsonl').read_text().splitlines()]
    start=next(e['infos']['player_0']['frame']for e in d['events']if e['event']=='before-RS')
    series=[aligned_series(steps,role,start)for role in [0,1]]
    if any(len(s[2]['offsets'])!=1 or not s[0]for s in series):raise ValueError(('clock alignment not constant',path))
    offset=series[1][2]['offsets'][0];log=Path(d['session'])/'player-0/host.log';captures={}
    for m in SNAP.finditer(log.read_text()):captures.setdefault(int(m[1]),{})[m[2]]=bytes.fromhex(m[3])
    groups=[];group=None
    for frame,blobs in sorted(captures.items()):
        if 'd4_engine'not in blobs:continue
        identity=blobs['d4_slash'][:8]+blobs['d4_params'][0x30:0x48]
        if group is None or frame>group[-1][0]+1 or identity!=group[-1][2]:group=[];groups.append(group)
        group.append((frame,blobs,identity))
    hp=[(int(m[1])+offset,int(m[2]))for m in re.finditer(r'RL_DAMAGE frame=(\d+) slot=\d+ hp=(-?\d+)',(Path(d['session'])/'player-1/host.log').read_text())]
    result=[]
    for index,group in enumerate(groups):
        rows=[]
        for frame,blobs,_ in group:
            source,target=[at_frame(s,frame)for s in series]
            if source is None or target is None:continue
            engine=np.frombuffer(blobs['d4_engine'],dtype='<f4').astype(float)
            origin=engine[0x25c//4:0x268//4];rotation=engine[0x268//4:0x28c//4].reshape(3,3)
            box=np.frombuffer(blobs['d4_box'],dtype='<f4').astype(float)
            key=min(['vertical','horizontal'],key=lambda k:np.linalg.norm(box[0xd8//4:0xe4//4]-xyz(world.shots.parameters[k+'_contact']['ShapeParam']['BoxHalfExtents'])))
            shape=native_shape(world.shots.parameters[key+'_contact']['ShapeParam'])
            enemy=np.array(target['position']);foot=np.array(source['position'])
            witness=closest_witness(origin,rotation,shape,enemy)
            los={}
            for name,p in [('attacker_body',foot+[0,1.1,0]),('contact_birth',origin),('geometric_closest',np.array(witness['shape_point']))]:
                los[name]=world.field.clear_pairs(p,enemy+np.array([[0,h,0]for h in [.35,.8,1.3]])).tolist()
            field=shape_field(world.field.tri,origin,rotation,shape)
            yaw=math.atan2(rotation[0,2],rotation[2,2])
            rows.append(dict(frame=frame,source=source,target=target,origin=origin.tolist(),rotation=rotation.tolist(),
                style=key,height_difference=float(enemy[1]-foot[1]),elevation_degrees=float(math.degrees(math.asin(np.clip(rotation[1,2],-1,1)))),
                receiver_overlap=contact_overlap(origin,rotation,shape,enemy),
                yaw_only_counterfactual_overlap=contact_overlap(origin,basis(yaw,0),shape,enemy),
                closest_witness=witness,los=los,
                field_intersections=field,any_field_overlap=bool(field),wall_field_overlap=any(h['surface_kind']=='wall-like'for h in field),
                masks={name:{hex(off):int.from_bytes(blobs[name][off:off+4],'little')for off in [0x10,0x14,0x68,0xe8]}for name in ['d4_body','d4_box','d4_cylinder']if name in blobs}))
        if not rows:continue
        first,last=rows[0]['frame'],rows[-1]['frame'];before=next((h for f,h in reversed(hp)if f<first),None)
        changes=[];previous=before
        for f,h in hp:
            if not first<=f<=last+12:continue
            if previous is not None and h!=previous:changes.append(dict(frame=f,drop=previous-h,hp=h))
            previous=h
        full=rows[0]['style']=='vertical'
        contact_label=any(c['drop']>=1000 for c in changes)if full and before==1000 else None
        result.append(dict(artifact=str(path.relative_to(ROOT)),artifact_sha256=sha(path),point=d['point']['id'],slash=index,
            clock_alignment=[s[2]for s in series],frame_interval=[first,last],frames=rows,hp_before=before,hp_edges=changes,
            full_contact_label=contact_label,
            first_observed_field_overlap=next((r['frame']for r in rows if r['any_field_overlap']),None),
            first_observed_wall_overlap=next((r['frame']for r in rows if r['wall_field_overlap']),None),
            rule_predictions={**{name:all(any(r['los'][name])for r in rows)for name in rows[0]['los']},
                              'deny_any_field_overlap':not any(r['any_field_overlap']for r in rows),
                              'deny_wall_overlap':not any(r['wall_field_overlap']for r in rows)},
            scope='LOS origins and volume/field intersections are competing hypotheses. Closest overlap witness is not the native notification point. First observed calc-frame overlap is not proven registration time.'))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,nargs='+',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('fresh output required')
    worlds={};rows=[r for path in a.results for r in audit(path.resolve(),worlds)]
    disagreements=[dict(artifact=r['artifact'],slash=r['slash'],label=r['full_contact_label'],rules=r['rule_predictions'])for r in rows if len(set(r['rule_predictions'].values()))>1]
    a.out.write_text(json.dumps(dict(schema='inklab.d4.contact.hypotheses.v1',rows=rows,disagreements=disagreements,
        source_sha256={str(p.relative_to(ROOT)):sha(p)for p in [Path(__file__),Path(__file__).with_name('contact_field.py')]},
        full_d4_passed=False),indent=2)+'\n')
    print(json.dumps(dict(slashes=len(rows),disagreements=len(disagreements),labels=[r['full_contact_label']for r in rows])))
