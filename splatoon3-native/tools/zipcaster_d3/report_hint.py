#!/usr/bin/env python3
"""Numerical reduction of immutable hint runs, no game assets in output."""
import argparse,json,math,re,struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import ROOT,sha
from decode_sensors import SNAP

def reduce(p):
    p=p.resolve()
    d=json.loads(p.read_text());steps=[json.loads(x)for x in p.with_name('steps.jsonl').read_text().splitlines()]
    groups=[]
    for s in steps:
        if not s['label'].startswith('hint-'):continue
        a=s['infos']['player_0'];b=s['infos']['player_1'];v=a.get('own_view',{})
        item=dict(frame=a['frame'],label=s['label'],position=a['position'],ground=a.get('ground_contact'),special=a['special'],ink=a['ink'],hp=a['hp'],target_hp=b['hp'],heading=a['heading'],yaw=v.get('yaw'),pitch=v.get('pitch'),sample=v.get('sample_frame'))
        if not groups or groups[-1]['label']!=s['label']:groups.append(dict(label=s['label'],first=item,last=item,rows=[item]))
        else:groups[-1]['last']=item;groups[-1]['rows'].append(item)
    keys={};storage={};native=[]
    path=Path(d['session'])/'player-0/host.log'
    with path.open(errors='replace')as f:
        for line in f:
            m=re.search(r'D2B_CANONICAL frame=(\d+) slot=\d+ key=(\d+) remaining=(-?\d+)',line)
            if m:keys[int(m[1])]=(int(m[2]),int(m[3]))
            m=SNAP.search(line)
            if m and m[2]=='storage':storage[int(m[1])]=bytes.fromhex(m[6])
    for frame,(key,remaining)in keys.items():
        b=storage.get(frame)
        if b:native.append(dict(frame=frame,remaining_counter=remaining,charge=struct.unpack('<f',struct.pack('<I',struct.unpack_from('<I',b,0xd0c)[0]^key))[0]))
    sensors=[json.loads(x)for x in p.with_name('sensors.jsonl').read_text().splitlines()]if p.with_name('sensors.jsonl').exists()else[]
    for g in groups:
        rows=g['rows'];g['yaw_delta_deg']=math.degrees(math.atan2(math.sin(rows[-1]['yaw']-rows[0]['yaw']),math.cos(rows[-1]['yaw']-rows[0]['yaw'])))if rows[0]['yaw']is not None else None
        g['native']=[r for r in native if g['first']['frame']-4<=r['frame']<=g['last']['frame']]
        g['sensors']=[s for s in sensors if g['first']['frame']-4<=s['native_frame']<=g['last']['frame']]
    return dict(artifact=str(p.relative_to(ROOT)),artifact_sha256=sha(p),passed=d['passed'],errors=d['errors'],mode=d['hint_mode'],jump=d['jump_enabled'],meter=d['meter_mode'],events=d.get('events',[]),groups=groups,raw_sha256=d['raw_sha256'])
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('results',type=Path,nargs='+');ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();o=dict(schema='inklab.d3.hint.v1',full_d3_passed=False,runs=[reduce(p)for p in a.results]);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n')
    for r in o['runs']:
        print(r['artifact'],r['passed'],r['errors'])
        for g in r['groups']:
            print(g['label'],g['first']['frame'],g['last']['frame'],'yaw',g['yaw_delta_deg'],'y',g['first']['position'][1],g['last']['position'][1],'sp',g['first']['special'],g['last']['special'],'counter',[(v['frame'],v['remaining_counter'])for v in g['native'][:2]+g['native'][-2:]])
