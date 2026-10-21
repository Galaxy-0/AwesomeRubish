#!/usr/bin/env python3
"""Offline D2B safety/provenance/evidence checks; starts no game processes."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(Path(__file__).parent))
from sensor_evidence import transform,reduce_group


def main():
    count=0
    def check(value,message):
        nonlocal count
        count+=1
        if not value:raise AssertionError(message)
    def source(entry):
        check(hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()==entry['sha256'],'source '+entry['path'])
    report=json.loads((ROOT/'notes/d2b-20261021.json').read_text())
    check(report['full_d2_passed']is False,'remaining ceiling/armor limits retained')
    for entry in report['source_provenance']+report['outputs']+list(report['runtime'].values()):source(entry)
    for run in report['raw_runs'].values():
        for entry in run['sources']+run.get('decoded',[]):source(entry)
    provenance=json.loads((ROOT/report['runtime']['provenance']['path']).read_text())
    for collection in ['protected','original_module_sha256']:
        for path,digest in provenance[collection].items():source(dict(path=path,sha256=digest))
    build=json.loads((ROOT/report['runtime']['build_manifest']['path']).read_text())
    check(build['test_only']and build['test_feature']=='special_meter'and build['diagnostic']=='d2b_readonly_superhook','isolated fixture identity')
    for path,digest in build['source_sha256'].items():source(dict(path=path,sha256=digest))
    # A translated/rotated actor is material to world-anchor evidence. Check
    # that normals do not receive translation and stale local fields are inert.
    matrix=[0,-1,0,10,1,0,0,20,0,0,1,30]
    check(transform(matrix,[1,2,3])==[8,21,33],'3x4 point transform')
    check(transform(matrix,[1,0,0],False)==[0,1,0],'normal transform excludes translation')
    hook=dict(kind='superhook',process=0,native_frame=1,slot=0,state_native=1,state_name='State::cShot',
        position_98_candidate=[1,2,3],normal_a4_candidate=[1,0,0],bind_object_id_candidate=18,phase_flags_candidate=[0])
    row=reduce_group([hook,dict(kind='surface_matrix',matrix_3x4=matrix)])
    check(row['anchor_world']is None and row['hook_tip_world']==[1,2,3],'Shot is tip, never stale anchor')
    hook['state_native']=0;row=reduce_group([hook,dict(kind='surface_matrix',matrix_3x4=matrix)])
    check(row['anchor_world']is None and row['hook_tip_world']is None,'Wait cache is not current bind')
    hook['state_native']=3;row=reduce_group([hook,dict(kind='surface_matrix',matrix_3x4=matrix)])
    check(row['anchor_world']==[8,21,33]and row['hit_normal_world']==[0,1,0],'bound native world data')
    check(reduce_group([hook])['anchor_world']is None,'missing actor transform remains unknown')
    high=report['high_combo'];check(high['before']['player_1']['hp']==1,'high target initially full')
    check([round(r['hp_after'],2)for r in high['hp_decreases']]==[.3,0],'native high70 then KO')
    check(high['charge_input_frames']==21 and high['charge_start_to_observed_ko_frames']==75,'recorded timing, not shortest-time guarantee')
    check(all(r['armor_hp_native']==0 and r['armor_flags_native']==0 for r in high['target_native_armor_during_combo']),'high target had no native armor')
    check(any(r['armor_hp_native']==300 and r['armor_flags_native']==1 for r in report['pure_wall_control']),'special armor presence control')
    early,late=[report['damage_controls'][case]for case in ['early','late']]
    check(early['before']==1 and early['after']==1,'early no body damage, cause remains unknown')
    check(late['before']==1 and abs(late['after']-.3)<1e-6,'late native70')
    late_hit=[r for r in late['native_changes']if r['body_hp_native']==300]
    check(late_hit and all(r['armor_hp_native']==0 for r in late_hit),'late hit outside armor buffer')
    check(len(report['raw_runs']['b2-ceiling']['failed_setup_commands'])==2,'two failed ceiling placements excluded')
    for name in ['b1-survey','b2-world','b2-ceiling','b2-armor']:
        source_path=ROOT/f'tools/zipcaster/plans/sensor-{name}.jsonl'
        queue=ROOT/f'work/d2/{name}.commands.jsonl'
        check(source_path.read_bytes()==queue.read_bytes(),'exact recorded plan '+name)
    trace_path=ROOT/report['outputs'][0]['path'];clip=json.loads(trace_path.read_text())[0]
    check(clip['schema']=='inklab.trace.v1'and clip['source_kind']=='native_observation','D1 trace schema')
    check(clip['players'][1]['states']and min(r[clip['columns'].index('hp')]for r in clip['players'][1]['states'])==0,'KO included in trace')
    result=dict(passed=True,checks=count,offline_only=True,full_d2_passed=False)
    destination=ROOT/'work/d2b/check.json';destination.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
