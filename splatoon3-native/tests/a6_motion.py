"""Post-step referee packet survey, never a policy observation extension.

The adjacent +0xfc hypothesis was REJECTED: roll and ordinary-jump trials
returned the same large non-enum word. PlayerNetState_Squid's bool/two-bit
codec layout does not establish its offset in the enclosing packet. Keep this
survey as evidence of that failed inference; never expose a named mode field.

The encoder dispatches the form-tagged payload at +0xc8. For squid only, its
vtable is main+0x5d2bf08 (constructor 0x280a2ec), and codec 0x280a380 reads
payload+0x20 bool / +0x24 two-bit value. These are structurally established
fields; their gameplay meanings still require matched native calibration.
"""
import json
from pathlib import Path
import re
import struct
import hashlib
from a6_metrics import roll_witness


def squid_packets(session,player=0,start=None,end=None):
    packets=[]
    main_base=None
    with (Path(session)/f'player-{player}/host.log').open() as stream:
        for line in stream:
            base=re.search(r'main: base (0x[0-9a-f]+)',line)
            if base:main_base=int(base[1],16)
            if not line.endswith('\n'):continue  # live log may end mid-write
            match=re.search(r'RL_STATE frame=(\d+) sequence=\d+ data=([0-9a-f]+)',line)
            if match is None:continue
            frame=int(match[1])
            if start is not None and frame<start or end is not None and frame>end:continue
            data=bytes.fromhex(match[2])
            if len(data)!=0x1f0:raise ValueError('unexpected native packet length')
            form=struct.unpack_from('<I',data,0xf8)[0]
            tag=struct.unpack_from('<Q',data,0xc8)[0]
            layout=form==0 and main_base is not None and tag==main_base+0x5d2bf08
            boolean=data[0xe8] if layout else None
            value=struct.unpack_from('<I',data,0xec)[0] if layout else None
            if layout and (boolean not in (0,1) or value not in range(4)):
                raise ValueError('squid payload does not match the validated codec bounds')
            packets.append(dict(frame=frame,is_human=form,raw_word_fc=struct.unpack_from('<I',data,0xfc)[0],
                                squid_payload_layout_verified=layout,squid_payload_bool=boolean,
                                squid_payload_two_bit=value,position=list(struct.unpack_from('<3f',data,0x20))))
    return packets


def summaries(result):
    packets=squid_packets(result['session']);rows=[]
    for case in result['cases']:
        if 'before' not in case or 'after' not in case:continue
        before,after=case['before'],case['after']
        if 'frame' not in before:before,after=before['0'],after['0']
        selected=[p for p in packets if before['frame']<=p['frame']<=after['frame']]
        transitions=[]
        payload=[]
        for p in selected:
            if not transitions or transitions[-1]['raw_word_fc']!=p['raw_word_fc']:
                transitions.append(dict(frame=p['frame'],raw_word_fc=p['raw_word_fc']))
            pair=[p['squid_payload_bool'],p['squid_payload_two_bit']]
            if not payload or payload[-1]['value']!=pair:
                payload.append(dict(frame=p['frame'],value=pair))
        rows.append(dict(kind=case['kind'],start=before['frame'],end=after['frame'],
                         rejected_word_transitions=transitions,payload_transitions=payload,
                         peak_y=max((p['position'][1] for p in selected),default=None),
                         start_position=before['position'],end_position=after['position']))
    return rows


def calibrate_roll(path):
    path=Path(path).resolve();result=json.loads(path.read_text())
    if 'freeze_after' not in result:raise ValueError('calibration run is not closed')
    if result.get('errors') not in ([],["RuntimeError('A6 normal match duration exhausted')"]):
        raise ValueError('native calibration failed outside normal duration')
    kinds={'swim-forward-jump-control':(False,True),'swim-reverse-control':(True,False),
           'squid-roll-matched':(True,True)}
    steps=path.with_name('steps.jsonl');data=[json.loads(line) for line in steps.read_text().splitlines()]
    features={}
    for kind,(reverse,jump) in kinds.items():
        case=next(c for c in result['cases'] if c['kind']==kind)
        first=case['before'];start=first['frame'];edge=start+30
        selected=[row for row in data if start<row['infos']['player_0']['frame']<=case['after']['frame']]
        covered=set()
        for row in selected:
            end=row['infos']['player_0']['frame'];action=row['actions']['player_0']
            for frame in range(end-row['frames'],end):
                elapsed=frame-start
                if not 0<=elapsed<46:continue
                expected_y=-1. if reverse and elapsed>=30 else 1.
                expected_b=int(jump and elapsed==30)
                if action['buttons']!=[0,1,0,0,expected_b,0] or action['sticks']!=[0.,expected_y,0.,0.]:
                    raise ValueError('matched native control inputs differ: '+kind)
                covered.add(elapsed)
        if covered!=set(range(46)):raise ValueError('matched native control input gap')
        run_up=[first]+[row['infos']['player_0'] for row in selected if row['infos']['player_0']['frame']<=edge]
        before=run_up[-1]
        samples=[row['infos']['player_0'] for row in selected if row['infos']['player_0']['frame']>edge]
        features[kind]=roll_witness(run_up,before,samples)
    forward,reverse,roll=(features[k] for k in kinds)
    distances=[f['run_up_distance'] for f in features.values()]
    passed=(all(f['run_up_valid'] for f in features.values()) and max(distances)/min(distances)<1.3 and
            not forward['verified'] and not reverse['verified'] and
            forward['peak_height_over_ground']<1. and reverse['peak_height_over_ground']<.1 and roll['verified'])
    screenshots={}
    for kind in kinds:
        for offset in ((33,37,41) if kind=='squid-roll-matched' else (3,7,11)):
            image=path.with_name(f'{kind}-{offset}-player_0.png')
            screenshots[str(image)]=hashlib.sha256(image.read_bytes()).hexdigest()
    return dict(schema='arena.a6.roll-calibration.v1',passed=bool(passed),
                source=str(path),source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                steps_sha256=hashlib.sha256(steps.read_bytes()).hexdigest(),controls=features,screenshots_sha256=screenshots,
                identity='matched-speed boosted reversal arc; early screenshots retained for manual review',
                limitations='does not establish a network enum, invulnerability or armor duration')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('result',type=Path)
    args=parser.parse_args();rows=summaries(json.loads(args.result.read_text()))
    args.result.with_name('motion-layout-analysis.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(rows,indent=2))
