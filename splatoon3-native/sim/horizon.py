"""Primary N=30/60/120/300 sample-clock, causally initialized comparisons."""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import time

import numpy as np

from .corpus import Trace, WORK
from .engine import Simulator
from .parameters import Parameters, ROOT, sha256
from .replay import stats
from .terrain import Terrain


def angle_error(a, b):
    return abs(math.atan2(math.sin(a-b), math.cos(a-b)))


def action_dict(array):
    return {f'player_{i}': dict(sticks=array[i, :4].tolist(), gyro=array[i, 4:7].tolist(),
                               buttons=array[i, 7:].tolist()) for i in range(2)}


def reset_native(env, trace, anchor):
    """Reset all observable fields, infer hidden state from PAST only.

    Native paint/projectiles/velocity/weapon phase are not measured. Past
    velocity and finite input history are estimates, not injected true values.
    """
    env.reset()
    env.frame = anchor
    metadata = []
    for role, p in enumerate(env.players):
        past = trace.past(anchor, role)
        if len(past) < 2:
            raise ValueError('insufficient past samples')
        before, latest = past
        row, old = trace.states[latest, role], trace.states[before, role]
        age = anchor-latest
        if age > 8 or not np.isfinite(row[:11]).all() or row[8] not in (0, 1) or row[9] not in (0, 4, 5):
            raise ValueError('stale/unknown observable anchor')
        p.position = row[:3].copy()
        velocity = (row[:3]-old[:3]) / (latest-before)
        if np.linalg.norm(velocity) > 1.5 or not np.isfinite(velocity).all():
            velocity = np.zeros(3)  # teleport/launch cannot identify velocity
        p.velocity[:] = velocity
        p.position += age * velocity  # propagate stale packet to boundary causally
        p.heading, p.yaw, p.pitch = row[3:6]
        p.hp, p.ink = row[6:8]
        p.squid, p.grounded, p.alive = bool(row[8]), row[9] != 5, bool(row[10])
        p.submerged = p.squid and row[9] == 0
        p.special = float(row[11]) if np.isfinite(row[11]) else 0.
        p.hurt_at = anchor  # unobserved recovery clock remains conservative
        history = trace.actions[max(0, anchor-180):anchor, role]
        p.previous = history[-1, 7:].astype(int).tolist() if len(history) else [0]*6
        held = 0
        for value in reversed(history[:, 7]):
            if not value: break
            held += 1
        p.charge = held if not p.squid else 0
        edges = np.flatnonzero(np.diff(history[:, 7]) < 0)
        if len(edges):
            since = len(history)-edges[-1]-2
            p.cooldown = max(0, env.rules.light_input_period-1-since)
            p.recover_stop = max(0, 40-since)
        if p.submerged:
            env.paint.disk(p.position, 1.5, role)
        metadata.append(dict(sample_age=int(age), velocity_estimated_from_past=True,
                             weapon_phase_estimated=True, native_paint_available=False))
    env.projectiles, env.slashes, env.scheduled, env.events, env.damage_queue = [], [], [], [], []
    if env.weapon_model is not None:
        from .engine import gear_factor
        for p in env.players:
            p.reserved = env.weapon_model.reserve(env.params, p.charge)*gear_factor('ink_saver_main', p.ap.get('ink_saver_main', 0))
    env._observations = None
    return metadata


def primary_entries(corpus):
    # Predeclared fixed three-map test set; all T1 sessions remain excluded
    # from fitting. The other held-out sessions serve transition diagnostics.
    entries = [g for g in corpus['games'] if g['split'] == 'test' and '/round-001/' in g['path']]
    return sorted(entries, key=lambda g: g['stage'])


