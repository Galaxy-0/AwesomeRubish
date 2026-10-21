#!/usr/bin/env python3
"""Compile an offline, asset-free tactical showcase. Never starts a game host."""
from __future__ import annotations
import argparse
import hashlib
import heapq
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from arena.geometry import CollisionMesh, GeometricVision, VisionConfig
from arena.lib.atlas import MapAtlas
from arena.lib import stamper_data as weapon
from arena.referee import PlayerTruth, RefereeSnapshot
from derive_3d import enrich_map
from derive_traces import compile_traces
from zipcaster import compile_zipcaster

MAPS = [('Yunohana', '温泉峡谷'), ('District00', 'District00'), ('Yagara', 'Yagara')]
REGIONS = {'center': '中路', 'central_high': '中央高台', 'west_lane': '西侧通路', 'east_lane': '东侧通路'}
SOURCES: dict[str, str] = {}
GRID = 2.0
VISION_GRID = 10.0


def source(path):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    SOURCES[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return path


def read(path):
    return json.loads(source(path).read_text())


def shortest(atlas, start):
    distances = [math.inf] * len(atlas.points)
    previous = [None] * len(atlas.points)
    distances[start] = 0
    queue = [(0., start)]
    while queue:
        cost, p = heapq.heappop(queue)
        if cost != distances[p]:
            continue
        for q in atlas.edges[p]:
            candidate = cost + math.dist(atlas.points[p], atlas.points[q])
            if candidate < distances[q]:
                distances[q] = candidate
                previous[q] = p
                heapq.heappush(queue, (candidate, q))
    return distances, previous


def position(p):
    return [round(p[0], 1), round(p[1], 1), round(p[2], 1)]


def calculate_map(name, title, speed):
    path = ROOT / 'work/arena/maps' / name
    atlas = MapAtlas(read(path / 'navigation.json'))
    source(path / 'sight.npz')
    source('arena/geometry.py')
    source('arena/lib/atlas.py')
    # The compiled page contains quantized scalar cells, not mesh vertices or faces.
    cache_key = hashlib.sha256(json.dumps([SOURCES[str((path / 'navigation.json').relative_to(ROOT))],
        SOURCES[str((path / 'sight.npz').relative_to(ROOT))], SOURCES['arena/geometry.py'],
        SOURCES['arena/lib/atlas.py'], speed, GRID, VISION_GRID, 'showcase-map-v2']).encode()).hexdigest()
    cache = ROOT / 'work/showcase' / f'{name}-{cache_key[:16]}.json'
    if cache.exists():
        print(f'{title}: reuse derived analysis', flush=True)
        return json.loads(cache.read_text())
    print(f'{title}: shortest paths + geometric visibility', flush=True)
    origins = [atlas.nearest(atlas.spawns[side]['ground']) for side in ('alpha', 'bravo')]
    searches = [shortest(atlas, start) for start in origins]
    reachable = [i for i in range(len(atlas.points)) if any(math.isfinite(d[i]) for d, _ in searches)]
    # Keep the upper reachable layer per top-down bin; lower stacked floors are omitted.
    bins = {}
    for i in reachable:
        x, y, z = atlas.points[i]
        key = (int(round(x / GRID)), int(round(z / GRID)))
        if key not in bins or y > atlas.points[bins[key]][1]:
            bins[key] = i
    coarse = {}
    for i in bins.values():
        x, y, z = atlas.points[i]
        key = (int(round(x / VISION_GRID)), int(round(z / VISION_GRID)))
        center = (key[0] * VISION_GRID, key[1] * VISION_GRID)
        rank = math.hypot(x - center[0], z - center[1])
        if key not in coarse or rank < coarse[key][0]:
            coarse[key] = (rank, i)
    sample_ids = [v[1] for _, v in sorted(coarse.items())]
    targets = tuple(PlayerTruth(str(n), 1, 8000, True, atlas.points[i], 0., 1., 1., False, 0, False)
                    for n, i in enumerate(sample_ids))
    vision = GeometricVision(CollisionMesh.load(path / 'sight.npz'),
                             VisionConfig(half_fov_degrees=180, max_distance=100))
    visibility = []
    for count, i in enumerate(sample_ids):
        own = PlayerTruth('observer', 0, 8000, True, atlas.points[i], 0., 1., 1., False, 0, False)
        truth = RefereeSnapshot('showcase-offline', 0, (own,) + targets)
        witnesses = vision.witnesses(truth, 'observer')
        seen = sum(w.in_fov and w.line_clear for n, w in enumerate(witnesses) if sample_ids[n] != i)
        visibility.append(position(atlas.points[i]) + [round(100 * seen / max(1, len(targets) - 1), 1)])
        if count % 60 == 0:
            print(f'  vision {count}/{len(sample_ids)}', flush=True)
    cells = []
    for (gx, gz), i in sorted(bins.items()):
        times = [round(d[i] / speed, 1) if math.isfinite(d[i]) else None for d, _ in searches]
        nearest = min(range(len(visibility)), key=lambda v: (visibility[v][0] - gx * GRID)**2 +
                      (visibility[v][2] - gz * GRID)**2 + 4 * (visibility[v][1] - atlas.points[i][1])**2)
        cells.append([gx * GRID, round(atlas.points[i][1], 1), gz * GRID, *times, visibility[nearest][3]])
    points = []
    for key, label in REGIONS.items():
        target = atlas.nearest(atlas.region(key))
        routes = []
        for d, prev in searches:
            route = []
            q = target
            if math.isfinite(d[q]):
                while q is not None:
                    route.append(position(atlas.points[q]))
                    q = prev[q]
            routes.append(list(reversed(route)))
        points.append(dict(id=key, label=label, position=position(atlas.points[target]),
                           times=[round(d[target] / speed, 1) if math.isfinite(d[target]) else None
                                  for d, _ in searches], routes=routes))
    result = dict(id=name, name=title, cells=cells, visibility=visibility, points=points,
                  spawns=[position(atlas.points[i]) for i in origins], grid=GRID,
                  sample_count=len(targets), node_count=len(atlas.points),
                  bounds=[min(c[0] for c in cells), max(c[0] for c in cells),
                          min(c[2] for c in cells), max(c[2] for c in cells)],
                  heights=[min(c[1] for c in cells), max(c[1] for c in cells)])
    cache.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':')))
    return result


