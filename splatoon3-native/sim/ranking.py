"""Offline policy matches on three maps, both seats, registered sensitivities.

No native environment imports. Every game has its own sandboxed policy workers
at unchanged cadence and deadline. Seeds describe initial-condition sensitivity,
not independent draws from an identified native probability distribution.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np

from arena.config import PolicySpec
from arena.control_process import ControlProcess, OwnSpecial
from .advanced import AdvancedModel
from .batch import VectorBatchSimulator
from .engine import neutral
from .motion import MotionModel
from .parameters import ROOT, Parameters, sha256
from .ranking_sources import WORK, PAIRS
from .terrain import Terrain
from .weapon import WeaponModel

CORE = ('engine.py','terrain.py','batch.py','motion.py','weapon.py','advanced.py','parameters.py','ranking.py')


def core_hashes():
    return {name:sha256(ROOT/'sim'/name) for name in CORE}

def scenarios(seeds=6):
    if not 1 <= seeds <= 100:
        raise ValueError('positive seed count <=100')
    return [dict(stage=s, swap=bool(side), seed=seed,
                 cohort='fixed' if seed==0 else 'initial_sensitivity')
            for s in (1,2,3) for side in (0,1) for seed in range(seeds)]


def perturb(env, seed):
    if not seed:
        return [[0.,0.,0.] for _ in env.players]
    rng = np.random.default_rng(seed)  # same draw paired across seats/maps/pairs
    delta = []
    for p in env.players:
        d = rng.uniform([-.15,-.15,-.03], [.15,.15,.03])
        if env.opening_model is not None and env.frame==0:
            p.position[[0,2]]+=d[:2]
            p.opening_delta+=d[:2]
        else:
            p.position = env.terrain.move(p.position, np.array([d[0],0,d[1]]),
                                         env.rules.terrain_radius, True, support_aware=True)
        p.yaw += float(d[2]); p.heading = p.yaw
        delta.append(d.tolist())
    env._observations = None
    return delta


def group(pair, specs, plans, paths, out, parameters, terrain, models, frames, *, extras=None, clock_period=None):
    started = time.perf_counter()
    batch = VectorBatchSimulator(len(plans), plans[0]['stage'], parameters=parameters, terrain=terrain,
             loadouts=[s.loadout for s in specs], duration_frames=frames,
             motion_model=models[0], weapon_model=models[1], advanced_model=models[2], **(extras or {}))
    actions = [{f'player_{i}':neutral() for i in range(2)} for _ in plans]
    starts = []
    trajectories = [hashlib.sha256() for _ in plans]
    for env, plan in zip(batch.envs, plans):
        env.swap = plan['swap']; env.reset(seed=plan['seed'])
        delta = perturb(env, plan['seed'])
        starts.append(dict(requested_delta_x_z_yaw=delta, position=[p.position.tolist() for p in env.players],
                           yaw=[p.yaw for p in env.players]))
        # Reproducible identity; no policy sees private seed or perturbation.
        env.match_id = 'sim-ranking-'+pair+'-'+str(plan['stage'])+'-'+str(int(plan['swap']))+'-'+str(plan['seed'])
        from arena.visibility import PolicyProjector
        env.projector = PolicyProjector(env.match_id, stage_id=env.stage_id)
        env._observations = None
    clocks=[]
    if clock_period:
        from .observation_clock import RecordedClock
        for env in batch.envs:
            stamps=np.full((frames+1,2),-1,int)
            for role in (0,1):
                for f in range(clock_period+1,frames+1):
                    stamps[f,role]=((f-1)//clock_period)*clock_period
            clock=RecordedClock(env,stamps);clocks.append(clock)
            env.truth=clock.truth
            original=env._weapons
            def capture(original=original,clock=clock):
                original();clock.capture()
            env._weapons=capture;env._observations=None
    cadence = math.gcd(*(s.step_frames for s in specs))
    calls = Counter()
    with ExitStack() as stack:
        workers = [[stack.enter_context(ControlProcess(path, out/f'{j}-{i}.stderr.log', spec.step_timeout))
                    for i,(spec,path) in enumerate(zip(specs, paths))] for j in range(len(plans))]
        while not batch.envs[0].done:
            for j, (env, duo) in enumerate(zip(batch.envs, workers)):
                for i, (worker, spec) in enumerate(zip(duo, specs)):
                    if env.frame % spec.step_frames == 0:
                        obs = env.typed_observation(i)
                        special=clocks[j].special(i) if clocks else OwnSpecial(f'player_{i}',env.frame,env.players[i].special)
                        actions[j][f'player_{i}'] = worker.act(obs, special)
                        calls[str(i)] += 1
            count = min(cadence,frames-batch.envs[0].frame)
            batch.step(actions, count, observe=False)
            for env,digest in zip(batch.envs,trajectories):
                digest.update(np.array([[*p.position,p.hp,p.ink,float(p.alive)] for p in env.players],dtype='<f8').tobytes())
    elapsed = time.perf_counter()-started
    results = []
    for j, (env,plan) in enumerate(zip(batch.envs, plans)):
        hud = [sum(v['kind']=='knockdown' and v['target']==1-i for v in env.events) for i in range(2)]
        kills = [sum(v['kind']=='knockdown' and v['attacker']==i for v in env.events) for i in range(2)]
        falls = [sum(v['kind']=='knockdown' and v['target']==i and v['cause']=='fall' for v in env.events) for i in range(2)]
        results.append(dict(**plan, **env.info(), policies=PAIRS[pair], initial=starts[j],
                            hud_downs=hud, attributed_kills=kills, environmental_downs=falls,
                            mechanics=dict(Counter(v['kind'] for v in env.events)),
                            trajectory_sha256=trajectories[j].hexdigest()))
    return dict(schema='sim.ranking.group.v1', pair=pair, frames_per_game=frames, games=results,
                wall_seconds=elapsed, environment_frames_per_second=frames*len(plans)/elapsed,
                policy_calls=dict(calls), policy_sha256=[s.source_sha256 for s in specs],
                model_sha256={k:sha256(p) for k,p in models.paths.items()},
                sim_source_sha256=core_hashes(),clock_period=clock_period)


class Models(list):
    def __init__(self, motion, weapon, advanced):
        super().__init__([MotionModel.load(motion),WeaponModel.load(weapon),AdvancedModel.load(advanced)])
        self.paths = dict(motion=motion,weapon=weapon,advanced=advanced)


def run(out=WORK, seeds=6, frames=10800, pairs=tuple(PAIRS), batch_size=6):
    out = Path(out).resolve()
    if ROOT/'work' not in out.parents:
        raise ValueError('raw output must stay under work/')
    source = json.loads((out/'sources.json').read_text())
    models = Models(ROOT/'work/sim/fidelity/motion.json', ROOT/'work/sim/fidelity/weapon.json',
                    ROOT/'work/sim/advanced/model.json')
    parameters = Parameters.local()
    plan_path = out/'plan.json'
    plan = dict(schema='sim.ranking.plan.v1', frames=frames, seeds=seeds, scenarios=scenarios(seeds),
                sources_sha256=sha256(out/'sources.json'), model_sha256={k:sha256(p) for k,p in models.paths.items()},
                sim_source_sha256=core_hashes(),
                interpretation='Seed 0 fixed; others paired +/-0.15 X/Z, +/-0.03 rad yaw sensitivities; not native independent trials.')
    encoded = json.dumps(plan,indent=2)+'\n'
    if plan_path.exists() and plan_path.read_text() != encoded:
        raise ValueError('existing experiment plan differs; use a new output directory')
    plan_path.write_text(encoded)  # before any result; outcome-independent
    for stage in (1,2,3):
        terrain = Terrain.load(stage)
        plans = [p for p in plan['scenarios'] if p['stage']==stage]
        for pair in pairs:
            paths = [ROOT/source['policies'][name]['root'] for name in PAIRS[pair]]
            specs = [PolicySpec.load(p) for p in paths]
            for s,name in zip(specs,PAIRS[pair]):
                if s.source_sha256 != source['policies'][name]['directory_sha256']:
                    raise ValueError('frozen policy drift')
            for offset in range(0,len(plans),batch_size):
                directory = out/f'{pair}-map{stage}-batch{offset//batch_size:02}'
                result = directory/'result.json'
                if result.exists():
                    old=json.loads(result.read_text())
                    if (old['model_sha256'] != plan['model_sha256'] or old['policy_sha256'] != [s.source_sha256 for s in specs]
                            or old['sim_source_sha256'] != plan['sim_source_sha256'] or old['frames_per_game'] != frames
                            or [{k:g[k] for k in ('stage','swap','seed','cohort')} for g in old['games']] != plans[offset:offset+batch_size]):
                        raise ValueError('existing result binding differs')
                    continue
                directory.mkdir(parents=True,exist_ok=True)
                if core_hashes()!=plan['sim_source_sha256']:
                    raise ValueError('core changed during registered experiment')
                data = group(pair,specs,plans[offset:offset+batch_size],paths,directory,parameters,terrain,models,frames)
                result.write_text(json.dumps(data,indent=2)+'\n')
                print(json.dumps(dict(pair=pair,stage=stage,batch=offset//batch_size,
                                      games=len(data['games']),seconds=round(data['wall_seconds'],2),
                                      fps=round(data['environment_frames_per_second'],1),
                                      winners=[g['winner'] for g in data['games']])),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=WORK)
    p.add_argument('--seeds',type=int,default=6)
    p.add_argument('--frames',type=int,default=10800)
    p.add_argument('--pairs',nargs='+',choices=list(PAIRS),default=list(PAIRS))
    p.add_argument('--batch-size',type=int,default=6)
    a=p.parse_args()
    run(a.out,a.seeds,a.frames,a.pairs,a.batch_size)
