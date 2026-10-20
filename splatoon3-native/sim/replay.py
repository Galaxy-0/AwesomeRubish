"""Offline same-controller-input comparison. Never imports a native runner.

Native packet sample frames are aligned separately for each host. The simulator
is initialized once per selected window; subsequent truth never corrects it.
Native paint/velocity/action-state are unavailable and are explicitly unmeasured.
"""
import argparse
import json
from pathlib import Path
import time

import numpy as np

from arena.visibility import PolicyProjector
from .engine import Simulator, neutral
from .parameters import ROOT, sha256


def read_jsonl(path):
    with Path(path).open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def stats(values):
    a = np.array(values, float)
    if not len(a):
        return dict(samples=0, mean=None, rmse=None, p95=None, maximum=None)
    return dict(samples=len(a), mean=float(a.mean()), rmse=float(np.sqrt(np.mean(a**2))),
                p95=float(np.percentile(a, 95)), maximum=float(a.max()))


def provenance(paths):
    return {str(Path(path).resolve().relative_to(ROOT)): sha256(path) for path in paths}


def initialize(env, barrier, origins, *, own_ink_fixture=False, previous_actions=None):
    """Only observed fields initialized. Hidden velocity/weapon state stay zero."""
    env.frame = barrier['frame']
    ages = {}
    for i, p in enumerate(env.players):
        key = f'player_{i}'
        info = barrier['infos'][key]
        p.position = np.array(info['position'], float)
        p.heading = info['heading']
        p.yaw = info['own_view']['yaw']
        p.pitch = info['own_view']['pitch']
        p.hp, p.ink = float(info['hp']), float(info['ink'])
        p.alive = bool(info['alive'])
        p.special = float(info['special']) if info.get('special_valid') else 0.
        motion = info.get('referee_motion', {})
        p.squid = bool(motion.get('form_squid'))
        p.grounded = motion.get('ground_contact') != 5
        p.hurt_at = env.frame  # avoid inventing an observed recovery delay
        p.previous = list((previous_actions or {}).get(key, neutral())['buttons'])
        ages[key] = env.frame - (info['position_sample_frame'] - origins[key])
        # Match the accepted NativeRefereeAdapter: squid + contact 0 is
        # submerged; 4 is non-submerged, 5 airborne. Never invert 0 and 4.
        if own_ink_fixture or p.squid and motion.get('ground_contact') == 0:
            env.paint.disk(p.position, 1.5, i)
            p.submerged = p.squid
    env.projector = PolicyProjector(env.match_id, stage_id=env.stage_id)
    env._observations = None
    return dict(initial_sample_age_frames=ages, velocity='unknown; initialized zero',
                weapon_state='unknown; initialized idle', previous_input='last recorded interval',
                paint=('own-ink disks under both players from fixture precondition' if own_ink_fixture else
                       'unknown map; only observed submergence seeds own-ink disk'),
                rest_of_paint='unpainted approximation; native paint unavailable')


def compare(env, intervals, barriers, start_index, end_frame, *, own_ink_fixture=False):
    first = barriers[start_index]
    origins = {key: info['frame'] - first['frame'] for key, info in first['infos'].items()}
    previous = next((row['actions'] for row in intervals
                     if row['frame_interval'][0] < first['frame'] <= row['frame_interval'][1]), None)
    initialization = initialize(env, first, origins, own_ink_fixture=own_ink_fixture, previous_actions=previous)
    end_frame = min(end_frame, barriers[-1]['frame'], env.duration)
    if end_frame <= env.frame:
        raise ValueError('empty comparison window')
    snapshots = {}
    start = env.frame
    started = time.perf_counter()
    cursor = 0
    while env.frame < end_frame:
        while cursor < len(intervals) and intervals[cursor]['frame_interval'][1] <= env.frame:
            cursor += 1
        if cursor == len(intervals):
            raise ValueError('recording ends before requested window')
        row = intervals[cursor]
        lo, hi = row['frame_interval']
        if not lo <= env.frame < hi:
            raise ValueError('gap in recorded inputs')
        env.step(row['actions'], observe=False)
        snapshots[env.frame] = [(p.position.copy(), p.hp, p.ink, p.alive) for p in env.players]
    seconds = time.perf_counter() - started
    per_player, curves = {}, {}
    for team in range(2):
        key = f'player_{team}'
        seen = set()
        position_errors, hp_errors, ink_errors, alive_errors = [], [], [], []
        native_damage, native_down = [], []
        curve = []
        old_hp, old_alive = first['infos'][key]['hp'], bool(first['infos'][key]['alive'])
        for barrier in barriers[start_index + 1:]:
            if barrier['frame'] > end_frame + 8:
                break
            info = barrier['infos'][key]
            frame = info['position_sample_frame'] - origins[key]
            if frame in seen or frame not in snapshots:
                continue
            seen.add(frame)
            pos, hp, ink, alive = snapshots[frame][team]
            curve.append([frame, *info['position'], *map(float, pos), info['hp'], hp,
                          info['ink'], ink, int(bool(info['alive'])), int(alive)])
            if info.get('position_valid'):
                position_errors.append(float(np.linalg.norm(pos - info['position'])))
            if info.get('hp_valid'):
                hp_errors.append(abs(hp - info['hp']))
                if old_hp - info['hp'] >= .29:
                    native_damage.append(dict(frame=frame, hp_drop=old_hp - info['hp']))
                old_hp = info['hp']
            if info.get('ink_valid'):
                ink_errors.append(abs(ink - info['ink']))
            if info.get('alive_valid'):
                if old_alive and not info['alive']:
                    native_down.append(frame)
                old_alive = bool(info['alive'])
                alive_errors.append(int(alive != bool(info['alive'])))
        damage = [v for v in env.events if v['kind'] == 'damage' and v['target'] == team]
        downs = [v['frame'] for v in env.events if v['kind'] == 'knockdown' and v['target'] == team]
        # Order matching is diagnostic only; unmatched events stay explicit.
        per_player[key] = dict(position_world_units=stats(position_errors), hp_fraction=stats(hp_errors),
            ink_fraction=stats(ink_errors), alive_disagreement=stats(alive_errors),
            native_direct_damage_samples=native_damage, simulated_damage=damage,
            first_direct_damage_delay_frames=(damage[0]['frame'] - native_damage[0]['frame']
                if damage and native_damage else None),
            native_knockdown_sample_frames=native_down, simulated_knockdown_frames=downs,
            first_knockdown_delay_frames=(downs[0] - native_down[0] if downs and native_down else None))
        curves[key] = curve
    return dict(start_frame=start, end_frame=end_frame, frames=end_frame - start,
                wall_seconds=seconds, frames_per_second=(end_frame - start) / seconds,
                initialization=initialization, players=per_player, simulator=env.info(),
                sampled_curves=dict(columns=['frame', 'native_x', 'native_y', 'native_z',
                     'sim_x', 'sim_y', 'sim_z', 'native_hp', 'sim_hp', 'native_ink', 'sim_ink',
                     'native_alive', 'sim_alive'], players=curves),
                notes=['No teacher forcing after initialization.',
                       'Native event times are packet observation bounds, not exact hit frames.',
                       'HP and ink normalized to 0..1; position in native world units.',
                       'No native world paint map or weapon/velocity state is available.'])


