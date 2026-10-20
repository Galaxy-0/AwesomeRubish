"""Fit motion from whole-session training splits; never fit on T1 test family."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

from .corpus import Trace, WORK
from .parameters import ROOT, sha256

MODES = ('human', 'charge', 'recovery', 'squid_own', 'squid_dry', 'air')


def wrapped(x):
    return np.arctan2(np.sin(x), np.cos(x))


def collect(corpus):
    groups = {'train': [], 'validation': [], 'test': []}
    for entry in corpus['games']:
        trace = Trace(entry)
        for role in range(2):
            ts = trace.samples[role]
            if len(ts) < 4:
                continue
            a, b, c = ts[:-2], ts[1:-1], ts[2:]
            s0, s1, s2 = (trace.states[t, role] for t in (a, b, c))
            dt0, dt1 = b-a, c-b
            v0 = (s1[:, :3]-s0[:, :3])/dt0[:, None]
            v1 = (s2[:, :3]-s1[:, :3])/dt1[:, None]
            actions = trace.actions[:, role]
            prefix = np.vstack([np.zeros(13), np.cumsum(actions, axis=0, dtype=np.float64)])
            avg = (prefix[c]-prefix[b])/dt1[:, None]
            current = actions[np.minimum(b, trace.frames-1)]
            # Mode inferred from observed form/contact + PAST action history.
            recent = np.zeros(trace.frames, int)
            held = np.zeros(trace.frames, int)
            last_release, run = -1000, 0
            for frame, row in enumerate(actions):
                if frame and actions[frame-1, 7] and not row[7]:
                    last_release = frame
                run = run+1 if row[7] else 0
                held[frame], recent[frame] = run, frame-last_release
            mode = np.where(s1[:, 8] == 1, np.where(s1[:, 9] == 0, 3, 4),
                            np.where(held[b] >= 5, 1, np.where(recent[b] < 30, 2, 0)))
            mode[s1[:, 9] == 5] = 5
            keep = ((dt0 <= 16) & (dt1 <= 16) & (dt0 >= 1) & (dt1 >= 1) &
                    np.isfinite(s0[:, :11]).all(axis=1) & np.isfinite(s1[:, :11]).all(axis=1) &
                    np.isfinite(s2[:, :11]).all(axis=1) &
                    (s0[:, 10] == 1) & (s1[:, 10] == 1) & (s2[:, 10] == 1) &
                    (s0[:, 1] < 20) & (s1[:, 1] < 20) & (s2[:, 1] < 20) &
                    (np.linalg.norm(v0, axis=1) < .8) & (np.linalg.norm(v1, axis=1) < .8) &
                    (s1[:, 8] == s2[:, 8]))
            # [mode, dt, stick xy, v0 xyz, v1 xyz, yaw0, yaw1,
            #  heading0/1, avg right/gyro/pitch, ground0/1, HPdelta, jump]
            matrix = np.column_stack([mode, dt1, avg[:, :2], v0, v1,
                s1[:, 4], s2[:, 4], s1[:, 3], s2[:, 3], avg[:, 2], avg[:, 6],
                avg[:, 4], s1[:, 5], s2[:, 5], s1[:, 9], s2[:, 9],
                s2[:, 6]-s1[:, 6], avg[:, 11],
                np.max(np.abs(avg[:, :2]-current[:, :2]), axis=1),
                s1[:, 1], s2[:, 1]])
            groups[entry['split']].append(matrix[keep])
    return {k: np.concatenate(v) if v else np.empty((0, 26)) for k, v in groups.items()}


def response(sticks, deadzone, exponent):
    # Per-axis deadzone, then unit circle. This matches the native diagonal
    # axis behavior observed during A4, without importing native controller code.
    x = np.sign(sticks) * (np.maximum(0., np.abs(sticks)-deadzone)/(1-deadzone))**exponent
    return x / np.maximum(1., np.linalg.norm(x, axis=-1, keepdims=True))


def fit(data):
    train = data['train']
    model = dict(schema='sim.motion.v2', modes={}, camera={}, jump={}, source='historical session train split')
    # Stable straight, unchanged-stick, no-HP-drop, ground-only segments.
    stable = ((np.abs(wrapped(train[:, 11]-train[:, 10])) < .04) &
              (np.linalg.norm(train[:, 7:10]-train[:, 4:7], axis=1) < .012) &
              (train[:, 23] < .01) & (train[:, 21] >= -.002) & (np.abs(train[:, 8]) < .035))
    for mode, name in enumerate(MODES):
        rows = train[stable & (train[:, 0] == mode)]
        speed = np.linalg.norm(rows[:, [7, 9]], axis=1)
        # Median of per-stick-bin 85th percentiles reduces stationary walls
        # dominating the estimated free-space speed. This is an upper envelope.
        bins = []
        magnitude = np.linalg.norm(rows[:, 2:4], axis=1)
        for lo in np.arange(.2, 1., .1):
            keep = (magnitude >= lo) & (magnitude < lo+.10001) & (speed > .005)
            if keep.sum() >= 30:
                bins.append((np.median(rows[keep, 2:4], axis=0), np.quantile(speed[keep], .85), int(keep.sum())))
        default_speed = (.096, .0384, .06, .192, .048, .096)[mode]
        best = None
        for deadzone in (0., .15, .25, .35, .4, .45, .5):
            for exponent in (.7, 1., 1.4, 2.):
                if len(bins) < 2:
                    continue
                # Binning by norm can mix stick directions. Use magnitude
                # response distribution within each actual sample bin instead.
                rs, ys = [], []
                for lo in np.arange(.2, 1., .1):
                    keep = (magnitude >= lo) & (magnitude < lo+.10001) & (speed > .005)
                    if keep.sum() >= 30:
                        rs.append(float(np.median(np.linalg.norm(response(rows[keep, 2:4], deadzone, exponent), axis=1))))
                        ys.append(float(np.quantile(speed[keep], .85)))
                r, y = np.array(rs), np.array(ys)
                fitted_speed = float(np.clip(np.dot(r, y)/max(np.dot(r, r), 1e-9), .02, .35))
                loss = float(np.mean((fitted_speed*r-y)**2))
                if best is None or loss < best[0]:
                    best = (loss, fitted_speed, deadzone, exponent)
        if best is None:
            # A single mostly-stationary input regime cannot separate free
            # speed, deadzone and walls. Retain independent prior, not the
            # observed obstructed-speed percentile as a fabricated maximum.
            best = (None, default_speed, 0., 1.)
        model['modes'][name] = dict(speed=best[1], deadzone=best[2], exponent=best[3],
                                    stable_segments=len(rows), stick_bins=len(bins), envelope_loss=best[0],
                                    acceleration=.01, braking=.02,
                                    status='fitted upper envelope' if best[0] is not None else 'sparse fallback')
    # Fit acceleration/braking on displacement transitions by vectorized grid
    # integration. Starting velocity is previous observed interval average;
    # its half-sample lag is retained as an explicit uncertainty.
    for mode, name in enumerate(MODES):
        rows = train[(train[:, 0] == mode) & (train[:, 23] < .01) &
                     (np.abs(wrapped(train[:, 11]-train[:, 10])) < .06) &
                     (train[:, 21] >= -.002) & (np.abs(train[:, 8]) < .04)]
        if len(rows) > 12000:
            rows = rows[np.linspace(0, len(rows)-1, 12000).astype(int)]
        params = model['modes'][name]
        stick = response(rows[:, 2:4], params['deadzone'], params['exponent'])
        yaw = rows[:, 10]
        target = np.column_stack([-stick[:, 0]*np.cos(yaw)+stick[:, 1]*np.sin(yaw),
                                   stick[:, 0]*np.sin(yaw)+stick[:, 1]*np.cos(yaw)])*params['speed']
        initial, observed = rows[:, [4, 6]], rows[:, [7, 9]]
        best = None
        for accel in (.003, .005, .008, .01, .015, .024, .04):
            for brake in (.005, .01, .02, .04, .08):
                v = initial.copy(); displacement = np.zeros_like(v)
                for frame in range(16):
                    active = frame < rows[:, 1]
                    decelerating = np.linalg.norm(target, axis=1) < np.linalg.norm(v, axis=1)
                    rate = np.where(decelerating, brake, accel)
                    v += np.clip(target-v, -rate[:, None], rate[:, None])
                    displacement += v*active[:, None]
                residual = np.linalg.norm(displacement/rows[:, 1, None]-observed, axis=1)
                # Robust losses tolerate residual wall collisions; no future
                # samples or test rows enter parameter selection.
                loss = float(np.mean(np.minimum(residual, .08)**2)) if len(rows) else float('inf')
                if best is None or loss < best[0]:
                    best = (loss, accel, brake)
        params.update(acceleration=best[1], braking=best[2], transition_segments=len(rows))
    turn = train[(np.abs(wrapped(train[:, 11]-train[:, 10])) < 1.2) & (train[:, 0] != 5)]
    y = wrapped(turn[:, 11]-turn[:, 10])/turn[:, 1]
    best = None
    for deadzone in (0., .2, .3, .4, .5, .6):
        x = np.sign(turn[:, 14])*np.maximum(0., np.abs(turn[:, 14])-deadzone)/(1-deadzone)
        design = np.column_stack([-x, turn[:, 15]])
        nonzero = np.linalg.norm(design, axis=1) > .001
        beta = np.linalg.lstsq(design[nonzero], y[nonzero], rcond=None)[0]
        gain = float(np.clip(beta[0], .001, .15))
        gyro = float(np.clip(beta[1], .01, .5)) if (np.abs(turn[:, 15]) > .01).sum() > 100 else .25062904
        loss = float(np.mean(np.minimum(np.abs(design@np.array([gain, gyro])-y), .1)))
        if best is None or loss < best[0]:
            best = (loss, deadzone, gain, gyro)
    model['camera'] = dict(stick_deadzone=best[1], stick_gain=best[2], gyro_gain=best[3],
                           training_mae=best[0], segments=len(turn), pitch_gain=.12, heading_rate=.15)
    pitch_x = turn[:, 16]
    pitch_y = (turn[:, 18]-turn[:, 17])/turn[:, 1]
    keep = (np.abs(pitch_x) > .001) & (np.abs(turn[:, 17]) < .8) & (np.abs(turn[:, 18]) < .8)
    if keep.sum() >= 100:
        model['camera']['pitch_gain'] = float(np.clip(-np.dot(pitch_x[keep], pitch_y[keep])/np.dot(pitch_x[keep], pitch_x[keep]), .01, 1.))
    air = train[(train[:, 19] == 5) & (train[:, 20] == 5) & (train[:, 21] >= -.002)]
    gravity = -(air[:, 8]-air[:, 5])/air[:, 1] if len(air) else np.array([])
    valid = gravity[(gravity > .001) & (gravity < .04)]
    model['jump'] = dict(gravity=float(np.median(valid)) if len(valid) >= 30 else .008,
                         jump_speed=.12, air_segments=len(air), gravity_samples=len(valid),
                         note='gravity from air interval derivative; impulse from ground-to-air B edges')
    launches = train[(train[:, 19] != 5) & (train[:, 20] == 5) & (train[:, 22] > .01) &
                     (train[:, 21] >= -.002) & (train[:, 8] > .01)]
    if len(launches) >= 30:
        impulse = launches[:, 8] + model['jump']['gravity']*launches[:, 1]/2
        model['jump']['jump_speed'] = float(np.clip(np.median(impulse), .06, .2))
        model['jump']['launch_segments'] = len(launches)
    ground = train[(train[:, 19] != 5) & (train[:, 20] != 5)]
    moving = ground[np.linalg.norm(ground[:, [7, 9]], axis=1) > .01]
    slope = np.abs(moving[:, 8])/np.maximum(np.linalg.norm(moving[:, [7, 9]], axis=1), 1e-9)
    model['terrain_diagnostics'] = dict(ground_segments=len(ground), moving_segments=len(moving),
        observed_dy_over_dxz_quantiles=np.quantile(slope, [.5, .9, .95, .99]).tolist(),
        support_normal_threshold=.7, step_height=.2,
        note='A4 geometry thresholds retained; sparse sample dy cannot distinguish one step from a ramp. No learned material-specific step claim.')
    model['unidentified'] = ['grounded human own/enemy/unpainted classification: native paint absent',
                             'gear AP curves: most old snapshots unavailable', 'full wall climbing / roll / surge',
                             'step/slope material-specific limits: test geometrically, do not infer from blocked speed']
    return model


def validation_select(model, data):
    """Select mode/camera improvements on validation, never T1 test results."""
    from .motion import MotionModel
    rows = data['validation']
    report = {}
    baseline = dict(model)
    baseline['modes'] = {name: dict(speed=speed, deadzone=0., exponent=1., acceleration=.024, braking=.024)
                         for name, speed in zip(MODES, (.096, .0384, .06, .192, .048, .096))}
    for mode, name in enumerate(MODES):
        r = rows[(rows[:, 0] == mode) & (rows[:, 23] < .01) &
                 (np.abs(wrapped(rows[:, 11]-rows[:, 10])) < .06) & (np.abs(rows[:, 8]) < .04)]
        errors = []
        for candidate in (baseline, model):
            m = MotionModel(candidate)
            v = r[:, [4, 6]].copy(); displacement = np.zeros_like(v)
            for frame in range(16):
                v, _ = m.batch_advance(v, r[:, 2:4], r[:, 10], np.full(len(r), mode))
                displacement += v*(frame < r[:, 1])[:, None]
            error = np.linalg.norm(displacement/r[:, 1, None]-r[:, [7, 9]], axis=1)
            errors.append(dict(samples=len(r), mae=float(np.mean(error)) if len(r) else None,
                               p95=float(np.quantile(error, .95)) if len(r) else None))
        selected = bool(len(r) >= 30 and errors[1]['mae'] < errors[0]['mae'])
        report[name] = dict(baseline=errors[0], fitted=errors[1], selected=selected)
        if not selected:
            model['modes'][name].update(baseline['modes'][name])
            model['modes'][name]['status'] += '; validation retained prior'
    y = wrapped(rows[:, 11]-rows[:, 10])/rows[:, 1]
    c = model['camera']
    x = np.sign(rows[:, 14])*np.maximum(0., np.abs(rows[:, 14])-c['stick_deadzone'])/(1-c['stick_deadzone'])
    fitted = -x*c['stick_gain']+rows[:, 15]*c['gyro_gain']
    previous = -rows[:, 14]*.018+rows[:, 15]*.25062904
    report['camera_yaw'] = dict(baseline_mae=float(np.mean(abs(previous-y))), fitted_mae=float(np.mean(abs(fitted-y))))
    if report['camera_yaw']['fitted_mae'] >= report['camera_yaw']['baseline_mae']:
        c.update(stick_deadzone=0., stick_gain=.018, gyro_gain=.25062904)
    model['validation_selection'] = report
    return model


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=WORK)
    args = p.parse_args()
    if ROOT / 'work' not in args.out.resolve().parents:
        p.error('fit outputs must stay under work/')
    corpus_path = args.out / 'corpus.json'
    corpus = json.loads(corpus_path.read_text())
    data = collect(corpus)
    np.savez_compressed(args.out / 'transitions.npz', **data)
    model = validation_select(fit(data), data)
    model['split_segments'] = {k: len(v) for k, v in data.items()}
    model['corpus_sha256'] = sha256(corpus_path)
    model['fit_source_sha256'] = sha256(__file__)
    (args.out / 'motion.json').write_text(json.dumps(model, indent=2) + '\n')
    print(json.dumps(model, indent=2))


if __name__ == '__main__':
    main()
