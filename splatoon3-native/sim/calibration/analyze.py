"""Packet-clock P0 summaries; raw curves and textures remain under work/."""
import argparse
import json
from pathlib import Path
import numpy as np

from sim.parameters import ROOT,Parameters,sha256
from sim.engine import Simulator
from sim.motion import MotionModel
from sim.opening import OpeningModel
from sim.paint_model import PaintModel
from sim.weapon import WeaponModel
from sim.terrain import Terrain
from sim.horizon import action_dict,reset_native
from sim.replay import stats
from .data import load


def release_intervals(trace):
    values=[]
    for role in (0,1):
        edges=np.flatnonzero(np.diff(trace.actions[:,role,7])<0)+1
        for edge in edges:
            held=0
            for value in trace.actions[:edge,role,7][::-1]:
                if not value:break
                held+=1
            if not str(trace.labels[edge-1]).startswith('measure'):continue
            ids=trace.samples[role];ids=ids[(ids>=edge-8)&(ids<=edge+40)]
            after=ids[(ids>=edge)&(trace.states[ids,role,9]==0)]
            if len(after):
                first=int(after[0]);past=ids[(ids<first)&(trace.states[ids,role,9]!=0)]
                values.append(dict(role=role,release=int(edge),hold=held,foot_onset_interval=[int(past[-1]+1-edge) if len(past) else None,first-edge]))
    return values


def motion_segments(trace):
    rows=[]
    for a,b in zip(trace.samples[0][:-1],trace.samples[0][1:]):
        if b-a>8 or a>=trace.frames:continue
        label=str(trace.labels[a]);p,q=trace.states[a,0],trace.states[b,0]
        if not label.startswith('measure-vector-') or not np.all(trace.labels[a:b]==label):continue
        rows.append(dict(label=label,start=int(a),end=int(b),sticks=trace.actions[a,0,:2].tolist(),
            yaw=float(p[4]),velocity=((q-p)[[0,2]]/(b-a)).tolist(),
            planar=bool(abs(q[1]-p[1])<.03 and p[9]in(0,4) and q[9]in(0,4) and not p[8] and not q[8])))
    return rows


def opening_comparison(base):
    reports=[]
    for stage,relative in ((1,'paint/p0-paint-map1-hold12-n1'),(2,'paint/p0-paint-map2-hold12-n1'),(3,'paint-retry/p0-yagara-hold12-n1')):
        trace=load(base/relative)
        for name in ('before','after'):
            env=Simulator(stage,parameters=Parameters.local(),terrain=Terrain.load(stage),
                motion_model=MotionModel.load(base/'models/motion.json' if name=='after' else ROOT/'work/sim/fidelity/motion.json'),
                opening_model=OpeningModel.load(base/'models/opening.json') if name=='after' else None)
            errors=[];early=[]
            for f in range(1,241):
                env.step(action_dict(trace.actions[f-1]),observe=False)
                for role in (0,1):
                    if not np.isfinite(trace.states[f,role,0]):continue
                    value=float(np.linalg.norm(env.players[role].position-trace.states[f,role,:3]));errors.append(value)
                    if f<=88:early.append(value)
            reports.append(dict(stage=stage,model=name,position=stats(errors),precontact=stats(early),
                scope='Fresh independent neutral trial; map1/2 trial ended at Judge due collector failure, first240-frame measurement intact. No fitted trajectory from these trials.',
                landing_error=[float(np.linalg.norm(env.players[r].position-trace.states[trace.samples[r][trace.samples[r]<=240][-1],r,:3])) for r in (0,1)]))
    return reports


def texture_summary(directory):
    from PIL import Image
    values=[]
    for path in sorted((directory/'textures').glob('*.png')):
        with Image.open(path) as im:
            if im.size!=(1600,1600):continue
            a=np.asarray(im.convert('RGB'))
        if np.max(a[:,:,2])!=0 or not (a[:,:,:2]>20).any():continue
        channels=[]
        for c in (0,1):
            y,x=np.where(a[:,:,c]>20)
            channels.append(dict(active_pixels=int(len(x)),bbox=[int(x.min()),int(y.min()),int(x.max()),int(y.max())] if len(x) else None,
                sum=int(a[:,:,c].sum()),std_xy=[float(x.std()),float(y.std())] if len(x) else None))
        values.append(dict(file=str(path.relative_to(ROOT)),sha256=sha256(path),channels=channels))
    return dict(threshold=20,targets=values,scope='Candidate UV paint targets, R/G not assigned to teams. No verified world mapping or scoring denominator; pixel counts are not world area.')


def paint_comparison(base,trace):
    starts=np.flatnonzero(np.char.startswith(trace.labels,'measure-paint-0-hold'))
    if not len(starts):return None
    anchor=int(starts[0]);end=int(np.flatnonzero(np.char.startswith(trace.labels,'measure-paint-tail'))[-1]+1)
    values=[]
    for name in ('before','after'):
        env=Simulator(trace.entry['stage'],parameters=Parameters.local(),terrain=Terrain.load(trace.entry['stage']),duration_frames=trace.frames,
            loadouts=trace.entry['loadouts'],motion_model=MotionModel.load(base/'models/motion.json'),
            weapon_model=WeaponModel.load(ROOT/'work/sim/fidelity/weapon.json'),
            paint_model=PaintModel.load(base/'models/paint.json') if name=='after' else None)
        reset_native(env,trace,anchor)
        for f in range(anchor,end):env.step(action_dict(trace.actions[f]),observe=False)
        values.append(dict(model=name,turf_pp=[100*v for v in env.paint.ratios()],special=[p.special for p in env.players],
            own_foot=[env.paint.at(p.position)==r for r,p in enumerate(env.players)],
            scope='Conditional on measured pre-shot pose/camera/HP/ink; dry pre-shot contact. Same grid denominator retained, no tuning to terminal winners.'))
    return values


def main(base):
    base=base.resolve();report=dict(schema='sim.native.p0.analysis.v1',opening=opening_comparison(base),paint=[],motion=[])
    for directory in sorted(base.glob('paint*/*')):
        if not (directory/'result.json').exists():continue
        result=json.loads((directory/'result.json').read_text())
        if 'paint_after' not in result:continue
        trace=load(directory)
        report['paint'].append(dict(path=str(directory.relative_to(ROOT)),passed=result['passed'],
            settings=result['case']['settings'],foot_onset=release_intervals(trace),
            score_peers=result.get('score_peers'),special=[r['special'] for r in result['paint_after'].values()],
            texture=texture_summary(directory),comparison=paint_comparison(base,trace)))
    for directory in sorted(base.glob('probes*/*')):
        if not (directory/'result.json').exists():continue
        result=json.loads((directory/'result.json').read_text())
        if result['case']['kind']=='p0_motion':
            trace=load(directory)
            report['motion'].append(dict(path=str(directory.relative_to(ROOT)),passed=result['passed'],case=result['case'],segments=motion_segments(trace)))
    (base/'analysis.json').write_text(json.dumps(report,indent=2,allow_nan=False,default=lambda v:v.item() if isinstance(v,np.generic) else str(v))+'\n')
    print(json.dumps(dict(opening=report['opening'],paint_trials=len(report['paint']),motion_trials=len(report['motion'])),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=ROOT/'work/sim/window-20261021');a=p.parse_args();main(a.directory)
