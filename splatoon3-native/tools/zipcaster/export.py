#!/usr/bin/env python3
"""Prepare compact D2 layers and D1-compatible native traces; no screenshots/assets."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from showcase.derive_traces import COLUMNS,clean,edges


def compact_layers(source):
    full=json.loads(source.read_text());result={k:v for k,v in full.items()if k!='maps'}
    result.update(schema='inklab.d2.hook-layer.compact.v1',full_analysis_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),maps=[])
    result['anchor_columns']=['id','x','y','z','nx','ny','nz','attach_x','attach_y','attach_z','landing_x','landing_y','landing_z','hanging_view_percent','landing_view_percent','flags_index']
    result['approach_columns']=['anchor_index','start_id','eye_to_anchor','incidence_cosine','potential_exposure']
    result['exposure_columns']=['target_id','first_visible_progress','visible_sample_fraction']
    result['target_columns']=['anchor_index','target_id','attach_distance','landing_distance','enemy_can_see_attachment_if_looking','landing_center_ray_clear','full_plus_light_geometry_candidate']
    for m in full['maps']:
        anchors=[];approaches=[];targets=[];flag_sets=[];target_positions={};starts={}
        for i,c in enumerate(m['candidates']):
            flags=c['material_flags']
            if flags not in flag_sets:flag_sets.append(flags)
            anchors.append([c['id'],*c['anchor'],*c['normal'],*c['attach_pose_estimate'],*(c['landing_estimate']or[None]*3),c['hanging_view_percent'],c['landing_view_percent'],flag_sets.index(flags)])
            for a in c['approaches']:
                starts[a['start']]=a['source'];approaches.append([i,a['start'],a['eye_to_anchor'],a['incidence_cosine'],[[e['target'],e['first_visible_progress'],e['visible_sample_fraction']]for e in a['potential_exposure']]])
            for t in c['targets']:
                target_positions[t['target']]=dict(position=t['position'],kind=t['kind']);targets.append([i,t['target'],t['attach_distance'],t['landing_distance'],t['enemy_can_see_attachment_if_looking'],t['landing_center_ray_clear'],t['full_plus_light_geometry_candidate']])
        result['maps'].append(dict(id=m['id'],wall_samples=m['wall_samples'],anchors=anchors,approaches=approaches,targets=targets,
            starts=starts,target_positions=target_positions,material_flag_sets=flag_sets,shortlist=m['shortlist'],selection=m['selection'],sources=m['sources']))
    result['native_validation']='All enumerated candidates remain unverified; native fixture traces are separate evidence, not wholesale certification.'
    return result


def trace(directory,prefix):
    directory=Path(directory);raw=directory/'steps.jsonl';rows=[json.loads(s)for s in raw.read_text().splitlines()];run=json.loads((directory/'result.json').read_text())
    origins={p:rows[0]['infos'][p]['frame']-rows[0]['frames']for p in ('player_0','player_1')}
    entry=next(r for r in rows if r['label']==prefix+'-RS');start=entry['infos']['player_0']['frame']-origins['player_0']-entry['frames']
    last=max(r['infos']['player_0']['frame']-origins['player_0']for r in rows if r['label'].startswith(prefix+'-'))
    end=min(start+1200,last);players=[]
    for n,p in enumerate(('player_0','player_1')):
        states=[];inputs=[];r_releases=[];previous=[0]*6;held=None
        for row in rows:
            info=row['infos'][p];f=info['frame']-origins[p];input_frame=f-row['frames']+1;b=row['actions'][p]['buttons'];inputs.append((input_frame,b))
            if b[2]and not previous[2]:held=input_frame
            if not b[2]and previous[2]and start<=input_frame<=end:r_releases.append(dict(frame=input_frame,type='R_release',hold_frames=input_frame-held if held is not None else None,evidence='recorded_input_edge'))
            previous=b
            if not start<=f<=end or not info.get('position_valid'):continue
            if states and f-states[-1][0]<6 and f!=end:continue
            motion=info.get('referee_motion',{});form=motion.get('form_squid');contact=motion.get('ground_contact')
            state_form='human'if form==0 else 'submerged'if form==1 and contact==0 else 'squid'if form==1 and contact in (4,5)else None
            states.append([f,info['position_sample_frame']-origins[p],*[clean(x,2)for x in info['position']],clean(info['heading'],4)if info.get('heading_valid')else None,
                state_form,clean(info['hp'])if info.get('hp_valid')else None,bool(info['alive'])if info.get('alive_valid')else None,clean(info['ink'])if info.get('ink_valid')else None])
        events=sorted(edges(inputs,start,end)+r_releases,key=lambda e:e['frame'])
        players.append(dict(id='alpha'if n==0 else 'bravo',display_name='飞索夹具'if n==0 else'靶 / 受击夹具',role=p,native_frame_origin=origins[p],states=states,events=events))
    return dict(schema='inklab.trace.v1',id='d2-'+directory.name+'-'+prefix,label='原生飞索 · '+prefix,
        source_kind='native_observation',map={1:'Yunohana',2:'District00',3:'Yagara'}[run['stage']],fps=60,start_frame=start,end_frame=end,stride=6,columns=COLUMNS,players=players,
        test_only=True,special_meter_mode=run['test_special_mode'],loadouts=run['loadouts'],
        evidence=dict(raw_steps=str(raw.relative_to(ROOT)),sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),result=str((directory/'result.json').relative_to(ROOT)),driver_completed=run.get('driver_completed',run.get('passed')),run_errors=run['errors']),
        selection='Explicit fixture prefix from RS through native end/last observation, capped at20s; no trajectory alignment.',
        position_semantics='Common controlled presents; sample_frame converted with each own native_frame_origin, preserving invertible native timestamps. Positions .01u / HP .001; unknown remains null. Only input events, never inferred hit/official phase.')


def main(args):
    args.out.mkdir(parents=True,exist_ok=True)
    if args.layers:
        payload=compact_layers(args.layers)
        if len(payload['maps'])!=3:raise ValueError('wait for all three complete map analyses')
        dest=args.out/'zipcaster-layer.json';text=json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n'
        if len(text.encode())>10_000_000:raise ValueError('compact layer exceeds preview budget')
        dest.write_text(text);print(dest,len(text.encode()))
    if args.clip:
        clips=[]
        for item in args.clip:
            run,prefix=item.rsplit(':',1)
            directory=Path(run)
            if not directory.exists():directory=Path(json.loads((ROOT/f'work/d2/{run}-latest.json').read_text())['artifacts'])
            clips.append(trace(directory,prefix))
        dest=args.out/'zipcaster-traces.json';dest.write_text(json.dumps(clips,ensure_ascii=False,separators=(',',':'))+'\n');print(dest,dest.stat().st_size)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--layers',type=Path);p.add_argument('--clip',action='append',help='run directory or local run name:fixture prefix');p.add_argument('--out',type=Path,default=ROOT/'showcase/data');raise SystemExit(main(p.parse_args()))
