"""Evaluate independent reset windows concurrently with the full batch core."""
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import time

import numpy as np

from .batch import VectorBatchSimulator
from .corpus import Trace
from .horizon import action_dict, measure, reset_native
from .parameters import Parameters, ROOT, sha256
from .replay import stats
from .terrain import Terrain


def evaluate_vector(entries, horizons, *, model, weapon_model, batch_size, out):
    out = Path(out).resolve()
    if ROOT/'work' not in out.parents:
        raise ValueError('raw horizon output must stay under work/')
    sources = {str(p.relative_to(ROOT)):sha256(p) for p in (ROOT/'sim').glob('*.py')}
    parameters = Parameters.local()
    results = []
    for entry in entries:
        trace, terrain = Trace(entry), Terrain.load(entry['stage'])
        for horizon in horizons:
            started = time.perf_counter()
            counts, ages = Counter(), []
            errors, endpoints, windows = defaultdict(list), defaultdict(list), []
            anchors = list(range(horizon, trace.frames-horizon+1, horizon))
            for start in range(0, len(anchors), batch_size):
                group = anchors[start:start+batch_size]
                batch = VectorBatchSimulator(len(group), entry['stage'], parameters=parameters, terrain=terrain,
                    motion_model=model, weapon_model=weapon_model, loadouts=entry.get('loadouts'), duration_frames=trace.frames)
                accepted = []
                for anchor, env in zip(group, batch.envs):
                    try:
                        meta = reset_native(env, trace, anchor)
                    except ValueError as exc:
                        counts[str(exc)] += 1
                        continue
                    if any(not p.alive or p.position[1] > 20 or p.position[1] < -20 for p in env.players):
                        counts['dead/launch anchor'] += 1
                        continue
                    accepted.append((anchor, env))
                    ages.extend(v['sample_age'] for v in meta)
                if not accepted: continue
                batch.envs = [env for _, env in accepted]
                per_window = [defaultdict(list) for _ in accepted]
                moving = [False]*len(accepted)
                last = [{} for _ in accepted]
                counts['windows'] += len(accepted)
                for offset in range(1, horizon+1):
                    actions = [action_dict(trace.actions[anchor+offset-1]) for anchor, _ in accepted]
                    batch.step(actions, observe=False)
                    for index, (anchor, env) in enumerate(accepted):
                        frame = anchor+offset
                        for role, p in enumerate(env.players):
                            row = trace.states[frame, role]
                            if not np.isfinite(row[0]): continue
                            counts['samples'] += 1
                            values = measure(p, row)
                            for name, value in values.items():
                                if math.isfinite(value):
                                    errors[name].append(value)
                                    per_window[index][name].append(value)
                            last[index][role] = values
                            moving[index] = bool(moving[index] or np.linalg.norm(trace.actions[frame-1,role,:2])>.2)
                for index, (anchor, _) in enumerate(accepted):
                    if not per_window[index]: continue
                    for values in last[index].values():
                        for name, value in values.items():
                            if math.isfinite(value): endpoints[name].append(value)
                    windows.append(dict(anchor=anchor,moving=moving[index],
                        errors={name:stats(v) for name,v in per_window[index].items()}))
            results.append(dict(stage=entry['stage'],trace=entry['path'],horizon=horizon,counts=dict(counts),
                sample_age=stats(ages),all_samples={k:stats(v) for k,v in errors.items()},
                endpoint_samples={k:stats(v) for k,v in endpoints.items()},
                window_rmse={k:stats([w['errors'][k]['rmse'] for w in windows if k in w['errors']]) for k in errors},
                moving_window_rmse={k:stats([w['errors'][k]['rmse'] for w in windows if w['moving'] and k in w['errors']]) for k in errors},
                wall_seconds=time.perf_counter()-started,windows=windows))
            print('vector horizon',entry['stage'],horizon,'windows',counts['windows'],
                  'position RMSE',round(stats(errors['position'])['rmse'] or 0,4),flush=True)
            out.parent.mkdir(parents=True,exist_ok=True)
            out.with_suffix('.partial.json').write_text(json.dumps(dict(results=results),allow_nan=False)+'\n')
    report=dict(schema='sim.horizon.v2',results=results,model=model.to_dict(),
                weapon_model=None if weapon_model is None else weapon_model.data,
                code_sha256_at_start=sources,batch_size=batch_size,
                protocol='Same causal resets/metrics as scalar horizon; complete combat, not motion-only surrogate.')
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report
