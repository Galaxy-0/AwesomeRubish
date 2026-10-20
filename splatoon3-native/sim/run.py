"""Offline policy compatibility harness. Runs Python workers, never a game."""
import argparse
from contextlib import ExitStack
import json
import math
from pathlib import Path
import time

from arena.config import PolicySpec
from arena.control_process import ControlProcess, OwnSpecial
from .engine import Simulator
from .parameters import ROOT, sha256


def run(policy_paths, stage_id=1, frames=10800, out=ROOT / 'work/sim/policy-run', *, motion_path=None, weapon_path=None,
        advanced_path=None, opening_path=None,paint_path=None,swap=False):
    specs = [PolicySpec.load(path) for path in policy_paths]
    out = Path(out).resolve()
    if ROOT / 'work' not in out.parents:
        raise ValueError('policy logs must stay under work/')
    out.mkdir(parents=True, exist_ok=True)
    from .motion import MotionModel
    from .weapon import WeaponModel
    from .advanced import AdvancedModel
    from .opening import OpeningModel
    from .paint_model import PaintModel
    env = Simulator(stage_id, loadouts=[s.loadout for s in specs], duration_frames=frames,
                    motion_model=MotionModel.load(motion_path) if motion_path else None,
                    weapon_model=WeaponModel.load(weapon_path) if weapon_path else None,
                    advanced_model=AdvancedModel.load(advanced_path) if advanced_path else None,
                    opening_model=OpeningModel.load(opening_path) if opening_path else None,
                    paint_model=PaintModel.load(paint_path) if paint_path else None,swap=swap)
    cadence = math.gcd(*(s.step_frames for s in specs))
    start = time.perf_counter()
    with ExitStack() as stack:
        workers = [stack.enter_context(ControlProcess(s.root, out / f'player-{i}.stderr.log', s.step_timeout))
                   for i, s in enumerate(specs)]
        actions = {}
        while not env.done:
            for i, (worker, spec) in enumerate(zip(workers, specs)):
                if env.frame % spec.step_frames == 0:
                    obs = env.typed_observation(i)
                    actions[f'player_{i}'] = worker.act(obs, OwnSpecial(f'player_{i}', env.frame, env.players[i].special))
            env.step(actions, min(cadence, frames - env.frame))
    seconds = time.perf_counter() - start
    result = dict(**env.info(), wall_seconds=seconds, frames_per_second=frames / seconds,
                  policy_sha256=[s.source_sha256 for s in specs], stage=stage_id,
                  model_sha256=dict(motion=sha256(motion_path) if motion_path else None,
                                    weapon=sha256(weapon_path) if weapon_path else None,
                                    advanced=sha256(advanced_path) if advanced_path else None,
                                    opening=sha256(opening_path) if opening_path else None,
                                    paint=sha256(paint_path) if paint_path else None),swap=bool(swap),
                  note='simulator outcome only; uncalibrated mechanics cannot establish native policy strength')
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('policies', type=Path, nargs=2)
    p.add_argument('--stage', type=int, choices=(1, 2, 3), default=1)
    p.add_argument('--frames', type=int, default=10800)
    p.add_argument('--out', type=Path, default=ROOT / 'work/sim/policy-run')
    p.add_argument('--motion-model', type=Path)
    p.add_argument('--weapon-model', type=Path)
    p.add_argument('--advanced-model', type=Path)
    p.add_argument('--opening-model',type=Path)
    p.add_argument('--paint-model',type=Path)
    p.add_argument('--swap',action='store_true')
    args = p.parse_args()
    print(json.dumps(run(args.policies,args.stage,args.frames,args.out,motion_path=args.motion_model,weapon_path=args.weapon_model,
                         advanced_path=args.advanced_model,opening_path=args.opening_model,paint_path=args.paint_model,swap=args.swap),indent=2))
