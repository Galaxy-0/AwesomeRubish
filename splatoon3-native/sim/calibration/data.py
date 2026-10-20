"""Normalize calibration packet stamps/actions; never invent future samples."""
import json
from pathlib import Path
import numpy as np

from sim.corpus import Trace,FIELDS
from sim.parameters import ROOT,sha256


def load(directory):
    directory=Path(directory).resolve()
    result=json.loads((directory/'result.json').read_text())
    rows=[json.loads(line) for line in (directory/'steps.jsonl').open()]
    origins={k:i['frame'] for k,i in result['origins'].items()}
    rows=[r for r in rows if all(i['phase']==1 for i in r['infos'].values())]
    end=max(r['infos']['player_0']['frame']-origins['player_0'] for r in rows)
    states=np.full((end+1,2,12),np.nan)
    actions=np.full((end,2,13),np.nan,np.float32)
    available=np.full((end+1,2),end+1,int)
    labels=np.full(end,'',dtype='U80')
    for row in rows:
        f=row['infos']['player_0']['frame']-origins['player_0']
        if row['frames']:
            lo=f-row['frames']
            if lo<0 or np.isfinite(actions[lo:f]).any():raise ValueError('overlap/negative interval')
            labels[lo:f]=row['label']
            for role in (0,1):
                a=row['actions'][f'player_{role}'];actions[lo:f,role]=[*a['sticks'],*a['gyro'],*a['buttons']]
        for role in (0,1):
            key=f'player_{role}';i=row['infos'][key]
            if i['frame']-origins[key]!=f:raise ValueError('hosts not at common barrier')
            sample=i.get('position_sample_frame',-1)-origins[key]
            if not i.get('position_valid') or not 0<=sample<=f or available[sample,role]<=f:continue
            view=i.get('own_view',{});motion=i.get('referee_motion',{})
            def scalar(name):return i[name] if i.get(name+'_valid') else np.nan
            states[sample,role]=[*i['position'],scalar('heading'),view.get('yaw',np.nan) if view.get('valid') else np.nan,
                view.get('pitch',np.nan) if view.get('valid') else np.nan,scalar('hp'),scalar('ink'),
                motion.get('form_squid',np.nan),motion.get('ground_contact',np.nan),scalar('alive'),scalar('special')]
            available[sample,role]=f
    if not np.isfinite(actions).all():raise ValueError('missing controlled inputs')
    trace=object.__new__(Trace)
    trace.states,trace.actions,trace.available=states,actions,available
    trace.frames=end;trace.samples=[np.flatnonzero(np.isfinite(states[:,role,0])) for role in (0,1)]
    trace.labels=labels;trace.result=result
    trace.entry=dict(path=str(directory.relative_to(ROOT)),stage=result['case']['stage'],loadouts=result['loadouts'],
        source_sha256={n:sha256(directory/n) for n in ('result.json','steps.jsonl')})
    return trace


def export(trace,out):
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out,states=trace.states,actions=trace.actions,available=trace.available,labels=trace.labels)
    out.with_suffix('.json').write_text(json.dumps(dict(**trace.entry,fields=FIELDS,samples=[len(s) for s in trace.samples]),indent=2)+'\n')