def evaluate(entries, horizons=(30, 60, 120, 300), *, model=None, max_windows=None,
             out=WORK / 'horizon-baseline.json'):
    out = Path(out).resolve()
    if ROOT / 'work' not in out.parents:
        raise ValueError('raw horizon output must stay under work/')
    sources = {str(p.relative_to(ROOT)): sha256(p) for p in (ROOT/'sim').glob('*.py')}
    parameters = Parameters.local()
    results = []
    for entry in entries:
        trace = Trace(entry)
        terrain = Terrain.load(entry['stage'])
        env = Simulator(entry['stage'], parameters=parameters, terrain=terrain,
                        loadouts=entry.get('loadouts'), duration_frames=trace.frames,
                        **({'motion_model': model} if model is not None else {}))
        for horizon in horizons:
            errors, endpoints = defaultdict(list), defaultdict(list)
            counts, ages, windows = Counter(), [], []
            started = time.perf_counter()
            for anchor in range(horizon, trace.frames-horizon+1, horizon):
                try:
                    meta = reset_native(env, trace, anchor)
                except ValueError as exc:
                    counts[str(exc)] += 1
                    continue
                if any(not p.alive or p.position[1] > 20 or p.position[1] < -20 for p in env.players):
                    counts['dead/launch anchor'] += 1
                    continue
                if max_windows is not None and counts['windows'] >= max_windows:
                    break
                counts['windows'] += 1
                ages.extend(v['sample_age'] for v in meta)
                window_errors = defaultdict(list)
                last_values = {}
                moving = False
                for frame in range(anchor+1, anchor+horizon+1):
                    env.step(action_dict(trace.actions[frame-1]), observe=False)
                    for role, p in enumerate(env.players):
                        row = trace.states[frame, role]
                        if not np.isfinite(row[0]):
                            continue
                        counts['samples'] += 1
                        values = dict(position=float(np.linalg.norm(p.position-row[:3])),
                                      horizontal=float(np.linalg.norm((p.position-row[:3])[[0, 2]])),
                                      vertical=abs(float(p.position[1]-row[1])),
                                      heading=angle_error(p.heading, row[3]), yaw=angle_error(p.yaw, row[4]),
                                      ink=abs(p.ink-row[7]), hp=abs(p.hp-row[6]),
                                      squid=int(p.squid != bool(row[8])),
                                      submerged=int(p.submerged != bool(row[8] == 1 and row[9] == 0)),
                                      alive=int(p.alive != bool(row[10])))
                        for name, value in values.items():
                            if math.isfinite(value):
                                errors[name].append(value)
                                window_errors[name].append(value)
                        last_values[role] = values
                        moving = bool(moving or np.linalg.norm(trace.actions[frame-1, role, :2]) > .2)
                if not window_errors:
                    continue
                for values in last_values.values():
                    for name, value in values.items():
                        if math.isfinite(value):
                            endpoints[name].append(value)
                record = dict(anchor=anchor, moving=moving,
                              errors={name: stats(v) for name, v in window_errors.items()})
                windows.append(record)
            elapsed = time.perf_counter()-started
            results.append(dict(stage=entry['stage'], trace=entry['path'], horizon=horizon,
                counts=dict(counts), sample_age=stats(ages), all_samples={k: stats(v) for k, v in errors.items()},
                endpoint_samples={k: stats(v) for k, v in endpoints.items()},
                window_rmse={k: stats([w['errors'][k]['rmse'] for w in windows if k in w['errors']]) for k in errors},
                moving_window_rmse={k: stats([w['errors'][k]['rmse'] for w in windows if w['moving'] and k in w['errors']]) for k in errors},
                wall_seconds=elapsed, windows=windows))
            print('horizon', entry['stage'], horizon, 'windows', counts['windows'],
                  'position RMSE', round(stats(errors['position'])['rmse'] or 0, 4), flush=True)
            # Preserve completed horizons even if a later horizon fails.
            partial = Path(out).with_suffix('.partial.json')
            partial.parent.mkdir(parents=True, exist_ok=True)
            partial.write_text(json.dumps(dict(results=results), allow_nan=False) + '\n')
    report = dict(schema='sim.horizon.v2', results=results,
                  protocol='Reset every N common frames; causal sample/velocity/input-history initialization; no truth within window.',
                  unknowns=['native world paint', 'projectile state', 'exact weapon/recovery phase'],
                  model='legacy' if model is None else model.to_dict(), code_sha256_at_start=sources)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus', type=Path, default=WORK / 'corpus.json')
    p.add_argument('--model', type=Path)
    p.add_argument('--weapon-model', type=Path)
    p.add_argument('--vector-batch', type=int, default=0)
    p.add_argument('--out', type=Path, default=WORK / 'horizon-baseline.json')
    p.add_argument('--max-windows', type=int)
    args = p.parse_args()
    model = None
    if args.model:
        from .motion import MotionModel
        model = MotionModel.load(args.model)
    corpus = json.loads(args.corpus.read_text())
    if args.vector_batch:
        if model is None or args.vector_batch < 1 or args.max_windows is not None:
            p.error('vector mode needs a model, positive batch size and complete window grid')
        from .horizon_batch import evaluate_vector
        from .weapon import WeaponModel
        weapon = WeaponModel.load(args.weapon_model) if args.weapon_model else None
        evaluate_vector(primary_entries(corpus),(30,60,120,300),model=model,weapon_model=weapon,
                        batch_size=args.vector_batch,out=args.out)
    else:
        if args.weapon_model:
            p.error('use --vector-batch for combined weapon/model evaluation')
        evaluate(primary_entries(corpus), model=model, max_windows=args.max_windows, out=args.out)


if __name__ == '__main__':
    main()
