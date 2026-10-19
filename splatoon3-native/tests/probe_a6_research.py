#!/usr/bin/env python3
"""One-room native A6 research. No milestone acceptance or frozen-file writes."""
import argparse
import datetime
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'arena/lib'))
from rl import NativeParallelEnv
from rl.loadout import uniform_loadout
from arena.referee_api import RefereeAPI
from arena.policy import encode_policy
from atlas import MapAtlas
from skills import Skills, aim_at, neutral
from probe_a1_time import sample_hosts

MANIFEST = ROOT / 'work/arena/tournament-20261019-113138-347725/runtime-sha256.json'


def freeze_check():
    frozen = json.loads(MANIFEST.read_text())
    bad = [p for p, sha in frozen.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha]
    if bad:
        raise AssertionError('T1 frozen files changed: ' + repr(bad))
    return dict(files=len(frozen), mismatches=bad)


def main(args):
    out = ROOT / 'work/a6' / datetime.datetime.now().strftime('research-%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True)
    result = dict(probe_completed=False, full_a6_passed=False, errors=[], trials=[], artifacts=str(out))
    result['freeze_before'] = freeze_check()
    paths = [Path(__file__).resolve(), ROOT / 'tools/research_a6.py']
    result['code_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    env = NativeParallelEnv(players=2, stage_id=1, weapons=[8000, 8000],
                            loadouts=[uniform_loadout(), uniform_loadout()], frame_skip=6,
                            reward_fn=None, timeout=args.timeout, step_timeout=150, state_dump=True)
    stream = (out / 'steps.jsonl').open('w')
    api = None
    origins = {}
    count = 0
    atlas = MapAtlas.load(1)
    duel_poses = None

    def save():
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')

    def actions():
        return {a: neutral() for a in env.possible_agents}

    def obs(n):
        return json.loads(encode_policy(api.policy_observation(f'player_{n}')))

    def info(n):
        return env.process_infos[f'player_{n}']

    def step(a, label, frames=6):
        nonlocal count
        typed = {p: {k: np.asarray(v, dtype=np.int8 if k == 'buttons' else np.float32)
                     for k, v in action.items()} for p, action in a.items()}
        env.frame_skip = frames
        _, _, _, truncated, infos = env.step(typed)
        if any(truncated.values()):
            raise TimeoutError('A6 research deadline')
        for p, i in infos.items():
            if i['phase'] != 1:
                raise AssertionError('A6 research exceeded normal match duration')
            elapsed = i['frame'] - origins[p]['frame']
            if i['guest_time_ns'] - origins[p]['guest_time_ns'] != elapsed * 1000000000 // 60:
                raise AssertionError('fixed60 drift')
        api.update(infos)
        count += 1
        stream.write(json.dumps(dict(step=count, label=label, frames=frames, actions=a, infos=infos)) + '\n')
        stream.flush()
        return infos

    def capture(label):
        for p, observation in env.observations.items():
            Image.fromarray(observation['pixels']).save(out / f'{label}-{p}.png')

    def align(n, target, label):
        stable = 0
        for _ in range(160):
            r = aim_at(obs(n), target)
            stable = stable + 1 if r.done else 0
            if stable >= 3:
                return
            a = actions()
            a[f'player_{n}'] = r.action
            step(a, label, 1)
            step(actions(), label + '-sample', 10)
        raise AssertionError('A6 aim did not converge')

    def navigate(goals, label):
        controllers = {n: Skills(atlas) for n in goals}
        for _ in range(500):
            a = actions()
            done = True
            for n, target in goals.items():
                r = controllers[n].move_to(obs(n), target)
                if r.status == 'blocked':
                    raise AssertionError(f'{label}: blocked at {info(n)["position"]}')
                if not r.done:
                    done = False
                    a[f'player_{n}'] = r.action
            if done:
                step(actions(), label + '-settle', 30)
                return
            step(a, label)
        raise AssertionError(label + ': navigation cap')

    def paint_floor(n):
        p = info(n)['position']
        align(n, (p[0], p[1], p[2] + 1.5), f'floor-{n}-aim')
        for _ in range(4):
            a = actions()
            a[f'player_{n}']['buttons'][0] = 1
            step(a, f'floor-{n}-press', 1)
            step(actions(), f'floor-{n}-release', 29)

    def restore_pose(n, goal, label):
        # Native hits move the target even after the first HP packet. Return
        # with ordinary inputs before repainting/healing, as in accepted A4.
        for _ in range(60):
            own = obs(n)['own']
            p = own['position']
            distance = math.dist(p, goal)
            if distance < .12:
                return
            dx, dz = goal[0] - p[0], goal[2] - p[2]
            yaw = own['view_yaw']
            x = -dx * math.cos(yaw) + dz * math.sin(yaw)
            y = dx * math.sin(yaw) + dz * math.cos(yaw)
            length = max(.001, math.hypot(x, y))
            a = actions()
            a[f'player_{n}']['sticks'][:2] = [.85 * x / length, .85 * y / length]
            # One-frame pulses cover only ~.0113 world units in this native
            # setup. Use three frames outside .3; retain the precise pulse
            # near the unchanged .12 arrival radius.
            step(a, label, 3 if distance > .3 else 1)
            step(actions(), label + '-sample', 10)
        raise AssertionError('could not restore native duel pose')

    def heal(label):
        step(actions(), label + '-knockback-settle', 60)
        for n, goal in enumerate(duel_poses):
            restore_pose(n, goal, label + '-restore')
        # Enemy ink and knockback can invalidate the target's previous patch.
        # Fresh native paint, not a guessed ZL input, establishes the reset.
        paint_floor(1)
        a = actions()
        for p in a:
            a[p]['buttons'][1] = 1
        step(a, label, 240)
        step(actions(), label + '-surface', 12)
        if not all(i['alive_valid'] and i['alive'] and i['hp_valid'] and i['hp'] > .999
                   for i in env.process_infos.values()):
            raise AssertionError('trial did not start with two healthy native players')

    def trial(label, segments):
        heal(label + '-heal')
        q = info(1)['position']
        align(0, (q[0], q[1] + .7, q[2]), label + '-aim')
        before = env.process_infos
        samples = []
        for frames, flags in segments:
            a = actions()
            for button in flags:
                a['player_0']['buttons'][button] = 1
            samples.append(step(a, label, frames))
        for _ in range(12):
            samples.append(step(actions(), label + '-observe', 3))
        valid_hp = [i['player_1']['hp'] for i in samples if i['player_1']['hp_valid']]
        t = dict(label=label, segments=segments, before=before, after=env.process_infos,
                 target_hp_loss=before['player_1']['hp'] - min(valid_hp),
                 ink_delta=before['player_0']['ink'] - info(0)['ink'],
                 positions=[before['player_0']['position'], before['player_1']['position']],
                 segment_feedback=[dict(frame=i['player_0']['frame'],
                                        motion=i['player_0'].get('referee_motion'),
                                        ink=i['player_0']['ink'], hp_target=i['player_1']['hp'])
                                   for i in samples])
        result['trials'].append(t)
        capture(label)
        save()
        print(json.dumps({k: t[k] for k in ('label', 'target_hp_loss', 'ink_delta', 'positions', 'segment_feedback')}), flush=True)
        return t

    try:
        _, origins = env.reset()
        result['session'] = str(env.session.out)
        result['owned_pids'] = [p.pid for _, p, _ in env.session.hosts]
        api = RefereeAPI(out.name, origins, dict.fromkeys(env.possible_agents, 8000),
                         dict(zip(env.possible_agents, (0, 1))),
                         ROOT / 'work/arena/maps/Yunohana/sight.npz', stage_id=1)
        for _ in range(30):
            step(actions(), 'warmup', 15)
        navigate({0: (8., 3., 8.), 1: (14., 3., 8.)}, 'duel-setup')
        duel_poses = [tuple(info(n)['position']) for n in (0, 1)]
        for n in (0, 1):
            paint_floor(n)
        capture('duel-setup')
        # Long-held reference must produce the native vertical damage before
        # interpreting a failed stored-charge trial as weapon behavior.
        trial('light', [(1, [0]), (1, [])])
        trial('charged-reference', [(60, [0]), (1, [])])
        trial('charged-dive-held', [(60, [0]), (18, [0, 1]), (1, [0]), (1, [])])
        trial('charged-dive-released', [(60, [0]), (18, [1]), (1, [])])
        result['probe_completed'] = True
    except BaseException as error:
        result['errors'].append(repr(error))
        result['traceback'] = traceback.format_exc()
        if env.session:
            capture('failure')
            sample_hosts(env.session, out)
    finally:
        try:
            env.close()
        except BaseException as error:
            result['errors'].append('cleanup: ' + repr(error))
        stream.close()
        result['steps'] = count
        result['freeze_after'] = freeze_check()
        result['probe_completed'] = result['probe_completed'] and not result['errors']
        save()
    print(json.dumps(dict(artifacts=str(out), probe_completed=result['probe_completed'], errors=result['errors'])), flush=True)
    return 0 if result['probe_completed'] else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--timeout', type=float, default=3000)
    raise SystemExit(main(p.parse_args()))
