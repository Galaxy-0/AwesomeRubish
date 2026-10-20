#!/usr/bin/env python3
"""Rank Metal 4 encoder GPU spans by actual targets under three-room load.

Spans include scheduling/interference and can overlap. Report both summed
spans and a union timeline with overlapping intervals shared equally; neither
is a hardware-exclusive execution counter. Profiled FPS is not acceptance data.
"""
import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import re
import statistics
from probe_a7_trial import ROOT,sha
from arena.runner import write_json_atomic


def category(row):
    return f"{row['kind']}:{row['w']}x{row['h']}:c{row['cfmt']}:d{row['dfmt']}"


def shared_union(rows):
    events=defaultdict(list)
    for n,r in enumerate(rows):
        events[r['t0_tick']].append((n,1));events[r['t1_tick']].append((n,-1))
    active=set();previous=None;allocated=defaultdict(float);covered=0
    for t,changes in sorted(events.items()):
        if previous is not None and active:
            dt=t-previous;covered+=dt
            for n in active:allocated[category(rows[n])]+=dt/len(active)
        # Zero-length spans do not enter the active set.
        for n,delta in sorted(changes,key=lambda x:x[1]):
            if rows[n]['t0_tick']==rows[n]['t1_tick']:continue
            if delta<0:active.remove(n)
            else:active.add(n)
        previous=t
    if active:raise AssertionError('unclosed GPU span')
    return covered,allocated


def read_stream(path):
    with path.open() as stream:
        rows=list(csv.DictReader((s for s in stream if not s.startswith('#')),delimiter='\t'))
    numeric=('frame','relative','encoder','pass','w','h','cfmt','dfmt','draws','t0_tick','t1_tick','frequency_hz')
    for r in rows:
        for k in numeric:r[k]=int(r[k])
        r['span_ms']=float(r['span_ms'])
        if not math.isfinite(r['span_ms']) or r['span_ms']<0:raise ValueError('invalid GPU span')
        if r['frequency_hz']<=0 or r['t1_tick']<r['t0_tick'] or r['t0_tick']<=0:raise ValueError('invalid GPU timestamp')
        actual=1000*(r['t1_tick']-r['t0_tick'])/r['frequency_hz']
        if abs(actual-r['span_ms'])>1e-5:raise ValueError('GPU counter unit mismatch')
    if not rows:raise ValueError('empty GPU stream '+str(path))
    return rows


def analyze(out):
    plan=json.loads((out/'plan.json').read_text());done=json.loads((out/'completed.json').read_text())
    if not (plan['parallel']==3 and plan['repeats']==3 and plan.get('pass_gpu') and done['passed']):raise ValueError('completed three-room diagnostic required')
    if done['plan_sha256']!=sha(out/'plan.json'):raise ValueError('diagnostic plan changed')
    build=json.loads(Path(plan['host']).with_suffix('.build.json').read_text())
    if build['render_mode']!='none':raise ValueError('full-render profile required before selecting skips')
    if sha(Path(plan['host']))!=build['output_sha256']:raise ValueError('profile executable changed')
    expected=set()
    for interval in plan['pass_gpu_ranges'].split(','):
        if not re.fullmatch(r'\d+-\d+',interval):raise ValueError('invalid sampling interval')
        lo,hi=map(int,interval.split('-'));expected.update(range(lo,hi+1))
    accum=defaultdict(lambda:dict(spans=[],allocated_ms=0,draws=0,frames=set()))
    streams=[];largest=[];total_sum=0.;total_union=0.;window_counts=defaultdict(int)
    for n in range(3):
        directory=out/f'trial-{n}';result_path=directory/'result.json';trial=json.loads(result_path.read_text())
        binding=json.loads((directory/'a8-run.json').read_text());match=trial['match']
        if not (trial['passed'] and match['native_winners'] and not match['void'] and binding['pass_gpu']):raise ValueError('incomplete diagnostic trial')
        if binding['trial_sha256']!=sha(result_path):raise ValueError('diagnostic trial changed')
        if len(binding['pass_gpu_sha256'])!=2:raise ValueError('both host streams required')
        for name,digest in binding['pass_gpu_sha256'].items():
            path=ROOT/name
            if sha(path)!=digest:raise ValueError('GPU stream changed')
            rows=read_stream(path);freq={r['frequency_hz'] for r in rows}
            if len(freq)!=1:raise ValueError('mixed timestamp clocks')
            if {r['relative'] for r in rows}!=expected:raise ValueError('sampling window incomplete')
            hz=freq.pop();frames=defaultdict(list)
            for r in rows:frames[r['frame']].append(r)
            union_ms=0.;sum_ms=0.
            for frame,items in frames.items():
                covered,allocated=shared_union(items);union_ms+=1000*covered/hz
                for key,ticks in allocated.items():accum[key]['allocated_ms']+=1000*ticks/hz
                for r in items:
                    key=category(r);a=accum[key];a['spans'].append(r['span_ms']);a['draws']+=r['draws'];a['frames'].add((name,frame))
                    sum_ms+=r['span_ms']
                    largest.append(dict(stream=name,**r))
                relative=min(r['relative'] for r in items)
                window_counts['early' if relative<2000 else 'middle' if relative<6000 else 'late']+=1
            total_sum+=sum_ms;total_union+=union_ms
            streams.append(dict(path=name,sha256=digest,frames=len(frames),encoders=len(rows),frequency_hz=hz,
                span_sum_ms=sum_ms,union_ms=union_ms,overlap_fraction=1-union_ms/sum_ms if sum_ms else 0))
    if len(streams)!=6 or any(not v for v in window_counts.values()) or len(window_counts)!=3:raise ValueError('six hosts and three time windows required')
    if total_sum<=0 or total_union<=0:raise ValueError('positive measured GPU time required')
    categories=[]
    for key,a in accum.items():
        categories.append(dict(target=key,encoders=len(a['spans']),frames=len(a['frames']),span_sum_ms=sum(a['spans']),
            span_mean_ms=statistics.mean(a['spans']),span_median_ms=statistics.median(a['spans']),span_max_ms=max(a['spans']),
            span_share_percent=100*sum(a['spans'])/total_sum,union_shared_ms=a['allocated_ms'],
            union_shared_percent=100*a['allocated_ms']/total_union,draws=a['draws'],
            protection='retain paint target' if ':1600x1600:' in key else 'retain compute/storage/copy' if key[0] in 'CB' else 'requires consumer/readback proof before changing'))
    categories.sort(key=lambda r:r['union_shared_ms'],reverse=True)
    return dict(schema='arena.a8.gpu-profile.v1',passed=True,diagnostic_only=True,accepts_a8=False,
        source_batch=str(out),plan_sha256=sha(out/'plan.json'),host_sha256=sha(Path(plan['host'])),analyzer_sha256=sha(Path(__file__)),
        streams=streams,window_frame_counts=dict(window_counts),categories=categories,
        largest_individual_spans=sorted(largest,key=lambda r:r['span_ms'],reverse=True)[:40],
        span_sum_ms=total_sum,union_shared_ms=total_union,
        attribution='Per-host/frame timestamp interval union; overlap shared equally. Aggregate shares describe measured encoder latency under contention, not exclusive device utilization.',
        limitations=['timestamps perturb scheduling; use separate uninstrumented trials for speedup',
            'old-queue readback/upload and CPU gaps are outside these encoder intervals',
            'target dimensions alone do not establish whether a pass is safe to skip'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=analyze(a.batch);write_json_atomic(a.out,r)
    print(json.dumps(r['categories'][:15],indent=2))
