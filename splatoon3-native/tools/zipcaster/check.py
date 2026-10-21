#!/usr/bin/env python3
"""Offline D2 evidence audit. Does not start games, modify saves, or publish data."""
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster.surfaces import first_hit
from tools.zipcaster.export import compact_layers, trace


def main():
    count=0
    def check(value,message):
        nonlocal count
        count+=1
        if not value:raise AssertionError(message)

    # Occlusion order, endpoints, two-sided triangles and a miss are all material
    # to static candidate filtering; no native-volume sweep is asserted here.
    tri=np.array([[[0,0,2],[2,0,2],[0,2,2]],[[0,0,1],[2,0,1],[0,2,1]]],float)
    hit=first_hit(tri,[.2,.2,0],[.2,.2,3]);check(hit[0]==1 and abs(hit[2]-1/3)<1e-8,'nearest occluder')
    check(first_hit(tri,[3,3,0],[3,3,3])is None,'off-face miss')
    check(first_hit(tri[:,::-1],[.2,.2,0],[.2,.2,3])[0]==1,'winding-independent query')
    check(first_hit(tri,[.2,.2,0],[.2,.2,1])[0]==1,'endpoint surface accepted')
    check(first_hit(tri,[.2,.2,1],[.2,.2,0])is None,'source face does not self-occlude')

    report=json.loads((ROOT/'notes/d2-20261021.json').read_text())
    check(report['full_d2_passed']is False and report['status']=='partial_blocked','no false acceptance')
    for collection in ('outputs','source_provenance'):
        for name,value in report[collection].items():
            path=ROOT/name;expected=value['sha256']if isinstance(value,dict)else value
            check(hashlib.sha256(path.read_bytes()).hexdigest()==expected,'source hash '+name)
    for run in report['raw_runs']:
        for name,sha in run['sha256'].items():
            check(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,'raw hash '+name)
        for pid in json.loads((ROOT/run['artifacts']/'result.json').read_text()).get('owned_pids',[]):
            # PID reuse is possible, so process inventory is separately reported;
            # raw record presence alone never proves a current process is owned.
            check(type(pid)is int,'owned PID record')
    d=json.loads((ROOT/'work/d2/measurements.json').read_text())
    check(len(d['range_trials'])==7,'range trial count')
    ranges={r['case']:r for r in d['range_trials']}
    check(ranges['range37']['body_displacement']>36 and ranges['range38']['body_displacement']<.01,'native positive/negative range bracket')
    check([round(v['hp_after'],2)for v in d['mid_combo']['hp_decreases']]==[.3,0],'mid combo actual HP transitions')
    start=d['mid_combo']['statuses']['mc-before-charge']['player_0']['frame']
    check(d['mid_combo']['hp_decreases'][-1]['actor0_ack']-start==150,'observed combo duration')
    for case,expected in [('gc20',.65),('gc21',.3)]:
        s=d['statuses']['combat-v3'];check(s[case+'-before']['player_1']['hp']==1,'full target HP')
        check(abs(s[case+'-after']['player_1']['hp']-expected)<1e-6,'20/21-frame damage discrimination')

    source=ROOT/'work/d2/map-analysis-full.json';full=json.loads(source.read_text())
    compact=compact_layers(source);actual=json.loads((ROOT/'showcase/data/zipcaster-layer.json').read_text())
    check(actual==compact,'lossless compact schema export')
    check(len(full['maps'])==3,'three maps complete')
    for m,c in zip(full['maps'],compact['maps']):
        check(len(m['candidates'])==len(c['anchors']),'all anchor rows retained')
        check(len(m['shortlist'])==5,'five static shortlist entries')
        for point,row in zip(m['candidates'],c['anchors']):
            check(point['native_status']=='unverified_static_candidate','no static point certified')
            check(row[1:4]==point['anchor'],'coordinate export')
            for a in point['approaches']:
                check(3<=a['eye_to_anchor']<=35 and a['native_reachable']is None,'conservative static range, no reachability claim')
                check(a['attach_pose_estimate']==point['attach_pose_estimate'],'oriented-side grouping')
            for t in point['targets']:
                check(t['native_combo_verified']is False,'no geometry-to-native combo promotion')
                if t['full_plus_light_geometry_candidate']:
                    check(t['landing_distance']<=19 and t['landing_center_ray_clear'],'combo geometry conditions')
    clips=json.loads((ROOT/'showcase/data/zipcaster-traces.json').read_text())
    check(len(clips)==5,'five fixture clips')
    for clip in clips:
        raw=ROOT/clip['evidence']['raw_steps'];directory=raw.parent
        prefix=clip['label'].split(' · ',1)[1]
        check(trace(directory,prefix)==clip,'exact raw-to-trace reconstruction')
        for p in clip['players']:
            check(all(a[0]<b[0]for a,b in zip(p['states'],p['states'][1:])),'monotonic trace frames')
            check(all(len(s)==len(clip['columns'])and all(v is None or not isinstance(v,float)or math.isfinite(v)for v in s)for s in p['states']),'schema/finiteness')
        if prefix=='idle':
            check(max(b[0]-a[0]for a,b in zip(clip['players'][0]['states'],clip['players'][0]['states'][1:]))<=6,'complete sampled return animation')
    print(json.dumps(dict(passed=True,checks=count,full_d2_passed=False,offline_only=True)))


if __name__=='__main__':main()
