#!/usr/bin/env python3
"""Attribute measured copy-encoder spans without guessing mixed-source costs."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
from analyze_a8_gpu import analyze as gpu_profile,read_stream,shared_union
from probe_a7_trial import ROOT,sha
from arena.runner import write_json_atomic


ORIGINS={
    'mtl_sub_copy':('game_native','buffer_copy'),
    'mtl_sub_update':('native_update_translation','inline_uniform_staging_copy'),
    'mtl_sub_fill':('game_native','buffer_fill'),
    'copy_t2t':('game_native','texture_copy'),
    'copy_b2t':('game_native','buffer_to_texture'),
    'copy_t2b':('game_native','texture_to_buffer'),
    'tex_upgrade_pfv':('translation','format_view_upgrade'),
    'fb_prepare':('translation','same_pass_feedback_snapshot'),
    'clear_rect_zero':('translation','scissored_clear_emulation'),
    'bright_lut':('translation','brightness_lut_snapshot'),
    'rt_clone':('translation','temporal_cache_clone'),
    'rt_blit_shift':('translation','temporal_cache_shift'),
    'up_flush':('translation','texture_upload'),
    'a8_uniform_scatter':('native_update_translation','masked_uniform_scatter'),
    'defer_ref':('diagnostic','deferred_reference_copy'),
    'defer_check':('diagnostic','deferred_reference_readback'),
}


def parse_sources(value):
    sources={}
    for entry in value.split(';') if value else []:
        name,ops,size,unknown=entry.split(':');numbers=list(map(int,(ops,size,unknown)))
        if name in sources or not name or any(v<0 for v in numbers) or numbers[0]==0 or numbers[2]>numbers[0]:raise ValueError('invalid copy source counters')
        sources[name]=dict(ops=numbers[0],bytes=numbers[1],unknown_bytes_ops=numbers[2])
    return sources


def source_label(sources):
    return next(iter(sources)) if len(sources)==1 else 'mixed+'+'+'.join(sorted(sources)) if sources else 'unattributed'


def classify(name):
    owner,operation=ORIGINS.get(name,('unknown','requires callsite inspection'))
    return dict(owner=owner,operation=operation)


def analyze(directory):
    gpu=gpu_profile(directory)
    plan=json.loads((directory/'plan.json').read_text())
    origins=defaultdict(lambda:dict(ops=0,bytes=0,unknown_bytes_ops=0))
    groups=defaultdict(lambda:dict(encoders=0,ops=0,bytes=0,unknown_bytes_ops=0,intra_barriers=0,span_sum_ms=0.,union_shared_ms=0.))
    events=defaultdict(lambda:dict(ops=0,bytes=0,cpu_ns=0,blocked=0));event_streams=[]
    for stream in gpu['streams']:
        rows=read_stream(ROOT/stream['path']);frames=defaultdict(list)
        for row in rows:
            if 'copy_sources' not in row:raise ValueError('source-instrumented stream required')
            sources=parse_sources(row['copy_sources']);label=source_label(sources)
            if row['kind']=='B':
                g=groups[label];g['encoders']+=1;g['intra_barriers']+=int(row['intra_barriers']);g['span_sum_ms']+=row['span_ms']
                for name,values in sources.items():
                    for k,v in values.items():origins[name][k]+=v;g[k]+=v
            elif sources:raise ValueError('copy metadata attached to a non-copy encoder')
            frames[row['frame']].append(row|dict(kind='B.'+label if row['kind']=='B' else 'other',w=0,h=0,cfmt=0,dfmt=0))
        for items in frames.values():
            _,allocated=shared_union(items)
            for key,ticks in allocated.items():
                if key.startswith('B.'):groups[key.split(':')[0][2:]]['union_shared_ms']+=1000*ticks/stream['frequency_hz']
    for n in range(3):
        binding=json.loads((directory/f'trial-{n}/a8-run.json').read_text())
        if len(binding.get('copy_event_sha256',{}))!=2:raise ValueError('six bound event streams required')
        for name,digest in binding['copy_event_sha256'].items():
            path=ROOT/name
            if sha(path)!=digest:raise ValueError('copy event stream changed')
            with path.open() as source:rows=list(csv.DictReader(source,delimiter='\t'))
            for row in rows:
                for k in ('ops','bytes','cpu_ns','blocked'):
                    v=int(row[k])
                    if v<0:raise ValueError('negative event counter')
                    events[row['origin'],row['action']][k]+=v
            event_streams.append(dict(path=name,sha256=digest,events=len(rows)))
    timeline=[]
    for label,g in groups.items():
        timeline.append(dict(source=label,**g,**classify(label),
            queue_boundary_barriers=2*g['encoders'],
            all_encoder_union_percent=100*g['union_shared_ms']/gpu['union_shared_ms']))
    timeline.sort(key=lambda r:r['union_shared_ms'],reverse=True)
    return dict(schema='arena.a8.copy-profile.v1',passed=True,accepts_a8=False,diagnostic_only=True,
        batch=str(directory),plan_sha256=sha(directory/'plan.json'),host_sha256=gpu['host_sha256'],
        analyzer_sha256=sha(Path(__file__)),gpu_profile=gpu,copy_timeline=timeline,
        origin_totals=[dict(source=k,**v,**classify(k)) for k,v in sorted(origins.items())],
        no_core_blit_observations=[dict(source=k,**classify(k),ops=0,bytes=0,all_encoder_union_percent=0) for k in sorted(ORIGINS) if k not in origins],
        cpu_and_external_events=[dict(source=k[0],action=k[1],**v) for k,v in sorted(events.items())],event_streams=event_streams,
        limitations=['encoder-boundary GPU spans include scheduling and instrumentation overhead',
            'mixed-origin encoder time remains a separate group; it is not distributed by bytes or operation counts',
            'texture bytes are logical payload for known uncompressed formats; unknown formats remain explicit',
            'external upload/readback event counts have no GPU-time attribution inside the original core-blit 40.15%',
            'CPU wait durations include condition/queue overhead and cannot be added to GPU spans'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=analyze(a.batch);write_json_atomic(a.out,r)
    print(json.dumps(r['copy_timeline'],indent=2))
