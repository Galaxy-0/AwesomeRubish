#!/usr/bin/env python3
"""Native release cost and sampled emergence bounds, without naming raw bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


def release_full(before_ink, released_ink, tolerance=.0002):
    # Charging reserves ink which may be refunded on a weak release. Only the
    # settled shot cost witnesses a full release, not the maximum reservation.
    return abs((before_ink-released_ink)-.117)<=tolerance


def analyze(path):
    result=json.loads(path.read_text());packets=[]
    log=Path(result['session'])/'player-0/host.log'
    with log.open() as stream:
        for line in stream:
            match=re.search(r'RL_STATE frame=(\d+) sequence=\d+ data=([0-9a-f]+)',line)
            if match:
                data=bytes.fromhex(match[2]);packets.append((int(match[1]),data))
    rows=[]
    for case in result['cases']:
        start,end=case['start_frame'],case['release_frame']
        settled=[(f,d) for f,d in packets if end+24<=f<=end+36]
        if not settled:raise ValueError('no settled native release sample')
        frame,data=settled[-1];ink=struct.unpack_from('<f',data,0x84)[0]
        row=dict(kind=case['kind'],hold_frames=case['hold_frames'],start_frame=start,release_frame=end,
                 settled_sample_frame=frame,retained_cost=1.-ink,full_release=release_full(1.,ink))
        if case['kind']=='surface-charge':
            window=[(f,d[0xf8]) for f,d in packets if start-8<=f<=end+36]
            human=next((f for f,form in window if f>start and form==1),None)
            squid=max((f for f,form in window if form==0 and (human is None or f<human)),default=None)
            row.update(last_squid_sample=squid,first_human_sample=human,
                       emergence_to_release_bounds=([max(0,end-human),end-max(start,squid)] if human is not None and squid is not None and end>=human else None))
        rows.append(row)
    thresholds={}
    for kind in ('standing-charge','surface-charge'):
        full=[r for r in rows if r['kind']==kind and r['full_release']]
        thresholds[kind]=min((r['hold_frames'] for r in full),default=None)
    return dict(evidence=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                rows=rows,minimum_observed_full_release=thresholds,
                caveat='Empirical minima in sampled input phases; native form transition is bounded by packet timestamps, not by button intent.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('result',type=Path)
    args=parser.parse_args();analysis=analyze(args.result)
    args.result.with_name('timing-analysis.json').write_text(json.dumps(analysis,indent=2)+'\n')
    print(json.dumps(analysis,indent=2))
