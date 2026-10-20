#!/usr/bin/env python3
"""Audit all A8 trials, then compare scores and aligned native trajectories.

The empirical gate is declared before the experiment: mean trajectory RMS
difference <= maximum within-group pairwise RMS, separately for each player
and measurement. It is not a confidence interval or a determinism assertion.
"""
import argparse
import itertools
import json
from pathlib import Path
import statistics
import re
import sys
import numpy as np
from probe_a7_trial import ROOT,sha
from probe_a7_repeatability import compare,spawn_identity
from arena.runner import write_json_atomic


def actual_copy_reduction(lines,mode):
    for line in lines:
        match=re.search(r'A8_COPY '+re.escape(mode)+r' native_updates=(\d+) '+('copies' if mode=='coalesce' else 'dispatches')+r'=(\d+)',line)
        if not match:continue
        native,encoded=map(int,match.groups())
        if not 0<encoded<native:continue
        if mode=='coalesce':
            saved=re.search(r' saved=(\d+)',line)
            if not saved or int(saved[1])!=native-encoded:continue
        return True
    return False


def gpu_timings(session,barriers):
    result={}
    for player in (0,1):
        agent=f'player_{player}';first=barriers[0]['infos'][agent]['frame']-barriers[0]['frame']
        values={};span={}
        with (session/f'player-{player}/gpu.tsv').open() as stream:
            for line in stream:
                parts=line.strip().replace('\\t','\t').split('\t')
                if len(parts)!=3 or not parts[0].isdigit():continue
                frame=int(parts[0]);key=parts[1]
                if not first<frame<=first+10920 or frame in (1800,1801):continue
                value=float(parts[2])
                if key in ('@frame_ms','@nvn_ms','@work_ms','@passes','@draws') and value>=0:values.setdefault(key,[]).append(value)
                if key in ('@gpu_beg_ms','@gpu_end_ms'):span.setdefault(frame,{})[key]=value
        times=[v['@gpu_end_ms']-v['@gpu_beg_ms'] for v in span.values() if len(v)==2 and v['@gpu_end_ms']>=v['@gpu_beg_ms']]
        if times:values['gpu_timeline_span_ms']=times
        result[agent]={k:dict(samples=len(v),mean=statistics.mean(v),maximum=max(v)) for k,v in values.items()}
    return result


def trajectory_comparison(before,after):
    groups=[np.asarray(v,dtype=float) for v in (before,after)]
    if any(len(v)<3 or not np.isfinite(v).all() for v in groups):raise ValueError('three finite trajectories required')
    if groups[0].shape[1:]!=groups[1].shape[1:]:raise ValueError('trajectory shapes differ')
    rms=lambda a,b:float(np.sqrt(np.mean((a-b)**2)))
    within=[[dict(indices=[i,j],rms=rms(g[i],g[j]),max_abs=float(np.max(np.abs(g[i]-g[j]))))
        for i,j in itertools.combinations(range(len(g)),2)] for g in groups]
    upper=max(p['rms'] for pairs in within for p in pairs)
    delta=rms(*(np.mean(g,axis=0) for g in groups))
    cross=[dict(before=i,after=j,rms=rms(a,b),max_abs=float(np.max(np.abs(a-b))))
        for i,a in enumerate(groups[0]) for j,b in enumerate(groups[1])]
    return dict(passed=delta<=upper+1e-6,mean_trajectory_rms=delta,within_maximum_rms=upper,
        within=dict(before=within[0],after=within[1]),cross_pairs=cross,
        mean_trajectory_max_abs=float(np.max(np.abs(np.mean(groups[0],axis=0)-np.mean(groups[1],axis=0)))))


