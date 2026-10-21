"""Convert existing native and simulated recordings into inklab.trace.v1."""
import json
import math
from pathlib import Path
import numpy as np

COLUMNS=['frame','sample_frame','x','y','z','heading','form','hp','alive','ink']


def edges(actions, start, end):
    result=[]
    held=None
    previous=[0]*6
    for frame, buttons in actions:
        for index,name in [(0,'ZR'),(2,'R'),(3,'RS'),(4,'B')]:
            if buttons[index] and not previous[index]:
                if index==0:held=frame
                if start<=frame<=end:
                    result.append(dict(frame=frame,type=name+'_down',evidence='recorded_input_edge'))
            if index==0 and not buttons[0] and previous[0]:
                duration=frame-held if held is not None else None
                if start<=frame<=end:
                    result.append(dict(frame=frame,type='ZR_release',hold_frames=duration,evidence='recorded_input_edge'))
                held=None
        previous=list(buttons)
    return result


def clean(value, digits=3):
    return round(float(value),digits) if value is not None and math.isfinite(float(value)) else None


def native_rows(path):
    rows=[]
    with path.open() as file:
        for line in file:
            row=json.loads(line)
            obs=row['observation'];own=obs['own']
            rows.append((obs['frame'],own,row['action']['buttons']))
    return rows


def compile_traces(root, source):
    clips=[]
    for n,swap in [(1,True),(2,False)]:
        path=root/f'work/arena/t1/round-{n:03d}/game-0-attempt-000'
        result=json.loads(source(path/'result.json').read_text())
        streams=[native_rows(source(path/f'policy-{i}.jsonl')) for i in range(2)]
        by_frame=[{f:o for f,o,_ in rows if o['position'] is not None} for rows in streams]
        near=[]
        for f in sorted(set(by_frame[0])&set(by_frame[1]))[::60]:
            a,b=by_frame[0][f],by_frame[1][f]
            if f>=900 and a['public']['alive'] and b['public']['alive']:
                near.append((math.dist(a['position'],b['position']),f))
        closest=min(near)[1]
        start=max(600,min(9000,closest-600));end=start+1800
        players=[]
        for role,rows in enumerate(streams):
            states=[]
            for f,o,_ in rows:
                if not start<=f<=end or (f-start)%6 or o['position'] is None:
                    continue
                form=('submerged' if o['submerged'] else 'squid') if o['form_squid'] else 'human'
                if o['form_squid'] is None:form=None
                states.append([f,o['sample_frame'],*[clean(v,2) for v in o['position']],clean(o['heading'],4),
                               form,clean(o['hp']),o['public']['alive'],clean(o['ink'])])
            policy=result['role_to_policy'][role]
            players.append(dict(id='alpha' if policy==0 else 'bravo',role=f'player_{role}',
                                states=states,events=edges([(f,b)for f,_,b in rows],start,end)))
        native=dict(schema='inklab.trace.v1',id=f'native-r{n}',label=f'原生 T1 · R{n} 温泉峡谷',
                    source_kind='native_observation',map='Yunohana',fps=60,start_frame=start,end_frame=end,
                    stride=6,columns=COLUMNS,selection='30s around closest recorded living pair; presentation selection only',
                    players=players,position_semantics='past own-player observations, quantized .01u; sample_frame retained; no hidden enemy inferred')
        clips.append(native)
        simdir=root/f'work/sim/window-20261021/route-check/R{n}-map1-side{int(swap)}'
        archive=source(simdir/'trace-0.npz')
        source(simdir/'result.json');source(simdir/'routes.json')
        with np.load(archive,allow_pickle=False) as recording:
            states=recording['states'];actions=recording['actions']
            players=[]
            for role,who in enumerate(('alpha','bravo')):
                samples=[]
                for f in range(start,end+1,6):
                    o=states[f,role]
                    if not np.isfinite(o[:3]).all():continue
                    form='squid' if o[8] else 'human'
                    # Recorder contact0 means own ink only when actually grounded.
                    if o[8] and o[9]==0:form='submerged'
                    samples.append([f,f,*[clean(v,2)for v in o[:3]],clean(o[3],4),form,
                                    clean(o[6]),bool(o[10]),clean(o[7])])
                players.append(dict(id=who,role=f'sim_player_{role}',states=samples,
                    events=edges([(f,list(a[role,7:13])) for f,a in enumerate(actions,1)],start,end)))
        clips.append(dict(schema='inklab.trace.v1',id=f'sim-r{n}',label=f'S1 模拟 · R{n} 同时段',
            source_kind='simulated_state',map='Yunohana',fps=60,start_frame=start,end_frame=end,stride=6,
            columns=COLUMNS,selection='same frame interval as native clip; no trajectory alignment or injected state',
            players=players,position_semantics='recorded model state, not native truth; route-check digest verified against frozen ranks-final'))
    return clips
