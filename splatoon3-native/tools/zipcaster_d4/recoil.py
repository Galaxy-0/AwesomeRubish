"""Conditional forced target displacement, fitted from old own-pose traces.

Not voluntary opponent movement. Unobserved light-tail extrapolation is marked
unsupported, rather than silently holding the original enemy point forever.
"""
import argparse,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha

def displacement(profile,style,age):
    p=profile[style];age=np.asarray(age,float)
    return np.interp(age,[-1]+p['frames'],[0]+p['distance'],left=0)

def fit(paths):
    profiles={};evidence={}
    for path in paths:
        d=json.loads(path.read_text());evidence[str(path.relative_to(ROOT))]=sha(path)
        steps=[json.loads(l)for l in path.with_name('steps.jsonl').open()]
        if 'records'in d:
            cases=[dict(style=r['style'],before=r['before'],rows=r['history'])for r in d['records']]
        else:
            cases=[]
            for e in d['events']:
                if e['event']not in ['full-release','light-input']:continue
                f=e['infos']['player_0']['frame']
                cases.append(dict(style='full'if e['event']=='full-release'else'light',before=e['infos'],rows=[r for r in steps if f<r['infos']['player_0']['frame']<=f+85]))
        for case in cases:
            before=case['before'];rows=case['rows'];last=before['player_1']['hp'];hit=None;next_hit=None
            for r in rows:
                value=r['infos']['player_1']['hp'];drop=last-value;last=value
                if drop>.19:
                    if hit is None:
                        if value<=0:break
                        hit=r
                    else:next_hit=r;break
            if hit is None:continue
            f=hit['infos']['player_0']['frame'];q=np.array(before['player_1']['position']);p=np.array(before['player_0']['position']);direction=q-p;direction[1]=0;direction/=np.linalg.norm(direction)
            tail=[r for r in rows if f<=r['infos']['player_0']['frame'] and (next_hit is None or r['infos']['player_0']['frame']<next_hit['infos']['player_0']['frame'])]
            times=[r['infos']['player_0']['frame']-f for r in tail]
            distances=[float((np.array(r['infos']['player_1']['position'])-q)@direction)for r in tail]
            profiles.setdefault(case['style'],[]).append(dict(times=times,distance=distances,artifact=str(path.relative_to(ROOT)),receipt_frame=f))
    out={}
    for style,rows in profiles.items():
        horizon=min(48 if style=='full'else 24,max(r['times'][-1]for r in rows))
        times=list(range(0,horizon+1,4));values=[];counts=[]
        for t in times:
            sample=[float(np.interp(t,r['times'],r['distance']))for r in rows if r['times'][-1]>=t]
            values.append(float(np.median(sample)));counts.append(len(sample))
        out[style]=dict(frames=times,distance=values,n_by_frame=counts,evidence_cases=len(rows),measured_until=horizon,tail_supported=False)
    return dict(schema='inklab.d4.recoil.v1',profiles=out,evidence_sha256=evidence,scope='Forced displacement projected along shot horizontal bearing, conditional on nonlethal observed HP receipt. Median sampled old traces; no new outcomes used. No generic ledge/fall/wall-body validation; extrapolated tail explicitly unsupported.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('fresh fit output')
    paths=[ROOT/'work/a6/d3-r-d4-attack-r1-District00-central_high-top1-20261022-143043-749479/result.json',ROOT/'work/a6/d3-r-d4-duel5-attack-r2-Yunohana-center-top1-h1-r0-20261022-144326-261885/result.json']
    d=fit(paths);d['source_sha256']=sha(__file__);a.out.write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d['profiles'],indent=2))