def tournament(directory, frames=600, *, parameters=None, terrain=None):
    directory = Path(directory)
    result_path = directory / 'result.json'
    result = json.loads(result_path.read_text())
    if not result.get('passed') or result.get('void'):
        raise ValueError('comparison requires a valid completed native game')
    input_path, states_path = directory / 'inputs-per-present.jsonl', directory / 'native-barriers.jsonl'
    sources = provenance([result_path, input_path, states_path])
    inputs, barriers = read_jsonl(input_path), read_jsonl(states_path)
    # Skip the unsupported spawner flight using a recorded common ground barrier.
    start_index = next(i for i, row in enumerate(barriers) if all(
        v.get('position_valid') and v['position'][1] < 20 and v.get('alive') and
        v.get('referee_motion', {}).get('ground_contact') == 0 for v in row['infos'].values()))
    end = next(row['frame'] for row in barriers if all(
        v.get('time_valid') and v['remaining_time'] <= 0 for v in row['infos'].values()))
    target = end if frames is None else min(end, barriers[start_index]['frame'] + frames)
    env = Simulator(result['stage'], parameters=parameters, terrain=terrain, duration_frames=end)
    report = compare(env, inputs, barriers, start_index, target)
    native_turf = result.get('turf_ratio_by_role')
    turf_error = ([100 * (a-b) for a, b in zip(env.paint.ratios(), native_turf)]
                  if target == end and native_turf is not None else None)
    report.update(kind='T1 same-input window', stage=result['stage'], sources=sources,
                  loadout_status='unknown in per-game result; baseline AP=0, not current strategy config',
                  native_final_turf_ratio=result.get('turf_ratio_by_role'),
                  turf_error_pp=turf_error,
                  turf_comparison=('diagnostic final score difference only: omitted launch, unknown initial paint, '
                                   'baseline gear, approximate paintable denominator; not parity acceptance'
                                   if target == end else 'unavailable: prefix window is not a full match'))
    return report


def a6_case(directory, prefix, *, parameters=None, terrain=None, weapon_model=None):
    directory = Path(directory)
    path = directory / 'steps.jsonl'
    sources = provenance([directory / 'result.json', path])
    rows = read_jsonl(path)
    intervals, barriers = [], []
    frame = 0
    indices = []
    for i, row in enumerate(rows):
        if 'actions' not in row:
            raise ValueError('legacy trace lacks actions; use an explicitly reconstructed script comparison')
        count = row.get('frames', next(iter(row['infos'].values()))['advanced'])
        intervals.append(dict(frame_interval=[frame, frame + count], actions=row['actions']))
        frame += count
        barriers.append(dict(frame=frame, infos=row['infos']))
        if row['label'].startswith(prefix):
            indices.append(i)
    if not indices or indices[0] == 0:
        raise ValueError('missing case/precondition barrier')
    env = Simulator(1, parameters=parameters, terrain=terrain, duration_frames=frame, weapon_model=weapon_model)
    report = compare(env, intervals, barriers, indices[0] - 1, barriers[indices[-1]]['frame'], own_ink_fixture=True)
    report.update(kind='A6 same-input isolated fixture', case=prefix,
                  sources=sources, turf_error_pp=None,
                  turf_comparison='unknown native paint; seeded own-ink fixture only')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--frames', type=int, default=600, help='0 = rest of battle to timer zero')
    p.add_argument('--a6-prefix')
    p.add_argument('--out', type=Path, default=ROOT / 'work/sim/replay.json')
    args = p.parse_args()
    if ROOT / 'work' not in args.out.resolve().parents:
        p.error('raw comparison output must stay under work/')
    report = a6_case(args.directory, args.a6_prefix) if args.a6_prefix else tournament(args.directory, args.frames or None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('sources', 'notes', 'sampled_curves')}, indent=2))


if __name__ == '__main__':
    main()
