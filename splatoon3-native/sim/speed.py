"""One/two CPU-worker throughput with full scalar vs vectorized environments."""
import os

# Limit this benchmark and its spawned workers only; no system settings change.
for _thread_setting in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[_thread_setting] = '1'

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import math
import multiprocessing
from pathlib import Path
import time

import numpy as np

from .batch import VectorBatchSimulator
from .corpus import WORK
from .engine import BatchSimulator, neutral
from .motion import MotionModel
from .parameters import Parameters, ROOT, sha256
from .terrain import Terrain
from .weapon import WeaponModel


def benchmark(kind, count, frames, workload, seed=0):
    setup = time.perf_counter()
    model, weapon = MotionModel.load(WORK/'motion.json'), WeaponModel.load(WORK/'weapon.json')
    parameters, terrain = Parameters.local(), Terrain.load(1)
    cls = BatchSimulator if kind == 'scalar' else VectorBatchSimulator
    batch = cls(count, motion_model=model, weapon_model=weapon, parameters=parameters,
                terrain=terrain, duration_frames=frames)
    rng = np.random.default_rng(seed)
    for env in batch.envs:
        for i, p in enumerate(env.players):
            p.position = np.array([8.+6*i, 3., 8.+rng.uniform(-.15, .15)])
            p.heading = p.yaw = math.pi/2 if i == 0 else -math.pi/2
            p.pitch = -.14
    setup_seconds = time.perf_counter()-setup
    start = time.perf_counter()
    for frame in range(frames):
        actions = []
        for index in range(count):
            a = {f'player_{i}': neutral() for i in range(2)}
            for i in range(2):
                if workload == 'movement':
                    a[f'player_{i}']['sticks'][:2] = [.3*math.sin(index+frame*.02), .65]
                    a[f'player_{i}']['buttons'][4] = int(frame % 100 == 40)
                else:
                    a[f'player_{i}']['buttons'][0] = int(frame % 60 < 21)
                    a[f'player_{i}']['buttons'][1] = int(frame % 60 > 45)
            actions.append(a)
        if kind == 'scalar':
            for env, action in zip(batch.envs, actions): env.step(action, observe=False)
        else:
            batch.step(actions, observe=False)
    seconds = time.perf_counter()-start
    state = [[*p.position, *p.velocity, p.hp, p.ink, p.heading, p.yaw, p.pitch, float(p.squid), float(p.alive)]
             for env in batch.envs for p in env.players]
    return dict(kind=kind, games=count, frames_per_game=frames, workload=workload,
                compute_seconds=seconds, setup_seconds=setup_seconds,
                environment_frames_per_second=count*frames/seconds,
                damage_events=sum(v['kind']=='damage' for e in batch.envs for v in e.events),
                knockdowns=sum(v['kind']=='knockdown' for e in batch.envs for v in e.events),
                final_state=state)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--games', type=int, default=16)
    p.add_argument('--frames', type=int, default=120)
    p.add_argument('--workers', type=int, choices=(1, 2), default=2)
    p.add_argument('--out', type=Path, default=WORK/'speed.json')
    args = p.parse_args()
    if ROOT/'work' not in args.out.resolve().parents:
        p.error('benchmark artifacts must stay under work/')
    results = []
    for workload in ('movement', 'combat'):
        scalar = benchmark('scalar', args.games, args.frames, workload)
        vector = benchmark('vector', args.games, args.frames, workload)
        equal = bool(np.allclose(scalar['final_state'], vector['final_state'], atol=1e-8, rtol=1e-8))
        if not equal or (scalar['damage_events'], scalar['knockdowns']) != (vector['damage_events'], vector['knockdowns']):
            raise RuntimeError('batch benchmark changed scalar judgment')
        results.extend([scalar, vector])
        print(workload, 'scalar', round(scalar['environment_frames_per_second'],1),
              'vector', round(vector['environment_frames_per_second'],1), 'equal', equal, flush=True)
    parallel = []
    if args.workers > 1:
        context = multiprocessing.get_context('spawn')
        for workload in ('movement', 'combat'):
            start = time.perf_counter()
            with ProcessPoolExecutor(max_workers=args.workers, mp_context=context) as pool:
                futures = [pool.submit(benchmark, 'vector', args.games, args.frames, workload, i)
                           for i in range(args.workers)]
                rows = [future.result() for future in futures]
            wall = time.perf_counter()-start
            total = args.games*args.frames*args.workers
            parallel.append(dict(workers=args.workers, games_per_worker=args.games, workload=workload,
                frames_per_game=args.frames, wall_seconds_including_startup=wall,
                end_to_end_environment_frames_per_second=total/wall,
                compute_environment_frames_per_second=total/max(row['compute_seconds'] for row in rows),
                worker_compute_seconds=[row['compute_seconds'] for row in rows]))
            print(workload, args.workers, 'workers compute', round(parallel[-1]['compute_environment_frames_per_second'],1), flush=True)
    for row in results: row.pop('final_state')
    result = dict(schema='sim.speed.v2', single_worker=results, multi_worker=parallel,
                  units='one frame = one two-player environment advanced 1/60 game second',
                  limitations=['NumPy movement/support queries vectorized; weapons/paint remain scalar.',
                               'Single process / BLAS threads=1, no OS core affinity guarantee.',
                               'No policy subprocesses or visibility/observation serialization in timed loop.',
                               'Other A7/A8 activity may affect wall time; not an isolated machine benchmark.'],
                  models={p.name:sha256(p) for p in (WORK/'motion.json', WORK/'weapon.json')})
    args.out.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
