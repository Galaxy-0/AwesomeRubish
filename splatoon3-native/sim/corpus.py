"""Normalize immutable native recordings into private, sample-clock NPZ caches.

No strategy source is read. Only frozen config.toml is used for historical gear.
All records, fitted models and caches stay under ignored work/sim/fidelity/.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tomllib

import numpy as np

from .parameters import ROOT, sha256

FIELDS = ('x', 'y', 'z', 'heading', 'yaw', 'pitch', 'hp', 'ink', 'squid', 'contact', 'alive', 'special')
WORK = ROOT / 'work/sim/fidelity'


def frozen_loadouts(directory, result):
    parent = directory.parent
    metadata = parent / 'result.json'
    if not metadata.exists():
        return None, []
    data = json.loads(metadata.read_text())
    paths = data.get('policy_snapshots')
    if paths is None:
        # Earlier tournaments keep frozen runtime policies in policies/a,b.
        paths = [str(parent / 'policies' / name) for name in ('a', 'b')]
    mapping = result.get('role_to_policy', [0, 1])
    configs, sources = [], []
    for role in range(2):
        path = Path(paths[mapping[role]]) / 'config.toml'
        if not path.exists():
            return None, []
        configs.append(tomllib.loads(path.read_text())['loadout'])
        sources.append(path)
    return configs, sources


def inventory():
    """Dedupe sessions; exclude void/unfinished/empty attempts before fitting."""
    seen, games, rejected = set(), [], []
    for path in sorted((ROOT / 'work/arena').glob('**/inputs-per-present.jsonl')):
        directory = path.parent
        result_path, states = directory / 'result.json', directory / 'native-barriers.jsonl'
        if not result_path.exists() or not states.exists():
            continue
        data = json.loads(result_path.read_text())
        key = data.get('session', str(directory))
        reason = ('void/unfinished' if not data.get('passed') or data.get('void') else
                  'empty trace' if not path.stat().st_size or not states.stat().st_size else
                  'duplicate session' if key in seen else None)
        if reason:
            rejected.append(dict(path=str(directory.relative_to(ROOT)), reason=reason))
            continue
        seen.add(key)
        # Entire sessions are held out; no temporal fragments cross this split.
        # Actual T1 rounds are held out as a family, avoiding sibling-game leakage.
        is_t1 = 't1' in directory.relative_to(ROOT / 'work/arena').parts
        split = 'test' if is_t1 else ('validation' if int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 5 == 0 else 'train')
        games.append(dict(path=str(directory.relative_to(ROOT)), stage=int(data['stage']), split=split))
    return games, rejected


def normalize(game, out=WORK):
    directory = ROOT / game['path']
    result_path = directory / 'result.json'
    result = json.loads(result_path.read_text())
    paths = [result_path, directory / 'inputs-per-present.jsonl', directory / 'native-barriers.jsonl']
    loadouts, config_paths = frozen_loadouts(directory, result)
    paths += config_paths
    sources = {str(p.relative_to(ROOT)): sha256(p) for p in paths}
    cache_id = hashlib.sha256(str(directory.relative_to(ROOT)).encode()).hexdigest()[:16]
    dest = out / 'traces' / (cache_id + '.npz')
    meta_path = dest.with_suffix('.json')
    if dest.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if meta.get('sources') == sources and meta.get('schema') == 'sim.trace.v2':
            return dict(**game, cache=str(dest.relative_to(ROOT)), samples=meta['samples'], loadouts=loadouts)
    end = result['frames']
    actions = np.full((end, 2, 13), np.nan, dtype=np.float32)
    for line in (directory / 'inputs-per-present.jsonl').open():
        row = json.loads(line)
        lo, hi = row['frame_interval']
        if not 0 <= lo < hi <= end or np.isfinite(actions[lo:hi]).any():
            raise ValueError('overlap/invalid interval: ' + str(directory))
        for role in range(2):
            a = row['actions'][f'player_{role}']
            actions[lo:hi, role] = [*a['sticks'], *a['gyro'], *a['buttons']]
    states = np.full((end + 1, 2, len(FIELDS)), np.nan, dtype=np.float64)
    available = np.full((end + 1, 2), end + 1, dtype=np.int32)
    origins, battle_end = None, None
    for line in (directory / 'native-barriers.jsonl').open():
        row = json.loads(line)
        ack = row['frame']
        if origins is None:
            origins = [v['frame'] - ack for v in row['infos'].values()]
        if battle_end is None and all(v.get('time_valid') and v['remaining_time'] <= 0 for v in row['infos'].values()):
            battle_end = ack
        for role in range(2):
            info = row['infos'][f'player_{role}']
            if info['frame'] - ack != origins[role]:
                raise ValueError('native origin changed within trace')
            frame = info.get('position_sample_frame', -1) - origins[role]
            if not 0 <= frame <= end or ack > end or not info.get('position_valid'):
                continue
            if available[frame, role] <= ack:
                continue  # repeated packets retain first availability only
            available[frame, role] = ack
            view, motion = info.get('own_view', {}), info.get('referee_motion', {})
            def scalar(key):
                return info[key] if info.get(key + '_valid') else np.nan
            states[frame, role] = [*info['position'], scalar('heading'),
                view.get('yaw', np.nan) if view.get('valid') else np.nan,
                view.get('pitch', np.nan) if view.get('valid') else np.nan,
                scalar('hp'), scalar('ink'), motion.get('form_squid', np.nan),
                motion.get('ground_contact', np.nan), scalar('alive'), scalar('special')]
    battle_end = battle_end or min(end, 10800)
    if not np.isfinite(actions[:battle_end]).all():
        raise ValueError('missing input coverage: ' + str(directory))
    states, actions, available = states[:battle_end+1], actions[:battle_end], available[:battle_end+1]
    if any(sha256(ROOT / p) != digest for p, digest in sources.items()):
        raise ValueError('trace changed during normalization')
    dest.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(dest, states=states, actions=actions, available=available)
    meta = dict(schema='sim.trace.v2', fields=FIELDS, sources=sources, origins=origins,
                frames=battle_end, samples=int(np.isfinite(states[:, :, 0]).sum()),
                loadouts=loadouts, stage=game['stage'], split=game['split'])
    meta_path.write_text(json.dumps(meta, indent=2) + '\n')
    return dict(**game, cache=str(dest.relative_to(ROOT)), samples=meta['samples'], loadouts=loadouts)


class Trace:
    def __init__(self, entry):
        self.entry = entry
        with np.load(ROOT / entry['cache'], allow_pickle=False) as data:
            self.states = data['states']
            self.actions = data['actions']
            self.available = data['available']
        self.frames = len(self.actions)
        self.samples = [np.flatnonzero(np.isfinite(self.states[:, i, 0])) for i in range(2)]

    def past(self, frame, role):
        ids = self.samples[role]
        ids = ids[(ids <= frame) & (self.available[ids, role] <= frame)]
        return ids[-2:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=WORK)
    args = parser.parse_args()
    if ROOT / 'work' not in args.out.resolve().parents:
        parser.error('corpus artifacts must stay under work/')
    games, rejected = inventory()
    accepted = []
    for i, game in enumerate(games):
        try:
            accepted.append(normalize(game, args.out))
        except (ValueError, KeyError) as exc:
            rejected.append(dict(**game, reason=str(exc)))
        if (i+1) % 20 == 0:
            print('normalized', i+1, '/', len(games), flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    result = dict(schema='sim.corpus.v2', games=accepted, rejected=rejected,
                  split='whole native session; T1 family held out; other sessions hash 80/20 train/validation')
    (args.out / 'corpus.json').write_text(json.dumps(result, indent=2) + '\n')
    from collections import Counter
    print(json.dumps(dict(games=len(accepted), rejected=len(rejected),
                          splits=dict(Counter(x['split'] for x in accepted)),
                          samples=sum(x['samples'] for x in accepted)), indent=2))


if __name__ == '__main__':
    main()
