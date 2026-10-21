#!/usr/bin/env python3
"""Rebuild the bounded D2B report from closed local native experiments."""
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
from sensor_evidence import reduce_group
from inspect_native import FIELDS,BUILD
import numpy as np
from tools.zipcaster.surfaces import load_surfaces,first_hit

RUNS={
    'b1-state':('20261021-135229-456778','20261021-135229-518656',None),
    'b1-survey':('20261021-140052-127937','20261021-140052-181502','b1-survey-final'),
    'b2-world':('20261021-141406-112958','20261021-141406-177533','b2-world-final'),
    'b2-ceiling':('20261021-142152-732002','20261021-142152-794630','b2-ceiling-final'),
    'b2-armor':('20261021-143013-962291','20261021-143014-022434','b2-armor-final'),
}


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def jsonl(p):return [json.loads(line)for line in Path(p).open()]
def ref(p):return dict(path=str(Path(p).relative_to(ROOT)),sha256=sha(p))


def joined(directory):
    key=None;group=[];output=[]
    for row in jsonl(directory/'sensors.jsonl'):
        newkey=(row['process'],row['native_frame'])
        if key!=newkey:
            value=reduce_group(group)
            if value:output.append(value)
            group=[];key=newkey
        group.append(row)
    value=reduce_group(group)
    if value:output.append(value)
    return output


def changes(rows,fields):
    result=[];previous=object()
    for row in rows:
        value=tuple(row.get(field)for field in fields)
        if value!=previous:
            result.append({k:row.get(k)for k in ['native_frame',*fields]});previous=value
    return result


def ray_recheck(commands):
    triangles,normals,_,attrs=load_surfaces(ROOT/'work/arena/maps/Yunohana')
    source=ROOT/'work/d2b/b1-survey-final/sensors.jsonl'
    native=[r for r in jsonl(source)if r['kind']=='superhook'and r['process']==0]
    results=[]
    for case,lo,hi in [('ceiling-corner',7165,7173),('fence-exact',8477,8485)]:
        rows=[r for r in native if lo<=r['native_frame']<=hi and r['state_native']==1]
        before=next(c['infos']['player_0']for c in commands if c['command']['label']==case+'-before')
        a,b=[np.array(r['position_98_candidate'])for r in rows[:2]];d=b-a
        start=a+d*((before['position'][1]+1.1-a[1])/d[1]);end=np.array(rows[-1]['position_98_candidate'])
        hit=first_hit(triangles,start,end)
        results.append(dict(case=case,tip_samples=[dict(frame=r['native_frame'],position=r['position_98_candidate'])for r in rows],
            actual_segment_start=start.tolist(),actual_segment_end=end.tolist(),
            speed_per_frame=float(np.linalg.norm(d)/(rows[1]['native_frame']-rows[0]['native_frame'])),
            view_pitch_before=before['own_view']['pitch'],actual_tip_pitch=math.atan2(d[1],math.hypot(d[0],d[2])),
            static_first_intersection=None if hit is None else dict(face_index=hit[0],point=hit[1].tolist(),normal=normals[hit[0]].tolist(),**attrs[hit[0]]),
            warning='Near-origin trim at source body Y+1.1; actual native tip line, static thin ray, not native sweep or bind eligibility.'))
    return results