TACTICS = {
    'alpha': [
        ('v0', '高区与两侧路循环，沿路挥刀；优先处理近距离可见敌人。', '路线状态机'),
        ('v1', '逐帧调用，加入蓄斩、预判、受击撤退与发射台重返战场。', '逐帧'),
        ('v2', '移动反击、世界坐标走位与朝向威胁撤退，压缩低效远战。', '不再背对威胁逃跑'),
        ('v3', '以自身到访和挥刀尝试的新颖度选区域，取代固定中场循环。', '记录自己的覆盖努力'),
        ('v4', '对准地面才单帧出刀，覆盖前沿随局时推进。', '按反馈出刀'),
        ('v5', '保留返中路线，以随人平移的瞄准平面稳定移动涂地。', '中央返程集合'),
        ('v6', '扩大中后程新区域搜索，并清理位置突变后的旧路线。', '扩大中后程覆盖'),
    ],
    'bravo': [
        ('v0', '侧路展开、近敌才交战；最后 22 秒优先涂地。', '最后 22 秒'),
        ('v1', '修复倒下后发射台停摆，加入预判满蓄与轻挥收尾。', '重生回场优先'),
        ('v2', '用可解释覆盖评分器寻找较少重复的可达地面。', '可解释覆盖评分器'),
        ('v3', '连续横移与低血撤离，避开近期受伤和倒下区域。', '连续的横移'),
        ('v4', '干地回墨失败后换位，按行进距离出刀并限制终局路线成本。', '干地回墨48帧'),
        ('v5', '独立地面喷涂器同时检查偏航与俯仰，恢复有墨时的铺色密度。', '独立地面喷涂器'),
    ],
}


