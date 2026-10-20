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
    directory=Path(directory).resolve()
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


def motion_comparison(base,trace):
    values=[]
    for name in ('before','after'):
        errors=[];pulses=[]
        for index in range(7):
            starts=np.flatnonzero(trace.labels==f'measure-vector-{index}-accelerate')
            if not len(starts):continue
            anchor=int(starts[0]);env=Simulator(1,terrain=Terrain.load(1),duration_frames=trace.frames,loadouts=trace.entry['loadouts'],
                motion_model=MotionModel.load(base/'models/motion.json' if name=='after' else ROOT/'work/sim/fidelity/motion.json'))
            reset_native(env,trace,anchor);pulse=[]
            for f in range(anchor,min(anchor+75,trace.frames)):
                env.step(action_dict(trace.actions[f]),observe=False);p=trace.states[f+1,0]
                if not np.isfinite(p[0]):continue
                error=float(np.linalg.norm(env.players[0].position-p[:3]));errors.append(error);pulse.append(error)
            pulses.append(dict(vector=index,position=stats(pulse)))
        values.append(dict(model=name,position=stats(errors),pulses=pulses,
            scope='Seven75-frame accelerator/brake windows, initialized causally at input onset. AP0 independent trial; AP19 transition-fit and AP57 gear-fit trials are calibration rechecks.'))
    return values


def combat_comparison(base,trace):
    results=[]
    for prefix in ('measure-light-timing','measure-full-timing','measure-second-full'):
        ids=np.flatnonzero(np.char.startswith(trace.labels,prefix))
        if not len(ids):continue
        anchor,end=int(ids[0]),int(ids[-1]+1)
        past=trace.past(anchor,1);previous=int(past[-1]);hp=float(trace.states[previous,1,6]);native=[]
        for f in trace.samples[1]:
            if not anchor<f<=end:continue
            value=float(trace.states[f,1,6])
            if hp-value>.01:native.append(dict(interval=[previous+1,int(f)],drop=hp-value))
            previous=int(f);hp=value
        comparisons=[]
        for name in ('legacy-no-delay','before','after'):
            weapon=WeaponModel.load(ROOT/'work/sim/fidelity/weapon.json')
            if name=='legacy-no-delay':weapon=WeaponModel({**weapon.data,'damage_delay':0})
            env=Simulator(1,terrain=Terrain.load(1),duration_frames=trace.frames,loadouts=trace.entry['loadouts'],
                motion_model=MotionModel.load(base/'models/motion.json' if name=='after' else ROOT/'work/sim/fidelity/motion.json'),
                weapon_model=weapon,paint_model=PaintModel.load(base/'models/paint.json') if name=='after' else None)
            reset_native(env,trace,anchor);ink=[];hp_error=[];position=[]
            for f in range(anchor,end):
                env.step(action_dict(trace.actions[f]),observe=False)
                for role,p in enumerate(env.players):
                    row=trace.states[f+1,role]
                    if not np.isfinite(row[0]):continue
                    position.append(float(np.linalg.norm(p.position-row[:3])))
                    if role==0:ink.append(abs(p.ink-row[7]))
                    else:hp_error.append(abs(p.hp-row[6]))
            events=[e for e in env.events if e['kind']=='damage' and e['target']==1 and e['cause']in('ink_blade','contact')]
            frame=events[0]['frame'] if events else None
            interval=native[0]['interval'] if native else None
            comparisons.append(dict(model=name,damage=events,position=stats(position),ink=stats(ink),hp=stats(hp_error),
                first_interval_violation=max(interval[0]-frame,0,frame-interval[1]) if interval and frame is not None else None,
                first_minus_native_latest=frame-interval[1] if interval and frame is not None else None))
        results.append(dict(case=prefix,anchor=anchor,end=end,native_damage=native,comparisons=comparisons,
            scope='New room, causal pre-trial reset, actual native input. Full trial starts after light damage; native loss is clipped at remaining HP, not nominal full damage.'))
    return results


def scan_comparison(base,trace):
    anchor=int(np.flatnonzero(trace.labels=='measure-isolated-hold')[0]);values=[]
    for name in ('before','after'):
        env=Simulator(1,terrain=Terrain.load(1),duration_frames=trace.frames,loadouts=trace.entry['loadouts'],
            motion_model=MotionModel.load(base/'models/motion.json'),weapon_model=WeaponModel.load(ROOT/'work/sim/fidelity/weapon.json'),
            paint_model=PaintModel.load(base/'models/paint.json') if name=='after' else None)
        reset_native(env,trace,anchor)
        for f in range(anchor,anchor+120):env.step(action_dict(trace.actions[f]),observe=False)
        samples={}
        for f in trace.samples[0]:
            if f>=trace.frames:continue
            p=trace.states[f,0];label=str(trace.labels[f])
            if not label.startswith('measure-scan-row-') or '-start' in label or p[9]not in(0,4) or abs(p[1]-3.)>.1:continue
            cell=env.terrain.cell_at(p[:3])
            if cell is not None:samples.setdefault(cell,(p[:3],int(p[9]==0),label))
        groups=[]
        for scope in ('all','train_rows','heldout_rows'):
            rows=[(own,int(env.paint.at(p)==0)) for p,own,label in samples.values() if scope=='all' or
                (('row-9.5' in label or 'row-11.0' in label)==(scope=='heldout_rows'))]
            tp=sum(a and b for a,b in rows);fp=sum(not a and b for a,b in rows);fn=sum(a and not b for a,b in rows)
            groups.append(dict(scope=scope,points=len(rows),positive_points=int(sum(a for a,b in rows)),tp=int(tp),fp=int(fp),fn=int(fn),f1=float(2*tp/max(1,2*tp+fp+fn))))
        values.append(dict(model=name,groups=groups))
    return values


def main(base):
    base=base.resolve();report=dict(schema='sim.native.p0.analysis.v1',opening=opening_comparison(base),paint=[],motion=[],combat=[],scans=[])
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
            report['motion'].append(dict(path=str(directory.relative_to(ROOT)),passed=result['passed'],case=result['case'],segments=motion_segments(trace),comparison=motion_comparison(base,trace)))
    for directory in sorted([*base.glob('bends-combat/*'),*base.glob('validation/*')]):
        if not (directory/'result.json').exists():continue
        result=json.loads((directory/'result.json').read_text())
        if result['case']['kind']=='p0_combat' and result.get('passed'):
            report['combat'].append(dict(path=str(directory.relative_to(ROOT)),cases=combat_comparison(base,load(directory)),respawn_status=result.get('respawn_status')))
    for directory in sorted([*base.glob('probes*/*'),*base.glob('validation/*')]):
        if not (directory/'result.json').exists():continue
        result=json.loads((directory/'result.json').read_text())
        if result['case']['kind']=='p0_scan' and result.get('passed'):
            report['scans'].append(dict(path=str(directory.relative_to(ROOT)),hold=result['case']['settings']['hold'],
                independent_repeat=directory.parent.name=='validation',comparison=scan_comparison(base,load(directory))))
    (base/'analysis.json').write_text(json.dumps(report,indent=2,allow_nan=False,default=lambda v:v.item() if isinstance(v,np.generic) else str(v))+'\n')
    print(json.dumps(dict(opening=report['opening'],paint_trials=len(report['paint']),motion_trials=len(report['motion'])),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=ROOT/'work/sim/window-20261021');a=p.parse_args();main(a.directory)
