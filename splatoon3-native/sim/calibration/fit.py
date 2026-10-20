"""Fit native P0 coefficients; output only to ignored work/, never raw assets."""
import argparse
import copy
import json
from pathlib import Path
import numpy as np

from .data import load
from sim.parameters import ROOT


def fit_transitions(directory):
    from .analyze import motion_segments
    from sim.identify import response
    directory=Path(directory).resolve();trace=load(directory/'probes/p0_motion-ap19')
    if not trace.result.get('passed'):raise ValueError('incomplete transition probe')
    rows=motion_segments(trace)
    full=[np.linalg.norm(r['velocity']) for r in rows if r['planar'] and r['sticks']==[0.,1.] and r['label'].endswith('accelerate')]
    speed=float(np.percentile(full,85))
    candidates=np.array([(a,b) for a in np.arange(.004,.0301,.001) for b in np.arange(.002,.0201,.001)])
    loss=np.zeros(len(candidates));count=0
    for index in range(7):
        label=f'measure-vector-{index}-accelerate';ids=np.flatnonzero(trace.labels==label)
        if not len(ids):continue
        start=int(ids[0]);past=trace.samples[0][trace.available[trace.samples[0],0]<=start]
        if len(past)<2:continue
        before,latest=past[-2:];row=trace.states[latest,0]
        initial=(row-trace.states[before,0])[[0,2]]/(latest-before)
        position=np.broadcast_to(row[[0,2]]+initial*(start-latest),(len(candidates),2)).copy()
        velocity=np.broadcast_to(initial,position.shape).copy()
        for f in range(start,min(start+75,trace.frames)):
            sticks=trace.actions[f,0,:2];x,z=response(sticks,0.,4.,'radial');yaw=row[4]
            target=np.array([-x*np.cos(yaw)+z*np.sin(yaw),x*np.sin(yaw)+z*np.cos(yaw)])*speed
            rate=np.where(np.linalg.norm(target)<np.linalg.norm(velocity,axis=1),candidates[:,1],candidates[:,0])
            velocity+=np.clip(target-velocity,-rate[:,None],rate[:,None]);position+=velocity
            native=trace.states[f+1,0]
            if not np.isfinite(native[0]) or native[9]not in(0,4) or abs(native[1]-3.)>.05:continue
            loss+=np.sum((position-native[[0,2]])**2,axis=1);count+=1
    best=int(np.argmin(loss));a,b=candidates[best]
    path=directory/'models/motion.json';model=json.loads(path.read_text())
    model['modes']['human'].update(acceleration=float(a),braking=float(b),transition_segments=count,
        status='P0 native AP0 radial quartic steady response; AP19 independent motion probe identifies transition coefficients')
    model['native_calibration']['transition_fit']=dict(source=trace.entry,acceleration=float(a),braking=float(b),position_rmse=float(np.sqrt(loss[best]/count)),samples=count,ap19_speed=speed,
        note='AP19 speed measured from same probe to remove gear confounding; transition fit is calibration, validate on AP0/AP57 and historical short horizons.')
    path.write_text(json.dumps(model,indent=2)+'\n');print(json.dumps(model['native_calibration']['transition_fit'],indent=2))


def fit_gear(directory):
    from .analyze import motion_segments
    directory=Path(directory).resolve();rows=[]
    for ap,relative in ((0,'probes2/p0-motion-ap0'),(19,'probes/p0_motion-ap19'),(57,'probes2/p0-motion-ap57')):
        trace=load(directory/relative)
        if not trace.result.get('passed'):raise ValueError('incomplete AP sweep')
        segments=motion_segments(trace)
        full=[np.linalg.norm(r['velocity']) for r in segments if r['planar'] and r['sticks']==[0.,1.] and r['label'].endswith('accelerate')]
        if len(full)<5:raise ValueError('insufficient stable maximum speed samples')
        speed=float(np.percentile(full,85));rows.append(dict(ap=ap,speed=speed,samples=len(full),source=trace.entry))
    path=directory/'models/motion.json';model=json.loads(path.read_text());base=rows[0]['speed']
    model['run_speed_up_curve']=[[r['ap'],r['speed']/base] for r in rows]
    model['native_calibration']['run_gear']=dict(anchors=rows,
        scope='Only ordinary human movement. AP3/10/38 piecewise interpolation unvalidated; charge/recovery/swim/resistance unchanged.')
    path.write_text(json.dumps(model,indent=2)+'\n');print(json.dumps(dict(curve=model['run_speed_up_curve'],anchors=rows),indent=2))


