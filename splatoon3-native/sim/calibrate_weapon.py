"""Fit range HP intervals, recheck charge calibration, validate combat room."""
import json

import numpy as np

from .corpus import WORK
from .parameters import Parameters, ROOT, sha256
from .replay import a6_case, stats
from .report import a1
from .terrain import Terrain
from .weapon import WeaponModel


def hit_interval(raw):
    curve = raw['sampled_curves']['players']['player_1']
    previous_frame, previous_hp = raw['start_frame'], 1.
    for row in curve:
        frame, hp = row[0], row[7]
        if previous_hp-hp >= .29:
            return int(previous_frame+1), int(frame)
        previous_frame, previous_hp = frame, hp
    return None


def summarize(raw):
    target = raw['players']['player_1']
    interval = hit_interval(raw)
    events = target['simulated_damage']
    frame = events[0]['frame'] if events else None
    violation = (max(interval[0]-frame, 0, frame-interval[1]) if interval and frame is not None else None)
    return dict(case=raw['case'], position_rmse=target['position_world_units']['rmse'],
                native_hit_interval=interval, simulated_damage=events,
                first_sample_delay=target['first_direct_damage_delay_frames'], interval_violation=violation,
                ink=raw['players']['player_0']['ink_fraction'])


def timing(parameters, model):
    path = ROOT/'work/a6/timing-refine-20261019-125833-624062/result.json'
    result = json.loads(path.read_text())
    errors, legacy, rows = [], [], []
    for case in result['cases']:
        seen = set()
        full = case['hold_frames'] - (5 if case['before_form'] else 0) >= 21
        final = parameters.charge['InkConsumeFullCharge'] if full else parameters.swing['InkConsume']
        for info in case['history']:
            frame = info['position_sample_frame']
            if frame in seen or not info.get('ink_valid'):
                continue
            seen.add(frame)
            elapsed = frame-case['start_frame']
            if elapsed < 0: continue
            cost = (model.reserve(parameters, max(0, elapsed-(5 if case['before_form'] else 0)))
                    if frame < case['release_frame'] else final)
            predicted = 1-cost
            old = 1. if frame < case['release_frame'] else 1-final
            errors.append(abs(predicted-info['ink']))
            legacy.append(abs(old-info['ink']))
            rows.append([case['kind'], case['hold_frames'], int(elapsed), info['ink'], float(predicted), float(old)])
    return dict(source=str(path.relative_to(ROOT)), sha256=sha256(path), legacy=stats(legacy), fitted=stats(errors),
                curves=rows, note='Charge-curve construction/calibration recheck, not held-out validation; unique sample frames, no new native run.')


def main():
    parameters, terrain = Parameters.local(), Terrain.load(1)
    range_dir = ROOT/'work/a6/range-20261019-135543-208917'
    range_cases = json.loads((range_dir/'result.json').read_text())['cases']
    train = []
    for case in range_cases:
        raw = a6_case(range_dir, case['kind'], parameters=parameters, terrain=terrain, weapon_model=WeaponModel())
        (WORK/('weapon-train-'+case['kind']+'.json')).write_text(json.dumps(raw)+'\n')
        train.append(summarize(raw))
    losses = []
    for delay in range(13):
        terms = []
        for row in train:
            if row['native_hit_interval'] and row['simulated_damage']:
                low, high = row['native_hit_interval']
                predicted = row['simulated_damage'][0]['frame']+delay
                terms.append(max(low-predicted, 0, predicted-high)**2)
        losses.append(float(np.mean(terms)) if terms else 1e9)
    delay = int(np.argmin(losses))
    profile = dict(schema='sim.weapon.v2', damage_delay=delay, contact_muzzle_anchor=True,
                   sources={'range':sha256(range_dir/'result.json')}, loss_by_delay=losses,
                   interpretation='Effective peer HP delivery delay, fit to interval-censored samples; does not identify physical hit latency.',
                   contact_anchor='candidate inferred from A1: slash local offset relative to projectile muzzle, not foot origin')
    (WORK/'weapon.json').write_text(json.dumps(profile, indent=2)+'\n')
    model = WeaponModel(profile)
    validation = []
    for prefix in ('minimum-predecessor-damage', 'minimum-full-damage', 'emerge-full-damage'):
        raw = a6_case(ROOT/'work/a6/combat-20261019-131326-782403', prefix,
                      parameters=parameters, terrain=terrain, weapon_model=model)
        (WORK/('weapon-validation-'+prefix+'.json')).write_text(json.dumps(raw)+'\n')
        validation.append(summarize(raw))
    report = dict(schema='sim.weapon.comparison.v2', model=profile, train=train, validation=validation,
                  timing=timing(parameters, model), a1=a1(parameters, terrain, weapon_model=model),
                  limitations=['A1 is calibration of contact origin candidate, not independent validation.',
                               'Native skeleton/joint transform and physical/network latency remain unobserved.'])
    (WORK/'weapon-comparison.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='timing'}, indent=2))
    print('timing', json.dumps({k:v for k,v in report['timing'].items() if k!='curves'}))


if __name__ == '__main__':
    main()
