"""Freeze historical git policies and audit the six native matchup references.

Only git/read-only historical results are consulted; outputs stay under work/.
Native directory hashes include notes/version archives, so runtime-file equality
is checked separately against the actual frozen T1 policy directories.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from arena.config import PolicySpec
from .parameters import ROOT, sha256

WORK = ROOT / 'work/sim/ranking'
PAIRS = {'A5': ('rush', 'high-ground'), 'R0': ('alpha-v0', 'bravo-v0'),
         'R1': ('alpha-v1', 'bravo-v1'), 'R2': ('alpha-v2', 'bravo-v1'),
         'R3': ('alpha-v3', 'bravo-v1'), 'R4': ('alpha-v3', 'bravo-v2')}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def extract(name, ref, directory, out):
    prefix = git('rev-parse', '--show-prefix').decode().strip()
    tree = prefix + directory
    commit = git('rev-parse', ref+'^{commit}').decode().strip()
    files = git('ls-tree', '-r', '--name-only', '--full-name', commit, '--', directory).decode().splitlines()
    if not files:
        raise ValueError(f'empty policy tree: {ref}:{tree}')
    destination = out / 'policies' / name
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for file in files:
        rel = str(Path(file).relative_to(tree))
        data = git('show', f'{commit}:{file}')
        path = destination / rel
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f'existing snapshot differs: {path}')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest[rel] = hashlib.sha256(data).hexdigest()
    return dict(root=str(destination.relative_to(ROOT)), ref=ref, commit=commit,
                directory=directory, files=manifest,
                directory_sha256=PolicySpec.load(destination).source_sha256)


def mapped_match(match):
    mapping = match['role_to_policy']
    def reorder(values):
        return [values[mapping.index(i)] for i in range(2)]
    hud = match['hud_by_role']
    return dict(stage=match['stage'], role_to_policy=mapping,
                outcome=match['outcome'], turf_pp=reorder(match['score_by_role']),
                hud_downs=reorder([hud[f'player_{i}']['enemy_hud_downs'] for i in range(2)]),
                environmental_downs=reorder([hud[f'player_{i}']['own_environmental_downs'] for i in range(2)]),
                source=match['artifacts'], session=match['session'])


def prepare(out=WORK):
    out = Path(out).resolve()
    if ROOT/'work' not in out.parents:
        raise ValueError('snapshots/results must stay under work/')
    out.mkdir(parents=True, exist_ok=True)
    snapshots = {}
    for name in ('alpha', 'bravo'):
        for version in range(1, 4 if name == 'alpha' else 3):
            key = f'{name}-v{version}'
            snapshots[key] = extract(key, 't1-'+key, f'arena/policies/{name}', out)
        key = name+'-v0'
        snapshots[key] = extract(key, 'e64744d', f'arena/policies/{name}', out)
    for name in ('rush', 'high-ground'):
        snapshots[name] = extract(name, '66263d1', f'arena/policies/{name}', out)
    sources = {'A5': ROOT/'arena/results/a5-paused-70-20261019.json',
               'R0': ROOT/'work/arena/tournament-20261019-113138-347725/result.json'}
    sources.update({f'R{i}': ROOT/f'work/arena/t1/round-{i:03}/result.json' for i in range(1, 5)})
    references = {}
    for label, path in sources.items():
        raw = json.loads(path.read_text())
        matches = [m for m in raw['matches'] if m.get('passed') and not m.get('void')]
        pair = PAIRS[label]
        verified = []
        for role, name in enumerate(pair):
            snapshot = snapshots[name]
            runtime = {k:v for k,v in snapshot['files'].items() if '/' not in k and (k.endswith('.py') or k == 'config.toml')}
            frozen = Path(raw['policy_snapshots'][role]) if 'policy_snapshots' in raw else None
            if frozen:
                actual = {p.name:sha256(p) for p in frozen.iterdir() if p.is_file() and
                          (p.suffix == '.py' or p.name == 'config.toml')}
                if actual != runtime:
                    raise ValueError(f'{label} {name}: runtime differs from native frozen policy')
                if PolicySpec.load(frozen).source_sha256 != raw['source_hashes'][role]:
                    raise ValueError('native frozen directory hash drift')
            elif snapshot['directory_sha256'] != raw['source_hashes'][role]:
                raise ValueError(f'{label} {name}: historical git directory hash differs')
            verified.append(dict(policy=name, native_directory_sha256=raw['source_hashes'][role],
                                 runtime_files=runtime, exact_runtime_equal=True))
        expected = {'A5':70, 'R0':50}.get(label, 3)
        if len(matches) != expected:
            raise ValueError(f'{label}: valid game count differs')
        references[label] = dict(pair=pair, source=str(path.relative_to(ROOT)), sha256=sha256(path),
                                 policies=verified, matches=[mapped_match(m) for m in matches],
                                 statistics=raw['statistics'])
    audit = ROOT/'arena/results/a5-accepted-70-20261019.json'
    accepted = json.loads(audit.read_text())
    if not accepted['accepted'] or accepted['source_sha256'] != sha256(sources['A5']):
        raise ValueError('A5 accepted checkpoint differs')
    report = dict(schema='sim.ranking.sources.v1', policies=snapshots, references=references,
                  a5_acceptance=dict(path=str(audit.relative_to(ROOT)), sha256=sha256(audit)),
                  public_library_sha256={str(p.relative_to(ROOT)):sha256(p) for p in (ROOT/'arena/lib').glob('*.py')})
    (out/'sources.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=WORK)
    a = p.parse_args()
    data = prepare(a.out)
    print(json.dumps({k:dict(pair=v['pair'], native_games=len(v['matches'])) for k,v in data['references'].items()}, indent=2))