def fit_air(directory):
    """Map1/2 free airborne episodes fit; map3 and other roles held out."""
    from sim.identify import response
    directory=Path(directory).resolve();episodes=[]
    for stage in (1,2):
        trace=load(directory/f'bends-combat/p0-bends-map{stage}');ids=trace.samples[0]
        ids=ids[(ids>240)&(trace.states[ids,0,9]==5)&(trace.states[ids,0,8]==0)]
        for run in np.split(ids,np.flatnonzero(np.diff(ids)>8)+1):
            if len(run)<5:continue
            episodes.append((trace,run))
    if not episodes:raise ValueError('no independent airborne excitation')
    candidates=np.array([(s,a,b) for s in np.arange(.06,.1041,.002) for a in (.0005,.001,.002,.003,.005,.008) for b in (.0005,.001,.002,.003,.005,.008)])
    loss=np.zeros(len(candidates));count=0
    for trace,run in episodes:
        a,anchor=run[:2];row=trace.states[anchor,0];initial=(row-trace.states[a,0])[[0,2]]/(anchor-a)
        position=np.broadcast_to(row[[0,2]],(len(candidates),2)).copy();velocity=np.broadcast_to(initial,position.shape).copy()
        samples=set(run[2:])
        for f in range(anchor,int(run[-1])):
            x,z=response(trace.actions[f,0,:2],0.,4.,'radial');yaw=row[4]
            target=np.array([-x*np.cos(yaw)+z*np.sin(yaw),x*np.sin(yaw)+z*np.cos(yaw)])[None,:]*candidates[:,0,None]
            rate=np.where(np.linalg.norm(target,axis=1)<np.linalg.norm(velocity,axis=1),candidates[:,2],candidates[:,1])
            velocity+=np.clip(target-velocity,-rate[:,None],rate[:,None]);position+=velocity
            if f+1 not in samples:continue
            loss+=np.sum((position-trace.states[f+1,0,[0,2]])**2,axis=1);count+=1
    best=int(np.argmin(loss));speed,acceleration,braking=candidates[best]
    import shutil
    out=directory/'models-v2';out.mkdir(exist_ok=True)
    for path in (directory/'models').glob('*.json'):shutil.copy2(path,out/path.name)
    model=json.loads((out/'motion.json').read_text());model['modes']['air'].update(speed=float(speed),exponent=4.,deadzone=0.,response_space='radial',acceleration=float(acceleration),braking=float(braking),
        status='P0 free-air episodes map1/2 role0; radial quartic, no collision/support labels fitted')
    model['native_calibration']['air_fit']=dict(training='P0 bends map1/2 role0 airborne episodes after frame240; first2 packets initialize velocity, predict rest',
        validation='Map3 and all role1 episodes held out; complete collision/support assessed separately',episodes=len(episodes),samples=count,position_rmse=float(np.sqrt(loss[best]/count)),
        coefficients=dict(speed=float(speed),acceleration=float(acceleration),braking=float(braking)))
    (out/'motion.json').write_text(json.dumps(model,indent=2)+'\n');print(json.dumps(model['native_calibration']['air_fit'],indent=2))


