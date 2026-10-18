#!/usr/bin/env python3
"""Exercise the private native adapter on a real saved STEP trace; not A3 acceptance."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arena.native_referee import NativeRefereeAdapter
from arena.policy import encode_policy
from arena.visibility import PolicyProjector


def main(path):
    path = path.resolve()
    if not path.is_relative_to(ROOT/'work'):
        raise ValueError('native diagnostic traces belong under ignored work/')
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    agents = tuple(rows[0]['infos'])
    if len(agents) != 2:
        raise ValueError('this diagnostic expects the two-player Stamper trace')
    # Begin at the first recorded common barrier. Each host has a different
    # absolute origin; relative deltas are all that the adapter can compare.
    adapter = NativeRefereeAdapter(path.parent.name, rows[0]['infos'],
                                   {p: 8000 for p in agents}, dict(zip(agents, (0, 1))))
    projector = PolicyProjector(path.parent.name)
    report = dict(diagnostic_completed=False, full_a3_passed=False, barriers=0,
                  private_positions=0, private_hp=0, observer_public_status=0,
                  policy_visible_enemies=0, policy_views=0,
                  unavailable=['validated_submerged', 'native_camera_fov_los',
                               'live_paint_grid', 'attributed_knockdowns', 'policy_process'])
    with (path.parent/'policy-boundary-replay.jsonl').open('wb') as output:
        for row in rows:
            truth = adapter.snapshot(row['infos'])
            report['barriers'] += 1
            report['private_positions'] += sum(p.position is not None for p in truth.players)
            report['private_hp'] += sum(p.hp is not None for p in truth.players)
            report['observer_public_status'] += len(truth.public_status)
            for agent in agents:
                obs = projector.observe(truth, agent)
                report['policy_views'] += 1
                report['policy_visible_enemies'] += sum(e.visible for e in obs.enemies)
                output.write(encode_policy(obs))
    report['diagnostic_completed'] = True
    target = path.parent/'policy-boundary-replay.json'
    target.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(report=str(target), **report), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('steps', type=Path)
    main(parser.parse_args().steps)