def load_group(out):
    plan=json.loads((out/'plan.json').read_text());done=json.loads((out/'completed.json').read_text())
    if plan.get('pass_gpu'):raise ValueError('instrumented diagnostic batch cannot certify performance')
    if not done['passed'] or plan['repeats']<3:raise ValueError('complete three-trial batch required')
    if done.get('plan_sha256')!=sha(out/'plan.json'):raise ValueError('batch plan changed')
    trials=[];identity=None
    for n in range(plan['repeats']):
        directory=out/f'trial-{n}';path=directory/'result.json';r=json.loads(path.read_text());m=r['match']
        bind=json.loads((directory/'a8-run.json').read_text())
        if bind.get('pass_gpu') or bind.get('profile'):raise ValueError('instrumented trial cannot certify performance')
        if not (r['passed'] and bind['passed'] and m['native_winners'] and not m['void'] and not m['errors']):raise ValueError('invalid trial '+str(path))
        if bind['trial_sha256']!=sha(path) or bind['entry_sha256']!=plan['trial_entry_sha256']:raise ValueError('trial binding changed')
        for file,digest in bind['timing_sha256'].items():
            if sha(ROOT/file)!=digest:raise ValueError('timing stream changed')
        ident={k:r[k] for k in ('runtime_sha256','source_hashes','policy_step_frames','stage','seed_words')}
        if identity is None:identity=ident
        elif ident!=identity:raise ValueError('mixed runtime/parameters within group')
        barriers=[json.loads(line) for line in (directory/'match/native-barriers.jsonl').read_text().splitlines()]
        final=barriers[-1]['infos'];peer_turf=[]
        for player in (0,1):
            row=final[f'player_{player}']
            if not (row['phase']==3 and row['turf_valid'] and row['score_valid'] and row['score_units']==1):raise ValueError('native final turf measurement unavailable')
            if not np.allclose(np.asarray(row['turf_ratio'])*100,row['score'],atol=1e-5,rtol=0):raise ValueError('native turf/score units disagree')
            peer_turf.append(row['turf_ratio'][::1 if player==0 else -1])
        native_turf=np.mean(peer_turf,axis=0).tolist()
        # Controlled, pre-settlement samples only. Both groups must have the
        # identical frame grid; no interpolation can conceal missing samples.
        samples={row['frame']:row['infos'] for row in barriers if row['frame']<=10920}
        if not samples or any(any(not inf[k+'_valid'] for k in ('position','hp','ink')) for v in samples.values() for inf in v.values()):raise ValueError('missing native measurement')
        inputs=[json.loads(line)['actions'] for line in (directory/'match/inputs-per-present.jsonl').read_text().splitlines()]
        if len(inputs)<10920:raise ValueError('fixed input plan truncated')
        session=Path(m['session']);skips=[];shadows=[];hdr=[];copies=[]
        for player in (0,1):
            home=session/f'player-{player}';options=json.loads((home/'input.json').read_text());log=(home/'host.log').read_text(errors='replace')
            if options.get('DM_SCENE_SEEDS')!='1,2,3,4' or options.get('DM_RL_CLOCK_MODE')!='fixed60' or options.get('DM_TEST_SPECIAL'):raise ValueError('wrong native runtime settings')
            if options.get('DM_NVN_PASSGPU4') or options.get('DM_NVN_PASSGPU'):raise ValueError('GPU instrumentation cannot certify performance')
            if not any('A7_SEEDS origin=consumed ' in s and 'requested_match=1' in s for s in log.splitlines()):raise ValueError('missing native seed consumption')
            if 'A8_CAMERA unsafe samples report' in log:raise ValueError('camera affected native query')
            if 'A8_HDR unsafe consumer=' in log:raise ValueError('HDR output escaped into a retained consumer')
            skips.append([s for s in log.splitlines() if 'A8_CAMERA skipped=' in s])
            shadows.append([s for s in log.splitlines() if 'A8_SHADOW layer=' in s])
            hdr.append([s for s in log.splitlines() if 'A8_HDR skipped=' in s])
            copies.append([s for s in log.splitlines() if 'A8_COPY ' in s and 'native_updates=' in s])
        trials.append(dict(result=r,path=str(path),sha256=sha(path),spawn=spawn_identity(barriers[0]['infos']),
            samples=samples,inputs=inputs,skips=skips,shadows=shadows,hdr=hdr,copies=copies,native_turf=native_turf,gpu_timings=gpu_timings(session,barriers)))
    return plan,trials