def fit_paint(directory,full=False,core_only=False):
    from sim.engine import Simulator
    from sim.parameters import Parameters
    from sim.terrain import Terrain
    from sim.motion import MotionModel
    from sim.weapon import WeaponModel
    from sim.paint_model import PaintModel
    from sim.horizon import reset_native,action_dict
    directory=Path(directory).resolve();source=directory/('probes2/p0-scan-full-ap0' if full else 'probes/p0_scan-ap0')
    trace=load(source)
    if not trace.result.get('passed'):raise ValueError('incomplete scan cannot supply accepted fit')
    if not trace.result.get('own_submergence_control',{}).get('submerged'):
        raise ValueError('own-ink control not confirmed')
    starts=np.flatnonzero(trace.labels=='measure-isolated-hold');anchor=int(starts[0])
    env=Simulator(1,parameters=Parameters.local(),terrain=Terrain.load(1),duration_frames=trace.frames,
        motion_model=MotionModel.load(directory/'models/motion.json'),weapon_model=WeaponModel.load(ROOT/'work/sim/fidelity/weapon.json'),
        paint_model=PaintModel(dict(schema='sim.paint.v1',weak_radius=0.,full_radius=0.,weak_delay=14,full_delay=11,field_collision_core_only=core_only)))
    reset_native(env,trace,anchor);pose=env.players[0].position.copy()
    for f in range(anchor,anchor+102):env.step(action_dict(trace.actions[f]),observe=False)
    owners=env.paint.owners.copy();samples={}
    for f in trace.samples[0]:
        if f>=trace.frames:continue
        label=str(trace.labels[f]);p=trace.states[f,0]
        if not label.startswith('measure-scan-row-') or '-start' in label or p[9]not in(0,4) or abs(p[1]-3.)>.1:continue
        cell=env.terrain.cell_at(p[:3])
        if cell is None:continue
        # One measured sample per world cell; repeated dwell does not inflate
        # apparent accuracy. Labels describe actual XYZ, not requested rows.
        samples.setdefault(cell,(p[:3].copy(),int(p[9]==0),label))
    def score(radius,validation):
        env.paint.owners[:]=owners
        if radius:env.paint.disk(pose,radius,0)
        truth=[];prediction=[]
        for cell,(p,own,label) in samples.items():
            held=('row-9.5' in label or 'row-11.0' in label)
            if held!=validation:continue
            truth.append(own);prediction.append(int(env.paint.at(p)==0))
        truth=np.array(truth);prediction=np.array(prediction)
        tp=int(((truth==1)&(prediction==1)).sum());fp=int(((truth==0)&(prediction==1)).sum());fn=int(((truth==1)&(prediction==0)).sum())
        return dict(cells=len(truth),positive_cells=int(truth.sum()),tp=tp,fp=fp,fn=fn,f1=2*tp/max(1,2*tp+fp+fn),accuracy=float(np.mean(truth==prediction)) if len(truth) else None)
    grid=[dict(radius=float(r),train=score(float(r),False),validation=score(float(r),True)) for r in np.linspace(0,3.5,36)]
    eligible=[r for r in grid if r['train']['positive_cells']>=3 and r['train']['cells']>=20]
    if not eligible:raise ValueError('scan has insufficient independent world cells')
    best=max(eligible,key=lambda r:(r['train']['f1'],-r['radius']))
    model=dict(schema='sim.paint.v1',weak_radius=best['radius'],full_radius=0.,weak_delay=14,full_delay=11,
        field_collision_core_only=core_only,
        interpretation='Foot radius fit to unique sampled cells on first3 requested rows; last2 rows held out. Effective contact onset delay includes sampling/material latency.',
        source=trace.entry,grid_search=grid,selected=best,
        limitations=['Not a full world paint mask/area IoU','unknown UV mapping/scoring denominator','moving foot-splash origin unvalidated','spatial holdout within each shot, no independent repeated shot fit'])
    if full:
        model=json.loads((directory/'models/paint.json').read_text())
        model.update(full_radius=best['radius'],full_source=trace.entry,full_grid_search=grid,full_selected=best,field_collision_core_only=core_only)
    (directory/'models/paint.json').write_text(json.dumps(model,indent=2)+'\n')
    print(json.dumps(dict(selected=best,baseline=grid[0]),indent=2))


def human_rows(trace,role):
    rows=[];ids=trace.samples[role]
    for a,b in zip(ids[:-1],ids[1:]):
        if b-a>8 or a>=trace.frames:continue
        label=trace.labels[a]
        if not label.startswith('measure-straight-') or not np.all(trace.labels[a:b]==label):continue
        p,q=trace.states[a,role],trace.states[b,role]
        if p[9]not in(0,4) or q[9]not in(0,4) or p[8] or q[8] or abs(q[1]-p[1])>.04:continue
        v=float(np.linalg.norm((q-p)[[0,2]])/(b-a))
        if v<.001:continue
        rows.append((float(label.split('-')[-1]),v,int(a)))
    return rows


