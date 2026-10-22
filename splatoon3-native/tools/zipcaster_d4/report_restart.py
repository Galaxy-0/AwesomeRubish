"""Numerical checkpoint/closure report; excludes meshes, raw bytes and traces."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha
from tools.zipcaster_d4.report_duel import reduce


def main(a):
    if a.out.exists():raise ValueError('fresh report required')
    base=ROOT/'work/d4/restart-v3'
    batch=json.loads((base/'native-cohort216-v1/batch.json').read_text())
    rooms=[];timeline=[];pids=set();bindings={}
    for path in sorted((ROOT/'work/a6').glob('d3-r-d4-duel6-*/result.json')):
        stamp=re.search(r'-(20261022-\d{6}-\d+)$',path.parent.name)
        if stamp is None or stamp[1]<'20261022-182552-000000':continue
        d=json.loads(path.read_text())
        assert 'freeze_after'in d and d['freeze_before']==d['freeze_after'],path
        raw=reduce(path)
        row=dict(artifact=str(path.relative_to(ROOT)),sha256=sha(path),point=d['point']['id'],
            errors=d['errors'],combat_started=any(e['event']=='before-RS'for e in d['events']),
            cohort_eligible=d.get('calibration_eligible',False),
            native_kill=d['outcome']['native_kill'],attacker_down=raw.get('attacker_down'),
            enemy_down=raw.get('enemy_down'),strict_budget_win=raw.get('strict_budget_win'),
            counter_at_enemy_down=raw.get('counter_at_enemy_down'),
            actual_pose_model=d.get('actual_pose_model'),
            setup_errors=d.get('setup_errors'))
        rooms.append(row);pids.update(d.get('owned_pids',[]))
        timeline.extend([(path.parent.stat().st_birthtime,1),(path.stat().st_mtime,-1)])
        bindings[row['artifact']]=row['sha256']
    active=peak=0
    for _,change in sorted(timeline):active+=change;peak=max(peak,active)
    listing=subprocess.check_output(['ps','-axo','pid=,comm='],text=True)
    live={int(line.strip().split(None,1)[0]):line.strip().split(None,1)[1]for line in listing.splitlines()if line.strip()}
    active_owned=[p for p in pids if p in live and 'dmhost'in live[p]]
    assert not active_owned and peak<=3,(active_owned,peak)
    protected=json.loads((base/'contact-host-v8/protected.json').read_text())
    assert all(sha(ROOT/p)==digest for p,digest in protected.items())
    runtime={}
    for name in ['contact-host-v5','contact-host-v6','contact-host-v7','contact-host-v8']:
        directory=base/name;record=json.loads((directory/'dmhost-aim.build.json').read_text())
        assert sha(directory/'dmhost-aim')==record['output_sha256']
        assert all(sha(directory/'modules'/n)==h for n,h in record['private_module_sha256'].items())
        runtime[name]=dict(host_sha256=record['output_sha256'],record_sha256=sha(directory/'dmhost-aim.build.json'))
    points={p['id']:p for p in json.loads((base/'calibration-plan-v4-neighbors.json').read_text())['points']}
    groups={}
    for row in batch['results']:
        group=points[row['point']]['band'];g=groups.setdefault(group,dict(valid=0,kills=0))
        if row['eligible']:g['valid']+=1;g['kills']+=int(row['strict_budget_win'])
    report=dict(schema='inklab.d4.restart.checkpoint.v2',date='2026-10-22',status=a.status,
        full_d4_passed=False,formal=dict(valid=batch['valid'],planned=batch['planned'],pending=batch['pending'],
            stop_reason=batch['stop_reason'],groups=groups,sha256=sha(base/'native-cohort216-v1/batch.json')),
        rooms=rooms,resources=dict(room_attempts=len(rooms),recorded_owned_hosts=len(pids),
            peak_rooms_conservative=peak,active_owned_hosts=active_owned,
            active_game_hosts=[dict(pid=p,command=c)for p,c in live.items()if Path(c).name.startswith('dmhost')],
            protected_hosts_sha256=protected,private_runtime=runtime,
            all_room_freeze_before_after_equal=True,
            freeze_scope='Unchanged inactive historical mismatch list; not a claim all frozen files match.'),
        evidence_sha256=bindings,source_sha256=sha(__file__),
        limits=['Formal cohort not complete; no native ranking/significance acceptance.',
                'Passive/changed-input/debug samples stay auxiliary. Pre-RS failures are voids, not kills or combat losses.',
                'Exact contact-volume overlap has an unclosed native damage/field-filter counterexample.',
                'New full-map bank, extreme-budget chains and corrected browser worker are not signed off.',
                'No grids, native code/byte dumps, screenshots, generated HTML or raw trace arrays in this report.'])
    a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(formal=report['formal'],resources={k:report['resources'][k]for k in ['room_attempts','recorded_owned_hosts','peak_rooms_conservative','active_owned_hosts','active_game_hosts']}),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--status',choices=['checkpoint','stopped'],default='checkpoint');main(p.parse_args())