def analyze(before,after):
    plans,trials=zip(*(load_group(p) for p in (before,after)))
    if plans[0]['parallel']!=3 or plans[1]['parallel']!=3:raise ValueError('significant-speedup gate requires two three-room batches')
    builds=[json.loads(Path(p['host']).with_suffix('.build.json').read_text()) for p in plans]
    if any(b.get('experimental_hdr') for b in builds):raise ValueError('unsupported HDR candidate cannot certify A8; resolve the native-smoke consumer guard first')
    copy_mode=builds[1].get('copy_mode','none')
    if builds[0]['render_mode']!='none' or builds[0].get('copy_mode','none')!='none' or builds[1]['render_mode'] not in ('none','camera') or (builds[1]['render_mode']=='none' and copy_mode=='none'):raise ValueError('expected full-render control and an explicit render/copy candidate')
    if copy_mode not in ('none','coalesce','scatter'):raise ValueError('unknown copy candidate')
    if builds[0]['source_sha256']!=builds[1]['source_sha256']:raise ValueError('full/camera compile sources differ')
    if any(not p.get('complete_build_inputs') for p in builds):raise ValueError('complete renderer build identity required')
    commands=[];common=[]
    for plan,build,group in zip(plans,builds,trials):
        command=list(build['command']);command[command.index('-o')+1]='<OUTPUT>'
        flags=[v for v in command if v.startswith('-DSPL3_A8_COPY=')]
        expected={'none':[],'coalesce':['-DSPL3_A8_COPY=1'],'scatter':['-DSPL3_A8_COPY=2']}.get(build.get('copy_mode','none'))
        if flags!=expected:raise ValueError('copy build flags disagree with manifest')
        commands.append([v for v in command if v not in ('-DSPL3_A8_CAMERA=1','-DSPL3_A8_COPY=1','-DSPL3_A8_COPY=2')])
        host=Path(plan['host'])
        common.append({k:v for k,v in group[0]['result']['runtime_sha256'].items() if Path(k) not in (host,host.with_suffix('.build.json'))})
        if sha(host)!=build['output_sha256']:raise ValueError('host executable changed')
    if commands[0]!=commands[1] or common[0]!=common[1]:raise ValueError('unrelated runtime/build flags differ')
    all_trials=trials[0]+trials[1];reference=all_trials[0]
    neutral=dict(sticks=[0.]*4,gyro=[0.]*3,buttons=[0]*6);tail={f'player_{i}':neutral for i in (0,1)}
    for t in all_trials:
        if t['spawn']!=reference['spawn']:raise ValueError('actual starting position/heading/slot mismatch')
        for k in ('source_hashes','policy_step_frames','stage','seed_words'):
            if t['result'][k]!=reference['result'][k]:raise ValueError('fixed parameters differ: '+k)
        if list(t['samples'])!=list(reference['samples']):raise ValueError('controlled sample frames differ')
        for i in range(max(len(t['inputs']),len(reference['inputs']))):
            if (t['inputs'][i] if i<len(t['inputs']) else tail)!=(reference['inputs'][i] if i<len(reference['inputs']) else tail):raise ValueError('executed input differs at '+str(i))
    for t in trials[1]:
        if builds[1]['render_mode']=='camera' and not all(t['skips']):raise ValueError('candidate did not actually skip camera draws on both players')
        if copy_mode!='none' and not all(actual_copy_reduction(lines,copy_mode) for lines in t['copies']):raise ValueError('candidate did not actually reduce uniform operations on both players')
        if b'A8_SHADOW layer=%d' in Path(plans[1]['host']).read_bytes():
            if not all(all(any(f'A8_SHADOW layer={layer} ' in line for line in lines) for layer in (0,1)) for lines in t['shadows']):raise ValueError('both shadow layers must actually be skipped on both players')
        if b'A8_HDR skipped=%llu' in Path(plans[1]['host']).read_bytes():
            if not all(t['hdr']):raise ValueError('HDR candidate did not actually run on both players')
    score=compare(*[[t['result']['match']['score_by_role'] for t in group] for group in trials])
    turf=compare(*[[t['native_turf'] for t in group] for group in trials])
    measurements={}
    for player in ('player_0','player_1'):
        for key in ('position','hp','ink'):
            arrays=[[[v[player][key] for v in t['samples'].values()] for t in group] for group in trials]
            measurements[player+'/'+key]=trajectory_comparison(*arrays)
    def metrics(group,directory):
        done=json.loads((directory/'completed.json').read_text())
        return dict(controlled_fps=statistics.mean(t['result']['controlled_fps'] for t in group),
            trials=len(group),batch_wall_seconds=done['wall_seconds'],games_per_hour=3600*len(group)/done['wall_seconds'],
            wall_seconds=statistics.mean(t['result']['wall_seconds'] for t in group),
            gpu_percent=statistics.mean(t['result']['gpu_utilization_percent_by_phase']['controlled']['mean'] for t in group),
            phase_wall_seconds={key:statistics.mean(t['result']['phase_wall_seconds'][key] for t in group) for key in group[0]['result']['phase_wall_seconds']})
    performance=dict(before=metrics(trials[0],before),after=metrics(trials[1],after))
    performance['fps_ratio']=performance['after']['controlled_fps']/performance['before']['controlled_fps']
    performance['batch_throughput_ratio']=performance['after']['games_per_hour']/performance['before']['games_per_hour']
    return dict(schema='arena.a8.comparison.v1',passed=score['passed'] and turf['passed'] and all(m['passed'] for m in measurements.values()) and performance['fps_ratio']>=1.2,
        equivalence_passed=score['passed'] and turf['passed'] and all(m['passed'] for m in measurements.values()),
        significant_speedup=performance['fps_ratio']>=1.2,scores=score,turf_ratios=turf,trajectories=measurements,performance=performance,
        frames_compared=list(reference['samples']),actual_spawn=reference['spawn'],
        batch_plans=[dict(path=str(p/'plan.json'),sha256=sha(p/'plan.json')) for p in (before,after)],
        trials=[[dict(path=t['path'],sha256=t['sha256'],scores=t['result']['match']['score_by_role'],outcome=t['result']['match']['outcome'],
            controlled_fps=t['result']['controlled_fps'],wall_seconds=t['result']['wall_seconds'],camera_skip_logs=t['skips'],shadow_skip_logs=t['shadows'],hdr_skip_logs=t['hdr'],copy_logs=t['copies'],gpu_timings=t['gpu_timings']) for t in group] for group in trials],
        limitations=['empirical noise gate, not determinism or a statistical bound','native final turf ratio; real-time world paint map remains unknown','GPU utilization is whole-machine; GPU timeline span is not exclusive execution time'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','after','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=analyze(a.before.resolve(),a.after.resolve());write_json_atomic(a.out,r)
    print(json.dumps({k:r[k] for k in ('passed','equivalence_passed','significant_speedup','performance')},indent=2))
    raise SystemExit(0 if r['passed'] else 1)
