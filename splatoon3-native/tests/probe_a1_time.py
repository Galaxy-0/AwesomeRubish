#!/usr/bin/env python3
"""Bounded native time diagnosis; this probe alone never accepts full A1."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rl import NativeParallelEnv


def neutral():
    return dict(sticks=np.zeros(4, np.float32), gyro=np.zeros(3, np.float32), buttons=np.zeros(6, np.int8))


def sample_hosts(session, out):
    """Capture every host before cleanup, including peers whose ACK was not read."""
    results = []
    for player, process, _ in session.hosts:
        target = out / f'sample-player-{player}.txt'
        try:
            completed = subprocess.run(['/usr/bin/sample', str(process.pid), '1', '10', '-file', str(target)],
                                       capture_output=True, text=True, timeout=10)
            results.append(dict(player=player, pid=process.pid, returncode=completed.returncode,
                                stdout=completed.stdout, stderr=completed.stderr, path=str(target)))
        except Exception as error:
            results.append(dict(player=player, pid=process.pid, error=repr(error)))
    (out / 'samples.json').write_text(json.dumps(results, indent=2) + '\n')


def main(args):
    out = ROOT / 'work/tests' / datetime.datetime.now().strftime(f'a1-time-{args.clock_mode}-%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True)
    result = dict(probe_completed=False, full_a1_passed=False, clock_mode=args.clock_mode, errors=[], artifacts=str(out))
    env = NativeParallelEnv(players=2, weapons=[8000, 8000], clock_mode=args.clock_mode,
                            frame_skip=15, timeout=args.timeout, step_timeout=30, reward_fn=None)
    rows = []
    log = (out / 'steps.jsonl').open('w')
    try:
        _, infos = env.reset()
        result['session'] = str(env.session.out)
        rows.append(dict(step=-1, wall=time.monotonic(), infos=infos))
        log.write(json.dumps(rows[-1]) + '\n'); log.flush()
        for n in range(80):
            env.frame_skip = (1, 7, 31)[n % 3] if 20 <= n < 32 else 15
            delay = .25 if n % 7 == 0 else 0
            if delay: time.sleep(delay)
            actions = {agent: neutral() for agent in env.agents}
            label = 'neutral'
            if 40 <= n < 48:
                actions['player_0']['sticks'][1] = 1; label = 'walk'
            if 56 <= n < 64:
                actions['player_0']['buttons'][0] = 1; label = 'fire'
            if 64 <= n < 76:
                actions['player_0']['buttons'][1] = 1; label = 'recover'
            _, _, _, truncations, infos = env.step(actions)
            rows.append(dict(step=n, wall=time.monotonic(), label=label, frames=env.frame_skip,
                             policy_delay=delay, infos=infos,
                             actions={a: {k: v.tolist() for k, v in action.items()} for a, action in actions.items()}))
            log.write(json.dumps(rows[-1]) + '\n'); log.flush()
            if any(truncations.values()): raise TimeoutError('session deadline')
            if not env.agents: raise AssertionError('probe ended before measurement window')
            if n % 10 == 0:
                print('A1', n, label, {a: {k: i[k] for k in ('frame', 'remaining_time', 'position')} for a, i in infos.items()}, flush=True)
        result['measurements'] = {}
        # Exclude launch animation and use native timer sample frames to avoid
        # mistaking a stale HUD sample for a change in physics time.
        for agent in env.possible_agents:
            valid = [r for r in rows if r['step'] >= 20 and r['infos'][agent]['time_valid']]
            if len(valid) < 20: raise AssertionError('insufficient valid native timer samples')
            first, last = valid[0], valid[-1]
            a, b = first['infos'][agent], last['infos'][agent]
            frames = b['time_sample_frame'] - a['time_sample_frame']
            elapsed = a['remaining_time'] - b['remaining_time']
            nominal = frames / 60
            ratio = elapsed / nominal
            result['measurements'][agent] = dict(presents=frames, hud_seconds=elapsed,
                nominal_seconds=nominal, hud_to_60hz_ratio=ratio, wall_seconds=last['wall']-first['wall'],
                fixed60_candidate=abs(elapsed-nominal) <= max(.05, nominal*.02),
                max_displacement=max(float(np.linalg.norm(np.asarray(r['infos'][agent]['position'])-a['position']))
                                     for r in valid if r['infos'][agent]['position_valid']))
        result['probe_completed'] = True
    except BaseException as error:
        result['errors'].append(repr(error)); result['traceback'] = traceback.format_exc()
        if env.session: sample_hosts(env.session, out)
    finally:
        try: env.close()
        except BaseException as error: result['errors'].append('cleanup: '+repr(error))
        log.close()
        result['completed_steps'] = max(0, len(rows)-1)
        (out / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result, indent=2), flush=True)
    return 0 if result['probe_completed'] and not result['errors'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clock-mode', choices=('realtime', 'fixed60'), default='realtime')
    parser.add_argument('--timeout', type=float, default=1800)
    raise SystemExit(main(parser.parse_args()))
