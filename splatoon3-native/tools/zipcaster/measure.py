#!/usr/bin/env python3
"""Reduce recorded native fixtures without starting hosts or inferring unobserved hits."""
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(info):
    keys = ('frame', 'position_sample_frame', 'position', 'hp', 'alive', 'ink',
            'special', 'remaining_time', 'own_view')
    return {k: info[k] for k in keys if k in info}


def movement(rows, start):
    """Distinct native position samples, not repeated RPC packets, for speed."""
    samples = {}
    for row in rows:
        info = row['infos']['player_0']
        if info.get('position_valid'):
            samples.setdefault(info['position_sample_frame'], info['position'])
    samples = sorted(samples.items())
    segments = [(a, b, math.dist(p, q), 60 * math.dist(p, q) / (b - a))
                for (a, p), (b, q) in zip(samples, samples[1:]) if b > a]
    moving = [s for s in segments if s[2] > .1]
    return dict(first_motion_native_sample_frame=next((f for f, p in samples if math.dist(p, start) > .1), None),
                max_segment_speed_units_per_second=max((s[3] for s in moving), default=0),
                moving_sample_segments=[dict(start=a, end=b, distance=d, speed_u_s=v) for a, b, d, v in moving],
                caveat='Body-position segments average multiple presents; includes acceleration, no hook-projectile readback.')


def load_run(path):
    result = json.loads((path / 'result.json').read_text())
    rows = [json.loads(s) for s in (path / 'steps.jsonl').read_text().splitlines()]
    return result, rows