def main():
    runs={};commands={};steps={};evidence={}
    for name,(stamp,session_stamp,decoded)in RUNS.items():
        run=ROOT/f'work/a6/d2-{name}-{stamp}';session=ROOT/f'work/tests/m6-2p-{session_stamp}'
        result=load(run/'result.json');assert result['driver_completed'] and not result['errors']
        queue=ROOT/f'work/d2/{name}.commands.jsonl';results=queue.with_suffix('.results.jsonl')
        commands[name]=jsonl(results);steps[name]=jsonl(run/'steps.jsonl')
        raw=[run/'result.json',run/'steps.jsonl',queue,results,*[session/f'player-{i}/host.log'for i in (0,1)]]
        entry=dict(artifacts=str(run.relative_to(ROOT)),session=str(session.relative_to(ROOT)),
            driver_completed=True,scientific_pass_not_implied=True,
            failed_setup_commands=[dict(label=r['command']['label'],error=r['error'])for r in commands[name]if not r['completed']],
            sources=[ref(p)for p in raw])
        if decoded:
            directory=ROOT/'work/d2b'/decoded;summary=load(directory/'summary.json')
            for path,digest in summary['host_log_sha256'].items():assert sha(path)==digest
            evidence[name]=joined(directory)
            entry.update(decoded=[ref(directory/f)for f in ['sensors.jsonl','summary.json']],counts=summary['counts'])
        runs[name]=entry
    world=evidence['b2-world'];armor=evidence['b2-armor']
    own=[r for r in world if r['process']==0];bound=[r for r in own if r['bind_witness']]
    # Distinct native bind witnesses, not a static mesh or stale Wait position.
    anchors=[]
    for r in bound:
        if not anchors or sum((a-b)**2 for a,b in zip(anchors[-1]['anchor_world'],r['anchor_world']))>.01:
            anchors.append({k:r[k]for k in ['native_frame','anchor_world','hit_normal_world','bound_actor_id','surface_matrix']})
    world_steps=steps['b2-world'];high=[r for r in world_steps if r.get('label','').startswith('high-side')]
    decreases=[]
    for a,b in zip(world_steps,world_steps[1:]):
        if b.get('label','').startswith('high-side')and a['infos']['player_1']['hp']>b['infos']['player_1']['hp']:
            decreases.append(dict(label=b['label'],actor0_ack=b['infos']['player_0']['frame'],
                target_ack=b['infos']['player_1']['frame'],target_position_sample_frame=b['infos']['player_1']['position_sample_frame'],
                hp_before=a['infos']['player_1']['hp'],hp_after=b['infos']['player_1']['hp']))
    charge=[r for r in high if r['label']=='high-side-charge21'];start=charge[0]['infos']['player_0']['frame']-1
    status=lambda name,label:next(r['infos']for r in commands[name]if r['command']['label']==label)
    damage_controls={}
    for case in ['early','late']:
        lo=status('b2-armor',case+'-before')['player_0']['frame'];hi=status('b2-armor',case+'-after')['player_0']['frame']
        native=[r for r in armor if r['process']==0 and lo<=r['native_frame']<=hi]
        damage_controls[case]=dict(before=status('b2-armor',case+'-before')['player_0']['hp'],
            after=status('b2-armor',case+'-after')['player_0']['hp'],
            native_changes=changes(native,['body_hp_native','armor_hp_native','armor_flags_native','collision_mask_21d_native','state_native']))
    protected=load(ROOT/'work/d2b/round2-world-build/provenance.json')
    for collection in ['protected','original_module_sha256']:
        for path,digest in protected[collection].items():assert sha(ROOT/path)==digest,path
    build=ROOT/'work/d2b/round2-world-build/dmhost-sensors.build.json';manifest=load(build)
    for path,digest in manifest['source_sha256'].items():assert sha(ROOT/path)==digest,path
    sources=sorted(Path(__file__).parent.glob('*sensor*'))+[Path(__file__).with_name('inspect_native.py')]
    sources=[p for p in sources if p.is_file()]
    report=dict(schema='inklab.d2b.report.v1',date='2026-10-21',build_id=BUILD,
        status='sensors_and_high_combo_verified_ceiling_fixture_blocked',full_d2_passed=False,
        readonly_sensors=True,native_rooms_max_concurrent=2,game_rendering='full pixels',fixed60=True,
        special_fixture_only='actor0 infinite, actor1 natural; both QS57AP',fields=FIELDS,
        limitations=['4-present native stride; phase boundaries are intervals, not single-frame guarantees.',
            'Native actor ID and world plane recovered, not a material/triangle index or eligibility enum.',
            'Armor flags 1 and raw HP300 are measured; raw damage multiplier and invulnerability not proved.',
            'Ceiling source placement failed twice; no universal ceiling bind/no-bind claim.',
            'Native hook tip ray and camera ray differ; no global aim correction inferred.',
            'No moving actor/rotated actor native fixture; matrix transformation statically verified plus synthetic regression.',
            'No RL_STALL flight re-fire exploration, no policy/protocol changes, no page re-publish.'],
        native_anchors=anchors,
        high_combo=dict(before=status('b2-world','high-side-charge-before'),
            full_after=status('b2-world','high-side-full-after'),after=status('b2-world','high-side-combo-after'),
            returned=status('b2-world','high-side-returned')['player_0']['position'],
            charge_input_frames=len(charge),charge_start_ack=start,hp_decreases=decreases,
            charge_start_to_observed_ko_frames=decreases[-1]['actor0_ack']-start,
            target_native_armor_during_combo=changes([r for r in world if r['process']==1 and 5700<=r['native_frame']<=5820],['armor_flags_native','armor_hp_native']),
            interpretation='Side-corner hook lands on grate near Y9; grounded full70 then light35 kills full-health high target. Not a hanging-air combo or minimum-time claim.'),
        pure_wall_control=changes([r for r in own if 4940<=r['native_frame']<=5070],['state_native','armor_flags_native','armor_hp_native','collision_mask_21d_native']),
        damage_controls=damage_controls,
        ceiling_ray_recheck=ray_recheck(commands['b1-survey']),
        raw_runs=runs,
        outputs=[ref(ROOT/'work/d2b/traces/high-side.json')],
        runtime=dict(host=ref(ROOT/manifest['output']),build_manifest=ref(build),provenance=ref(ROOT/'work/d2b/round2-world-build/provenance.json')),
        source_provenance=[ref(p)for p in sources],
        stopped_remaining_branch='Ceiling setup: direct spawn route and center-reset route both bounded fixture failures. Preserve dependent shots as invalid, stop route exploration.')
    out=ROOT/'notes/d2b-20261021.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(out)


if __name__=='__main__':main()