def fit(directory):
    directory=Path(directory).resolve();traces={s:load(directory/'opening'/f'p0-opening-map{s}') for s in (1,2,3)}
    model=json.loads((ROOT/'work/sim/fidelity/motion.json').read_text());motion=copy.deepcopy(model)
    train=[];validation=[]
    for stage,t in traces.items():
        for role in (0,1):
            (train if stage in(1,2) and role==0 else validation).extend(human_rows(t,role))
    bins=[]
    for magnitude in (.5,.85,1.):
        v=[v for m,v,f in train if m==magnitude]
        if len(v)<2:raise ValueError('insufficient free native human excitation')
        bins.append((magnitude,float(np.percentile(v,85))))
    best=None
    for exponent in np.linspace(1.,5.,81):
        x=np.array([m**exponent for m,v in bins]);y=np.array([v for m,v in bins]);speed=float(x@y/(x@x))
        loss=float(np.mean((x*speed-y)**2))
        if best is None or loss<best[0]:best=(loss,speed,float(exponent))
    human=motion['modes']['human'];human.update(speed=best[1],exponent=best[2],deadzone=0.,
        response_space='radial',acceleration=.01,braking=.008,
        stable_segments=len(train),stick_bins=3,envelope_loss=best[0],transition_segments=0,
        status='P0 AP0 native radial quartic steady response; .01/.008 transition candidate from start/stop pulses')
    def error(rows,p):return float(np.sqrt(np.mean([(v-p['speed']*m**p['exponent'])**2 for m,v,f in rows])))
    motion['native_calibration']=dict(training='map1/2 role0 stable nonzero planar intervals,85th percentile per magnitude',
        validation='map3 both roles plus map1/2 role1; same opening experiment, not independent trial',
        bins=bins,training_segments=len(train),validation_segments=len(validation),
        steady_speed_rmse_before=error(validation,model['modes']['human']),steady_speed_rmse_after=error(validation,human),
        sources=[t.entry for t in traces.values()],unidentified=['human ink-color differences','run AP curve','flight lateral/other amplitudes'])
    opening=dict(schema='sim.opening.v1',steer_start=14,steer_speed=0.,stages={},sources=[t.entry for t in traces.values()],
        note='Role0 neutral launch and residual launch impulse fit through frame140; phase/form boundaries packet-resolved. Includes initial contact under launch drive, not general terrain locomotion. Steering fit at .85 forward on maps1/2 before contact, map3 held out. No respawn fit.')
    estimates=[]
    for stage,t in traces.items():
        ids=t.samples[0];valid=ids[(ids<=140)]
        if valid[0]>0:valid=np.r_[0,valid]
        knots=[]
        for f in valid:
            row=t.states[f,0]
            if not np.isfinite(row[0]):row=t.states[t.samples[0][0],0]
            knots.append([int(f),*row[:3].tolist()])
        last=knots[-1][0]
        form=ids[(t.states[ids,0,8]==1)&(ids<88)]
        ground=ids[(np.isin(t.states[ids,0,9],(0,4)))&(ids>60)]
        opening['stages'][str(stage)]=dict(end_frame=last,knots=knots,squid_start=int(form[0]),squid_end=int(form[-1]+4),ground_frame=int(ground[0]))
        if stage not in(1,2):continue
        k=np.array(knots)
        for f in t.samples[1]:
            if not 32<=f<=min(84,last):continue
            base=-np.interp(f,k[:,0],k[:,3]);delta=t.states[f,1,2]-base
            estimates.append(float(delta/((f-14)*(.85**4))))
    opening['steer_speed']=float(np.median(estimates))
    out=directory/'models';out.mkdir(exist_ok=True)
    (out/'motion.json').write_text(json.dumps(motion,indent=2)+'\n')
    (out/'opening.json').write_text(json.dumps(opening,indent=2)+'\n')
    print(json.dumps(dict(human=human,validation=motion['native_calibration'],opening_steer_speed=opening['steer_speed']),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=ROOT/'work/sim/window-20261021');p.add_argument('--paint',action='store_true');p.add_argument('--full-paint',action='store_true');p.add_argument('--core-field',action='store_true');p.add_argument('--transitions',action='store_true');p.add_argument('--gear',action='store_true');p.add_argument('--air',action='store_true');a=p.parse_args()
    fit_paint(a.directory,a.full_paint,a.core_field) if a.paint or a.full_paint else fit_transitions(a.directory) if a.transitions else fit_gear(a.directory) if a.gear else fit_air(a.directory) if a.air else fit(a.directory)