def main(args):
    runs = {}; inventory = []
    for pointer in sorted((ROOT / 'work/d2').glob('*-latest.json')):
        path = Path(json.loads(pointer.read_text())['artifacts'])
        result, rows = load_run(path)
        commands = Path(result.get('commands', ROOT / f'work/d2/{pointer.stem.removesuffix("-latest")}.commands.jsonl'))
        command_results = commands.with_suffix('.results.jsonl')
        records = [json.loads(s) for s in command_results.read_text().splitlines()] if command_results.exists() else []
        files = [path / 'result.json', path / 'steps.jsonl']
        files += [p for p in (commands, command_results, path/'tested-serve.py') if p.is_file()]
        files += [Path(p) for p in result.get('raw_sha256', {}) if Path(p).is_file()]
        item = dict(name=pointer.stem.removesuffix('-latest'), artifacts=str(path.relative_to(ROOT)),
                    driver_completed=result.get('driver_completed', result['passed']), errors=result['errors'],
                    steps=len(rows), fixture_failures=[dict(command=c['command'], error=c.get('error')) for c in records if not c['completed']],
                    test_special_mode=result['test_special_mode'], loadouts=result['loadouts'],
                    host_sha256=result['host_build']['output_sha256'],
                    sha256={str(p.resolve().relative_to(ROOT)): digest(p) for p in set(files)})
        inventory.append(item)
        runs[item['name']] = (result, rows, records)

    statuses = {}
    for name, (_, _, records) in runs.items():
        statuses[name] = {c['command']['label']: {p: compact(i) for p, i in c['infos'].items()}
                          for c in records if c['command']['op'] == 'status' and c['completed']}

    discovery = []
    for case in runs['discovery'][0]['cases']:
        if 'start_frame' not in case:
            continue
        prefix = case['kind']; start = case['start_frame']
        rows = [r for r in runs['discovery'][1] if r['label'].startswith(prefix+'-')]
        released = [r for r in rows if r['label'] == prefix+'-R-released']
        first = released[0]['infos']['player_0']['frame'] - released[0]['frames'] + 1
        active = next((r['infos']['player_0']['frame']-start for r in rows if r['infos']['player_0']['special'] < .999), None)
        refilled = next((r['infos']['player_0']['frame']-start for r in rows
                         if r['infos']['player_0']['frame']>start+100 and r['infos']['player_0']['special'] >= .999), None)
        discovery.append(dict(case=prefix, rs_before_frame=start, R_release_first_input_frame=first,
            first_special_below_full_ack_delta=active, first_refill_observed_ack_delta=refilled,
            hold_frames=case['hold_frames'], hold_displacement=case['displacement_during_hold'],
            release_displacement=case['displacement_after_release'],
            movement=movement(released, case['held']['position'])))

    range_trials = []
    for prefix in ('range10','range24','range34','range35','range36','range37','range38'):
        s = statuses['hooks']; before = s[prefix+'-before']['player_0']; after = s[prefix+'-after']['player_0']
        eye = [before['position'][0], before['position'][1]+1.1, before['position'][2]]
        anchor = [-25.5,9.5,70.5]
        release_rows = [r for r in runs['hooks'][1] if r['label'] == prefix+'-released']
        range_trials.append(dict(case=prefix,before=before,after=after,aim=anchor,
            eye_to_intended_surface=math.dist(eye,anchor),body_displacement=math.dist(before['position'],after['position']),
            movement=movement(release_rows,before['position']),
            native_hook_surface_readback=False))

    rows = runs['combat-v3'][1]
    rs = next(r for r in rows if r['label']=='mc-RS'); origin = rs['infos']['player_0']['frame']-rs['frames']
    previous = 1.; changes = []
    for r in rows:
        if not r['label'].startswith('mc-'): continue
        i = r['infos']['player_1']
        if i['hp'] < previous - .001:
            changes.append(dict(label=r['label'],actor0_ack=r['infos']['player_0']['frame'],target_ack=i['frame'],
                target_sample=i['position_sample_frame'],relative_to_RS=r['infos']['player_0']['frame']-origin,
                hp_before=previous,hp_after=i['hp'],alive=bool(i['alive'])))
        previous=i['hp']
    combo = dict(statuses={k:v for k,v in statuses['combat-v3'].items() if k.startswith('mc-')},hp_decreases=changes,
                 caveat='Stationary painted-lane target; final hit is HP-capped at30. Nominal35 separately measured; N=1 successful combo.')
    lifecycles = []
    for name, prefix in [('high-target', 'ha'), ('armor', 'idle')]:
        _, rows, _ = runs[name]
        rs = next(r for r in rows if r['label'] == prefix+'-RS')
        start = rs['infos']['player_0']['frame']-rs['frames']; position = rs['infos']['player_0']['position']
        late = [r['infos']['player_0'] for r in rows if r['label'].startswith(prefix+'-')
                and r['infos']['player_0']['frame'] > start+500]
        takeoff = next(i for i in late if i['position'][1] > position[1]+.5)
        land = next(i for i in late if i['frame'] > takeoff['frame'] and math.dist(i['position'], position) < .1)
        lifecycles.append(dict(run=name,case=prefix,rs_before_frame=start,
            first_refill_ack_delta=next(i['frame']-start for i in late if i['special'] >= .999),
            return_first_Y_over_origin_plus_half=takeoff['frame']-start,
            return_first_within_point_one_of_origin=land['frame']-start,
            observed_air_window=land['frame']-takeoff['frame'],
            final_distance_to_origin=math.dist(late[-1]['position'],position),
            caveat='Observed position thresholds, not exact animation boundaries or control unlock; QS57AP.'))
    payload = dict(schema='inklab.d2.measurements.v1',date='2026-10-21',full_d2_passed=False,
                   inventory=inventory,discovery=discovery,range_trials=range_trials,statuses=statuses,mid_combo=combo,
                   lifecycles=lifecycles,
                   limits=['All frame counts are controlled presents unless explicitly native sample frames.',
                           'Native position updates are normally4 presents apart; do not turn first RPC observation into exact engine-transition time.',
                           'Default fixture loadout is57AP quick_super_jump, not gearless. No special_power_up.',
                           'Script completion is not scientific acceptance. Failed placement invalidates its dependent case.',
                           'No hitpoint/armor state is exposed: an HP-unchanged shot cannot establish invincibility.',
                           'No game resources or screenshots in this numerical report.'])
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    print(args.out,len(inventory),'runs',len(range_trials),'range trials',len(changes),'combo HP decreases')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=ROOT/'work/d2/measurements.json')
    main(p.parse_args())
