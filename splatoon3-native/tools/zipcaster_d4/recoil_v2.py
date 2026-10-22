"""Forced displacement aligned to native HP and position sample clocks.

Public request/receipt frames are not substituted for native position sample
frames. Contact20+projectile35 is a separate observed joint profile.
"""
import argparse
import json
import re
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha


def fit(paths):
    groups={};evidence={}
    for path in paths:
        path=path.resolve();d=json.loads(path.read_text());evidence[str(path.relative_to(ROOT))]=sha(path)
        if not d.get('records'):continue
        raw=[]
        for m in re.finditer(r'RL_DAMAGE frame=(\d+) slot=\d+ hp=(-?\d+)',(Path(d['session'])/'player-1/host.log').read_text()):raw.append((int(m[1]),int(m[2])))
        for row in d['records']:
            before=row['before'];start=before['player_0']['frame'];offset=start-before['player_1']['frame'];last_frame=row['history'][-1]['infos']['player_0']['frame']
            last=1000;edges=[]
            for f,hp in raw:
                f+=offset
                if start<f<=last_frame and last-hp>=190:edges.append((f,(last-hp)/10))
                last=hp
            if not edges or not row['after']['player_1']['alive']:continue
            drops=[e[1]for e in edges]
            if row['style']=='full'and drops==[70.]:kind='full'
            elif row['style']=='light'and drops==[35.]:kind='light'
            elif row['style']=='light'and drops==[20.,35.]:kind='light_contact_then_projectile'
            else:continue
            first=edges[0][0];enemy=np.array(before['player_1']['position']);source=np.array(before['player_0']['position']);direction=enemy-source;direction[1]=0;direction/=np.linalg.norm(direction)
            samples={}
            for infos in [before]+[h['infos']for h in row['history']]:
                info=infos['player_1'];t=info['position_sample_frame']+offset-first
                samples[t]=dict(distance=float((np.array(info['position'])-enemy)@direction),position=info['position'])
            times=sorted(samples);values=[samples[t]['distance']for t in times]
            groups.setdefault(kind,[]).append(dict(artifact=str(path.relative_to(ROOT)),case=row.get('id',row['index']),
                first_hp_frame=first,hp_events=[dict(age=f-first,drop=v)for f,v in edges],times=times,distance=values,
                vertical_delta=max(abs(samples[t]['position'][1]-enemy[1])for t in times if t>=0)))
    profiles={}
    for kind,rows in groups.items():
        times=list(range(0,49,2));values=[];counts=[];errors=[]
        for t in times:
            obs=[float(np.interp(t,r['times'],r['distance']))for r in rows if r['times'][-1]>=t and r['vertical_delta']<.05]
            if not obs:break
            median=float(np.median(obs));values.append(median);counts.append(len(obs));errors.append(max(abs(x-median)for x in obs))
        if values:profiles[kind]=dict(frames=times[:len(values)],distance=values,n_by_frame=counts,
                maximum_absolute_residual=errors,measured_until=times[len(values)-1],tail_supported=False,
                joint_hp_ages=rows[0]['hp_events']if kind=='light_contact_then_projectile'else None)
    return dict(schema='inklab.d4.recoil.v2',profiles=profiles,cases=groups,evidence_sha256=evidence,
        tool_sha256=sha(__file__),limits=['Native HP callback clock and native position sample clock normalized by each case frame offset.',
        'Piecewise linear empirical flat-support motion only; ledge fall/wall collisions excluded from pooled profile.',
        'A joint20+35 profile is not two independent35 impulses. Contact-only20 motion not measured.',
        'Held tails unsupported; sample quantization and one-case joint profile are not a universal dynamics proof.'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,nargs='+',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('fresh output required')
    a.out.write_text(json.dumps(fit(a.results),indent=2)+'\n')