def story():
    r0 = read('work/arena/tournament-20261019-113138-347725/result.json')
    s = r0['statistics']
    assert s['valid_games'] == 50 and s['failed_or_cancelled'] == 0
    rounds = [dict(round=0, versions=['v0', 'v0'], hashes=r0['source_hashes'], games=50,
                   wins=[s['wins'], s['losses']], turf=[p['score_percentage_points']['mean'] for p in s['by_policy']],
                   downs=[p['own_hud_downs'] for p in s['by_policy']], maps=[])]
    versions = {}
    snapshot_by_version = {}
    for n in range(1, 10):
        d = read(f'work/arena/t1/round-{n:03d}/summary.json')
        full = read(f'work/arena/t1/round-{n:03d}/result.json')
        assert d['passed'] and d['complete'] and len(d['games']) == 3
        vs = []
        for who, sha in zip(('alpha', 'bravo'), d['source_hashes']):
            versions.setdefault(who, {})
            if sha not in versions[who]:
                versions[who][sha] = f'v{len(versions[who]) + 1}'
            vs.append(versions[who][sha])
            snapshot_by_version[(who, vs[-1])] = Path(full['policy_snapshots'][len(vs) - 1])
        rounds.append(dict(round=n, versions=vs, hashes=d['source_hashes'], games=3,
            wins=[d['wins']['a'], d['wins']['b']],
            turf=[round(sum(g['score_by_policy'][p] for g in d['games']) / 3, 3) for p in ('a', 'b')],
            downs=[sum(g['hud_by_policy'][p]['own_hud_downs'] for g in d['games']) for p in ('a', 'b')],
            maps=[dict(map=g['map'], score=[round(g['score_by_policy'][p], 2) for p in ('a', 'b')],
                       winner=g['winner_name']) for g in d['games']]))
    tactics = {}
    for who, items in TACTICS.items():
        notes_path = source(f'arena/policies/{who}/NOTES.md')
        notes = notes_path.read_text()
        tactics[who] = []
        for version, summary, evidence in items:
            assert evidence in notes, (who, version, evidence)
            card_path = ROOT / f'work/arena/proficiency/{who}-{version}.json'
            if version == 'v0':
                card_path = ROOT / f'arena/results/proficiency/{who}.json'
            card = read(card_path) if card_path.exists() else None
            binding = None
            if card:
                assert card['measured'] == card['total'] == 13
                expected_hash = (r0['source_hashes'][0 if who == 'alpha' else 1] if version == 'v0'
                                 else next((sha for sha, v in versions[who].items() if v == version), None))
                if card['source_sha256'] == expected_hash:
                    binding = 'exact_source_hash'
                elif expected_hash:
                    # Tournament directory hashes also cover notes, checks and old versions.
                    # An independently captured version card can have a different directory
                    # hash. Verify each entry/auxiliary module and config before associating it.
                    frozen = Path(card['policy_version']['snapshot'])
                    tournament = snapshot_by_version[(who, version)]
                    for f in sorted(frozen.glob('*')):
                        if f.suffix != '.py' and f.name != 'config.toml':
                            continue
                        source(f)
                        other = source(tournament / f.name)
                        assert f.read_bytes() == other.read_bytes(), (who, version, f.name)
                    binding = 'runtime_files_equal_directory_hash_differs'
            tactics[who].append(dict(version=version, text=summary,
                score=card['aggregate_score'] if card else None,
                measured=card['measured'] if card else None, total=card['total'] if card else None,
                source_hash=card['source_sha256'] if card else None,
                binding=binding,
                evidence_line=next(i for i, line in enumerate(notes.splitlines(), 1) if evidence in line)))
    a5 = read('arena/results/a5-accepted-70-20261019.json')
    return dict(rounds=rounds, tactics=tactics,
                baseline=dict(policies=a5['policy_order'], games=a5['statistics']['valid_games'],
                              wins=[a5['statistics']['wins'], a5['statistics']['losses']]))


def calibration():
    d = read('work/sim/window-20261021/comparison.json')
    return dict(rows=[dict(frames=p['horizon'], windows=p['before']['windows'],
                          before=p['before']['metrics']['position']['rmse'],
                          after=p['final']['metrics']['position']['rmse'],
                          hp_before=p['before']['metrics']['hp']['mean'],
                          hp_after=p['final']['metrics']['hp']['mean']) for p in d['primary']],
                yagara={k: d['pairs']['A5'][k] for k in ('native', 'before', 'after')},
                ranks={k: {phase: d['pairs'][k][phase]['wins'] for phase in ('native', 'after')}
                       for k in ('R1', 'R2', 'R3')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'showcase/index.html')
    args = parser.parse_args()
    (ROOT / 'work/showcase').mkdir(parents=True, exist_ok=True)
    motion = read('work/sim/window-20261021/models-v2/motion.json')
    speed = motion['modes']['human']['speed'] * 60
    data = dict(schema='showcase.d1.v1', snapshot='2026-10-21', speed=round(speed, 6),
                maps=[enrich_map(calculate_map(n, title, speed), ROOT, source) for n, title in MAPS], story=story(),
                traces=compile_traces(ROOT, source),
                calibration=calibration(),
                weapon=dict(id=weapon.WEAPON_ID, damage=[weapon.LIGHT_PROJECTILE_DAMAGE, weapon.FULL_PROJECTILE_DAMAGE],
                    range=[list(weapon.LIGHT_RANGE_BRACKET), list(weapon.FULL_RANGE_BRACKET)],
                    charge=[weapon.MINIMUM_OBSERVED_STANDING_RELEASE, weapon.MINIMUM_OBSERVED_EMERGE_INPUT_RELEASE],
                    repeat=weapon.LIGHT_REPEAT_INPUT_PERIOD, special_points=weapon.SPECIAL_BASE_POINTS))
    source('arena/lib/stamper_data.py')
    source('showcase/derive_traces.py')
    source('showcase/zipcaster.py')
    data['zipcaster'], zip_clips = compile_zipcaster(ROOT, source)
    data['traces'][:0] = zip_clips
    scene_path = source('showcase/scene.js')
    template_path = source('showcase/template.html')
    source('showcase/build.py')
    data['sources'] = SOURCES
    (ROOT / 'showcase/data').mkdir(exist_ok=True)
    (ROOT / 'showcase/data/derived.json').write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')))
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c')
    template = template_path.read_text()
    assert template.count('__SHOWCASE_DATA__') == 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(template.replace('__SHOWCASE_DATA__', payload).replace('__SCENE_SCRIPT__', scene_path.read_text()))
    assert args.out.stat().st_size < 10_000_000, 'preview must stay under10MB'
    print(f'Built {args.out} ({args.out.stat().st_size:,} bytes), {len(SOURCES)} evidence files.')


if __name__ == '__main__':
    main()
