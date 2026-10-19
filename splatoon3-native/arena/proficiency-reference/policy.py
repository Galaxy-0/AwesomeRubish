"""Public benchmark reference: predictive full/light fire, no map tactics."""
from skills import neutral
from stamper import FULL_CHARGE_FRAMES, PredictiveAim, charge_slash

aim = PredictiveAim(max_lead_frames=60)
plan = None
match = None


def act(obs):
    global plan, match
    if match != obs['match_id']:
        plan = None
        match = obs['match_id']
    if plan is not None:
        result = plan.tick(obs)
        if not result.done:
            enemy = next((e for e in obs['enemies'] if e['visible']), None)
            if enemy is not None:
                aim.windup = max(0, FULL_CHARGE_FRAMES-(obs['frame']-plan.start))+6
                tracking = aim.aim(obs, enemy['public']['player_id'], fast=True)
                if tracking.status != 'target_unavailable':
                    result.action['sticks'][2:] = tracking.action['sticks'][2:]
                    result.action['gyro'] = tracking.action['gyro']
            return result.action
        plan = None
    if obs['own'].get('ink') is not None and obs['own']['ink'] < .12:
        result = neutral()
        result['buttons'][1] = 1
        return result
    enemy = next((e for e in obs['enemies'] if e['visible']), None)
    if enemy is None:
        return neutral()
    aim.windup = 6
    result = aim.aim(obs, enemy['public']['player_id'], fast=True)
    if not result.done:
        return result.action
    plan = charge_slash(obs)
    return plan.tick(obs).action
