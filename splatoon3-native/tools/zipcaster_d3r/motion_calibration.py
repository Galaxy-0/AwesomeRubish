"""Training-only own-motion identification, never fit from enemy outcome/HP.

Only trial0/1,40f full-light, source alpha free of large incoming impulse.
Each measured wall/source gets a conditional trajectory template. This is not
cross-hook physics generalization. Trial2 is evaluation only, never selected.
"""
import argparse,json,sys,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'tools/zipcaster_d3'),str(ROOT)]
from tools.zipcaster_d3r.analyze_direction import sha
from tools.zipcaster_d3r.ideal_search_v2 import trajectory as base_trajectory

def own_profile(d,steps):
    if d['trial']>=2:raise ValueError('held-out trial cannot fit motion')
    if d['speed_frames']!=40 or d['combo']!='full-light':return None
    events={e['event']:e['infos']['player_0']for e in d['events']}
    if 'arrival'not in events:return None
    start=events['before-R']['frame'];arrival=events['arrival']['frame'];samples={};last_hp=events['before-R']['hp'];impulse=None
    for row in steps:
        own=row['infos']['player_0'];f=own['frame']
        if f<=start:continue
        if last_hp-own['hp']>=.18 or not own['alive']:impulse=f;break
        last_hp=own['hp']
        if f>=arrival:samples[f-arrival]=own['position']
    if not samples or max(samples)<100:return None
    ground=next((r['infos']['player_0'].get('referee_motion',{}).get('ground_contact')for r in steps if r['infos']['player_0']['frame']>=arrival+100),None)
    # No assumption that a high-wall actor has landed by100f. Motion may still
    # be used if it is stable for the final16f even when the field is unavailable.
    times=sorted(samples);poses=np.array([samples[t]for t in times]);post=np.column_stack([np.interp(np.arange(101),times,poses[:,i])for i in range(3)])
    if np.ptp(post[-16:,1])>.15:return None
    return dict(arrival_frames=arrival-start,post=post,ground_contact_at100=ground,impulse_frame=impulse)

def fit(a):
    if a.out.exists():raise ValueError('fresh motion fit')
    rows=[]
    for batch in a.batch:
        for r in json.loads(batch.read_text())['results']:
            if not r['eligible']or r['trial']>=2:continue
            p=ROOT/r['artifact'];d=json.loads(p.read_text());steps=[json.loads(l)for l in p.with_name('steps.jsonl').open()];profile=own_profile(d,steps)
            if profile:rows.append((d['point']['id'],d['point']['map'],d['trial'],p,profile))
    points={}
    for ident in sorted({r[0]for r in rows}):
        rr=[r for r in rows if r[0]==ident];stack=np.stack([r[4]['post']for r in rr]);mean=stack.mean(axis=0);points[ident]=dict(id=ident,map=rr[0][1],training_trials=[r[2]for r in rr],arrival_frames=int(round(np.mean([r[4]['arrival_frames']for r in rr]))),post_positions=mean.tolist(),training_position_rmse=float(np.sqrt(np.mean((stack-mean)**2))),sources=[dict(path=str(r[3].relative_to(ROOT)),sha256=sha(r[3]))for r in rr])
    out=dict(schema='inklab.d3r.motion.fit.v1',points=points,source_sha256=sha(__file__),fit_keys=[[r[0],r[2]]for r in rows],uses_enemy_state_or_outcome=False,scope='Existing measured singles,40f full-light only. Trial0/1 own movement, no >=18HP impulse before100f, stable terminal height. Other programs/links remain kinematic extrapolation.');a.out.write_text(json.dumps(out,indent=2)+'\n');print('MOTION_FIT '+str(len(points))+' points '+str(len(rows))+' free training trials')

def trajectory(point,speed,style,profiles):
    profile=profiles.get(point['id'])if speed==40 and style=='full-light'and len(point.get('sequence',[point['id']]))==1 else None
    if profile is None:return base_trajectory(point,speed,style)
    path,start,budget=base_trajectory(point,speed,style)
    if path is None:return path,start,budget
    first=np.array(point['native_flight']);old_t=np.arange(len(first));new_t=np.linspace(0,len(first)-1,profile['arrival_frames']+1);prefix=np.column_stack([np.interp(new_t,old_t,first[:,i])for i in range(3)]);post=np.array(profile['post_positions']);prefix+=np.linspace(0,1,len(prefix))[:,None]*(post[0]-prefix[-1]);tail=np.concatenate([post[1:],np.repeat(post[-1][None,:],speed+99-len(post)+1,axis=0)]);path=np.concatenate([prefix,tail]);arrival=len(prefix)-1;start=arrival+speed-21
    from budget import Gauge
    cost=Gauge().cost(arrival+speed+45,hooks=1,lights=1,fulls=1)
    if cost>=.96:return None,None,None
    budget=dict(budget,spent=cost,motion_calibrated=True,training_trials=profile['training_trials'],events=[dict(frame=0,event='出钩'),dict(frame=arrival,event='到达 / B跳离'),dict(frame=start,event='开始蓄力'),dict(frame=arrival+speed,event='满蓄释放'),dict(frame=arrival+speed+36,event='轻斩输入')]);return path,start,budget
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,nargs='+',default=[ROOT/'work/d3r/calibration-v2/batch.json']);p.add_argument('--out',type=Path,required=True);fit(p.parse_args())
