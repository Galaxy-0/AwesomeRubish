"""Offline route diagnosis, with an explicitly conditional opening intervention.

ground: the original ranking start. prefix: replay ONLY the first 120 frames of
historical policy observations to restore policy memory, then reset observable
sim state once. No native state is injected after that boundary. Prefix results
are causal ablations, not validation of a predictive launch/respawn model.
All poses, actions and event details are private artifacts under work/.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import time
import traceback

import numpy as np

from arena.config import PolicySpec
from arena.control_process import ControlProcess, OwnSpecial
from arena.policy import PublicPlayer, OwnState, EnemyView, PolicyObservation
from arena.visibility import PolicyProjector
from .corpus import Trace, normalize
from .engine import neutral
from .batch import VectorBatchSimulator
from .horizon import reset_native
from .parameters import ROOT, Parameters, sha256
from .ranking import Models, core_hashes, perturb
from .ranking_sources import PAIRS, WORK
from .terrain import Terrain

OUT = ROOT/'work/sim/diagnosis'
BOUNDARY = 120
FIELDS = ('x','y','z','heading','yaw','pitch','hp','ink','squid','contact','alive','special')


def typed_record(obs, mapping, match_id):
    """Rebuild the same allowlist; never send a raw recording/referee dict."""
    def public(p):
        role = int(p['player_id'].split('_')[-1])
        return PublicPlayer(f'player_{mapping[role]}', mapping[role], p['weapon'], p['alive'])
    def point(p):return tuple(p) if p is not None else None
    own = obs['own']
    return PolicyObservation(match_id, obs['frame'], OwnState(public(own['public']),
        point(own['position']), own['heading'], own['hp'], own['ink'], own['sample_frame'],
        own.get('form_squid'), own.get('submerged'), own.get('view_yaw'), own.get('view_pitch')),
        tuple(EnemyView(public(e['public']),e['visible'],point(e['position']),e['heading'],
                       e['sample_frame'],point(e['last_seen_position']),e['last_seen_frame']) for e in obs['enemies']),
        obs['remaining_seconds'],obs['stage_id'])


def native_trace(match):
    directory = ROOT/match['source']
    entry = normalize(dict(path=str(directory.relative_to(ROOT)),stage=match['stage'],split='diagnosis'), OUT/'native')
    trace = Trace(entry)
    order = [match['role_to_policy'].index(i) for i in range(2)]
    trace.states = trace.states[:,order].copy()
    trace.actions = trace.actions[:,order].copy()
    trace.available = trace.available[:,order].copy()
    trace.samples = [np.flatnonzero(np.isfinite(trace.states[:,i,0])) for i in range(2)]
    return trace


def route_summary(states, actions, stage, visibility=None):
    """Dwell uses left sample holds only across <=16-frame gaps; no long fills.

    ZR time/releases are paint INPUT opportunities, never native painted area.
    HP loss intervals are candidate fights, not last-hit attribution.
    """
    from arena.lib.atlas import MapAtlas
    atlas = MapAtlas.load(stage)
    high = np.array(atlas.region('central_high'))
    result = []
    for role in range(2):
        ids = np.flatnonzero(np.isfinite(states[:,role,0]))
        s = states[ids,role]
        if not len(ids):raise ValueError('empty route')
        horizontal = np.linalg.norm(s[:,[0,2]]-high[[0,2]],axis=1)
        on = (horizontal < 2.) & (abs(s[:,1]-high[1]) < .3) & (s[:,10]==1)
        arrived = (np.linalg.norm(s[:,:3]-high,axis=1)<.7) & (abs(s[:,1]-high[1])<.3)
        gaps = np.diff(ids,append=ids[-1]); covered = gaps<=16
        weights = np.where(covered,gaps,0)
        zr = actions[:,role,7]
        release = np.flatnonzero(np.diff(zr,prepend=0)<0)
        high_input = sum(int(np.count_nonzero(zr[f:min(f+w,len(zr))])) for f,w,keep in zip(ids,weights,on) if keep)
        losses = []
        for j in np.flatnonzero(np.diff(s[:,6])<-.01):
            losses.append(dict(interval=[int(ids[j]+1),int(ids[j+1])],
                               position=s[j+1,:3].tolist(),hp_loss=float(s[j,6]-s[j+1,6])))
        grounded = np.isin(s[:,9],(0,4)) & (s[:,1]<20)
        result.append(dict(first_frame=int(ids[0]),first_position=s[0,:3].tolist(),
            last_position=s[-1,:3].tolist(),xyz_range=np.ptp(s[:,:3],axis=0).tolist(),
            ground_first_frame=int(ids[grounded][0]) if grounded.any() else None,
            high_first_frame=int(ids[on][0]) if on.any() else None,
            exact_arrival_first_frame=int(ids[arrived][0]) if arrived.any() else None,
            high_dwell_sample_hold_frames=int(weights[on].sum()),high_ZR_sample_hold_frames=high_input,
            high_min_horizontal=float(horizontal.min()),
            observed_path_length=float(np.linalg.norm(np.diff(s[:,:3],axis=0),axis=1)[covered[:-1]].sum()),
            ink_min=float(np.nanmin(s[:,7])),ink_end=float(s[-1,7]),hp_losses=losses,
            release_inputs=int(len(release)),move_input_frames=int(np.count_nonzero(np.linalg.norm(actions[:,role,:2],axis=1)>.1)),
            visible_frames=int(np.count_nonzero(visibility[:,role])) if visibility is not None else None,
            first_visible_frame=int(np.flatnonzero(visibility[:,role])[0]) if visibility is not None and visibility[:,role].any() else None,
            high_definition='XZ radius <2, abs height error <.3, alive; exact arrival uses public Skills .7/.3',
            native_paint_area_or_painting_duration_measured=False))
    return result


def records(match):
    directory = ROOT/match['source']
    logs = []
    for i in range(2):
        role = match['role_to_policy'].index(i)
        logs.append([json.loads(line) for line in (directory/f'policy-{role}.jsonl').open()])
    return logs


def inventory():
    sources=json.loads((WORK/'sources.json').read_text())
    results=[]
    for pair in ('A5','R1','R2'):
        for match in sources['references'][pair]['matches']:
            if pair=='A5' and match['stage']!=3:continue
            trace=native_trace(match);logs=records(match)
            visibility=np.zeros((len(trace.states),2),bool)
            ages=[];unavailable=[0,0]
            for role,rows in enumerate(logs):
                for j,row in enumerate(rows):
                    obs=row['observation'];f=obs['frame']
                    if f>=len(visibility):continue
                    end=min(rows[j+1]['observation']['frame'] if j+1<len(rows) else len(visibility),len(visibility))
                    visibility[f:end,role]=any(e['visible'] for e in obs['enemies'])
                    stamp=obs['own']['sample_frame']
                    if stamp is None:unavailable[role]+=1
                    else:ages.append(f-stamp)
            directory=ROOT/match['source']
            inputs=[directory/name for name in ('result.json','inputs-per-present.jsonl','native-barriers.jsonl','policy-0.jsonl','policy-1.jsonl')]
            results.append(dict(pair=pair,**match,routes=route_summary(trace.states,trace.actions,match['stage'],visibility),
                policy_sample_age=dict(min=min(ages),median=float(np.median(ages)),p95=float(np.percentile(ages,95)),max=max(ages)),
                missing_own_observations=unavailable,source_sha256={str(p.relative_to(ROOT)):sha256(p) for p in inputs}))
    OUT.mkdir(parents=True,exist_ok=True)
    data=dict(schema='sim.route.native.v1',games=results,
              clock='Deduplicated own position sample frame; policy visibility/input at call time, held to next call.',
              limitations=['No per-cell native paint; HUD losses are not last-hit attribution.','Sample-held dwell is an estimate, not continuous native telemetry.'])
    (OUT/'native.json').write_text(json.dumps(data,indent=2)+'\n')
    return data


def _run_group(job):
    pair,stage,swap,mode,seeds,frames,out=job
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    source=json.loads((WORK/'sources.json').read_text())
    candidates=[m for m in source['references'][pair]['matches'] if m['stage']==stage and (m['role_to_policy'][0]==1)==swap]
    # Unobserved native seat: only ground baseline is defined; do not invent a
    # mirrored native recording or count it as a matched historical replay.
    if mode!='ground' and not candidates:raise ValueError('no recorded native seat')
    match=candidates[0] if candidates else None
    paths=[ROOT/source['policies'][p]['root'] for p in PAIRS[pair]]
    specs=[PolicySpec.load(p) for p in paths]
    if [s.source_sha256 for s in specs]!=[source['policies'][p]['directory_sha256'] for p in PAIRS[pair]]:
        raise ValueError('frozen policy changed')
    models=Models(ROOT/'work/sim/fidelity/motion.json',ROOT/'work/sim/fidelity/weapon.json',ROOT/'work/sim/advanced/model.json')
    binding=dict(core=core_hashes(),diagnosis=sha256(Path(__file__)),models={k:sha256(p) for k,p in models.paths.items()},
                 sources=sha256(WORK/'sources.json'),clock_code=sha256(ROOT/'sim/observation_clock.py'),
                 reset_code=sha256(ROOT/'sim/horizon.py'),
                 native={name:sha256(ROOT/match['source']/name) for name in ('native-barriers.jsonl','policy-0.jsonl','policy-1.jsonl')} if match else None)
    plan=dict(pair=pair,stage=stage,swap=swap,mode=mode,seeds=seeds,frames=frames,boundary=BOUNDARY,binding=binding,
              prefix_source=match['source'] if mode!='ground' else None)
    encoded=json.dumps(plan,indent=2)+'\n';plan_path=out/'plan.json'
    if plan_path.exists() and plan_path.read_text()!=encoded:raise ValueError('experiment plan changed; use new output')
    plan_path.write_text(encoded)
    if (out/'result.json').exists():return json.loads((out/'result.json').read_text())
    terrain=Terrain.load(stage);parameters=Parameters.local()
    from .ranking_report import immutable_inputs
    immutable_inputs(dict(sim_source_sha256=binding['core'],model_sha256=binding['models']))
    batch=VectorBatchSimulator(seeds,stage,parameters=parameters,terrain=terrain,loadouts=[s.loadout for s in specs],
         duration_frames=frames,motion_model=models[0],weapon_model=models[1],advanced_model=models[2])
    states=np.full((seeds,frames+1,2,12),np.nan);actions=np.zeros((seeds,frames,2,13),np.float32)
    vis=np.zeros((seeds,frames+1,2),bool);paint=np.zeros((seeds,frames+1,2),np.float32)
    clocks={}
    def capture(j,env):
        states[j,env.frame]=[[*p.position,p.heading,p.yaw,p.pitch,p.hp,p.ink,float(p.squid),
                             5 if not p.grounded else 0 if p.submerged else 4,float(p.alive),p.special] for p in env.players]
        paint[j,env.frame]=env.paint.ratios()
        if j in clocks:clocks[j].capture()
    for j,env in enumerate(batch.envs):
        env.swap=swap;env.reset(seed=j);env.match_id=f'diagnosis-{pair}-{stage}-{int(swap)}-{mode}-{j}'
        env.projector=PolicyProjector(env.match_id,stage_id=stage);env._observations=None
        original=env._weapons
        def record(original=original,j=j,env=env):
            original();capture(j,env)
        env._weapons=record
    held=[{f'player_{i}':neutral() for i in range(2)} for _ in range(seeds)]
    cadence=math.gcd(*(s.step_frames for s in specs));start=time.perf_counter()
    prefix_replay=[]
    with ExitStack() as stack:
        workers=[[stack.enter_context(ControlProcess(p,out/f'{j}-{i}.stderr.log',s.step_timeout))
                  for i,(p,s) in enumerate(zip(paths,specs))] for j in range(seeds)]
        if mode!='ground':
            logs=records(match);trace=native_trace(match)
            for j,(env,duo) in enumerate(zip(batch.envs,workers)):
                for role,(worker,rows) in enumerate(zip(duo,logs)):
                    for row in rows:
                        obs=row['observation']
                        if obs['frame']>=BOUNDARY:break
                        special=OwnSpecial(f'player_{role}',obs['own']['sample_frame'] or 0,obs['own'].get('special'))
                        actual=worker.act(typed_record(obs,match['role_to_policy'],env.match_id),special)
                        delta=max(abs(a-b) for k in actual for a,b in zip(actual[k],row['action'][k]))
                        prefix_replay.append(delta)
                        if delta>1e-6:raise ValueError('frozen policy prefix differs from native action')
                identity=env.match_id
                reset_native(env,trace,BOUNDARY)
                env.match_id=identity;env.projector=PolicyProjector(identity,stage_id=stage);env._observations=None
        for j,env in enumerate(batch.envs):
            perturb(env,j);capture(j,env)
            if mode=='prefix-clock':
                from .observation_clock import from_policy_logs
                clocks[j]=from_policy_logs(env,logs)
                env.truth=clocks[j].truth;env._observations=None
        while not batch.envs[0].done:
            f=batch.envs[0].frame
            for j,(env,duo) in enumerate(zip(batch.envs,workers)):
                for role,(worker,spec) in enumerate(zip(duo,specs)):
                    if f%spec.step_frames==0:
                        obs=env.typed_observation(role)
                        vis[j,f,role]=any(e.visible for e in obs.enemies)
                        special=(clocks[j].special(role) if j in clocks else OwnSpecial(f'player_{role}',f,env.players[role].special))
                        held[j][f'player_{role}']=worker.act(obs,special)
            count=min(cadence,frames-f)
            for j in range(seeds):
                for role in range(2):
                    a=held[j][f'player_{role}'];actions[j,f:f+count,role]=[*a['sticks'],*a['gyro'],*a['buttons']]
                    vis[j,f:f+count,role]=vis[j,f,role] if f%specs[role].step_frames==0 else vis[j,f-1,role]
            batch.step(held,count,observe=False)
    games=[]
    for j,env in enumerate(batch.envs):
        np.savez_compressed(out/f'trace-{j}.npz',states=states[j],actions=actions[j],visibility=vis[j],paint=paint[j])
        hud=[sum(e['kind']=='knockdown' and e['target']==1-i for e in env.events) for i in range(2)]
        falls=[sum(e['kind']=='knockdown' and e['target']==i and e['cause']=='fall' for e in env.events) for i in range(2)]
        games.append(dict(stage=stage,swap=swap,seed=j,cohort='fixed' if j==0 else 'initial_sensitivity',**env.info(),
            hud_downs=hud,environmental_downs=falls,mechanics=dict(Counter(e['kind'] for e in env.events)),
            trajectory_sha256=hashlib.sha256(states[j].astype('<f8').tobytes()).hexdigest(),
            routes=route_summary(states[j],actions[j],stage,vis[j]),events=env.events,
            trace_sha256=sha256(out/f'trace-{j}.npz')))
    if (core_hashes()!=binding['core'] or sha256(Path(__file__))!=binding['diagnosis']
            or sha256(ROOT/'sim/observation_clock.py')!=binding['clock_code']
            or sha256(ROOT/'sim/horizon.py')!=binding['reset_code']):raise ValueError('source changed during run')
    result=dict(**plan,games=games,wall_seconds=time.perf_counter()-start,
                prefix_action_checks=len(prefix_replay),prefix_action_max_error=max(prefix_replay,default=None))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(pair=pair,stage=stage,swap=swap,mode=mode,seconds=round(result['wall_seconds'],1),winners=[g['winner'] for g in games])),flush=True)
    return result


def run_group(job):
    try:return _run_group(job)
    except BaseException as exc:
        directory=Path(job[-1]);directory.mkdir(parents=True,exist_ok=True)
        failure=dict(job=list(job[:-1]),exception=repr(exc),traceback=traceback.format_exc(),
                     completed=False,interpretation='Collection failure, no match outcome inferred.')
        (directory/'failure.json').write_text(json.dumps(failure,indent=2)+'\n')
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory',action='store_true');p.add_argument('--run',action='store_true')
    p.add_argument('--mode',choices=('ground','prefix','prefix-clock'),default='ground')
    p.add_argument('--pairs',nargs='+',choices=('A5','R1','R2'),default=['A5','R1','R2'])
    p.add_argument('--stages',nargs='+',type=int,choices=(1,2,3),default=[1,2,3])
    p.add_argument('--seeds',type=int,default=6);p.add_argument('--frames',type=int,default=10800)
    p.add_argument('--workers',type=int,choices=(1,2),default=1)
    p.add_argument('--out',type=Path,default=OUT/'runs')
    a=p.parse_args()
    if ROOT/'work' not in a.out.resolve().parents:p.error('artifacts must stay under work/')
    if not 1<=a.seeds<=100 or a.frames<=BOUNDARY:p.error('positive seeds <=100, frames >120 required')
    if a.inventory:print('native games',len(inventory()['games']),flush=True)
    if a.run:
        source=json.loads((WORK/'sources.json').read_text());jobs=[]
        for pair in a.pairs:
            for stage in a.stages:
                if pair=='A5' and stage!=3:continue
                for swap in (False,True):
                    if a.mode!='ground' and not any(m['stage']==stage and (m['role_to_policy'][0]==1)==swap for m in source['references'][pair]['matches']):continue
                    name=f'{pair}-map{stage}-side{int(swap)}-{a.mode}'
                    jobs.append((pair,stage,swap,a.mode,a.seeds,a.frames,str(a.out/name)))
        if a.workers==1:
            for job in jobs:run_group(job)
        else:
            with ProcessPoolExecutor(max_workers=a.workers) as pool:list(pool.map(run_group,jobs))


if __name__=='__main__':main()
