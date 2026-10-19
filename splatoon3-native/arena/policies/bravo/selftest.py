"""Single-room, one-game-per-map smoke using the arena's unchanged run_match.

The standard A5 CLI requires swapped pairs; this small policy-local driver
checks the three-map BO3 shape without spending six further rooms. It never
loads another author's policy. No retry is automatic; every room is budgeted.
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from arena.config import PolicySpec
from arena.runner import run_match, write_json_atomic


def wait_idle(enabled):
    if not enabled:
        return
    last = -100
    while True:
        found = subprocess.run(['pgrep', '-x', 'dmhost'], capture_output=True, text=True)
        if found.returncode == 1:
            return
        if found.returncode != 0:
            raise RuntimeError('cannot check native room admission')
        if time.monotonic()-last >= 30:
            print(json.dumps(dict(waiting_for_idle=True,
                                  native_hosts=len(found.stdout.splitlines()))), flush=True)
            last = time.monotonic()
        time.sleep(5)


def main(args):
    if args.parallel != 1 or len(args.stages) > 5:
        raise ValueError('one room; at most five additional attempts')
    if os.environ.get('DM_TEST_SPECIAL'):
        raise RuntimeError('test special override forbidden in matches')
    wait_idle(args.wait_idle)
    if args.proficiency:
        # Reuse the public one-room fixture unchanged. This verifies the
        # combat branch when the weak map baseline never enters weapon range.
        out = ROOT/'work/a6'/datetime.datetime.now().strftime('bravo-v1-stationary-%Y%m%d-%H%M%S-%f.json')
        print(json.dumps(dict(proficiency_out=str(out), parallel=1, repeats=1)), flush=True)
        return subprocess.call([sys.executable, str(ROOT/'tests/benchmark_a6.py'),
                                '--policy', str(Path(__file__).parent),
                                '--scenario', 'stationary', '--repeats', '1',
                                '--out', str(out), '--timeout', str(args.timeout)])
    paths = [Path(__file__).parent, ROOT/'arena/policies/high-ground']
    sources = [PolicySpec.load(p).source_sha256 for p in paths]
    # Freeze only allowed runtime and the participating sources. Do not open
    # the unrelated private policy that the global A5 freeze also includes.
    files = [ROOT/'upstream/dm/host/dmhost']
    files += list((ROOT/'arena').glob('*.py'))
    files += list((ROOT/'arena/lib').glob('*.py'))
    files += list((ROOT/'rl').glob('*.py'))
    files += [ROOT/f'work/arena/maps/{name}/{filename}'
              for name in ('Yunohana', 'District00', 'Yagara')
              for filename in ('navigation.json', 'sight.npz')]
    frozen = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    out = ROOT/'work/arena'/datetime.datetime.now().strftime('bravo-v1-smoke-%Y%m%d-%H%M%S-%f')
    out.mkdir()
    write_json_atomic(out/'runtime-sha256.json', frozen)
    report = dict(passed=False, diagnostic_only=True, parallel_games=1,
                  policies=['bravo', 'high-ground'], source_hashes=sources,
                  matches=[], errors=[], artifacts=str(out))
    print(json.dumps(dict(artifacts=str(out), stages=args.stages, parallel=1)), flush=True)
    for n, stage in enumerate(args.stages):
        wait_idle(args.wait_idle)
        task = dict(round=n, attempt=0, stage=stage,
                    roles=[0, 1] if n % 2 == 0 else [1, 0],
                    policy_paths=[str(p) for p in paths], timeout=args.timeout,
                    out=str(out/f'game-{n:03d}-stage-{stage}'))
        result = run_match(task)
        report['matches'].append(result)
        write_json_atomic(out/'result.json', report)
        print(json.dumps({k: result.get(k) for k in
                          ('round', 'stage', 'passed', 'outcome', 'score_by_role', 'errors')}), flush=True)
        if not result['passed']:
            report['errors'].append('room failed; no automatic retry')
            break
    changed = [str(p) for p, sha in frozen.items()
               if hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha]
    if changed:
        report['errors'].append(dict(runtime_changed=changed))
    if [PolicySpec.load(p).source_sha256 for p in paths] != sources:
        report['errors'].append('participating policy source changed')
    report['passed'] = len(report['matches']) == len(args.stages) and not report['errors']
    report['wins'] = sum(m.get('outcome') == 'a' for m in report['matches'] if m['passed'])
    report['losses'] = sum(m.get('outcome') == 'b' for m in report['matches'] if m['passed'])
    write_json_atomic(out/'result.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'matches'}), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parallel', type=int, choices=(1,), default=1)
    parser.add_argument('--stages', type=int, choices=(1, 2, 3), nargs='+', default=[1, 2, 3])
    parser.add_argument('--timeout', type=float, default=7200)
    parser.add_argument('--wait-idle', action='store_true', help='wait for other native rooms to exit before each room')
    parser.add_argument('--proficiency', action='store_true', help='one public stationary fixture, one repeat; no map games')
    raise SystemExit(main(parser.parse_args()))
