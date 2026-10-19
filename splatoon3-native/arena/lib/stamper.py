"""Public Splatana Stamper controllers. Only allowlisted observations enter here.

Macro and predictive results include ``frames``: the maximum execution budget.
Call again at that boundary, including the final neutral release. ``fast_turn``
returns the base aim_at result and must be executed for ONE present at a time.
Timing is in controlled game presents, never wall time. See README for scope.
"""
from dataclasses import dataclass
import math

from skills import aim_at, neutral, own_state, wrap

WEAPON_ID = 8000
FULL_CHARGE_FRAMES = 24  # conservative until the release sweep is accepted
EMERGE_CHARGE_FRAMES = 30  # emergence takes additional native action time
LIGHT_CYCLE_PARAMETER_FRAMES = 26
LIGHT_PERIOD = 30  # 26-frame input repetition swallowed the second native swing
CHARGE_KEEP_SUPPORTED = False


@dataclass
class Result:
    action: dict
    frames: int = 1
    done: bool = False
    status: str = 'running'
    phase: str = ''


def _action(*buttons, move=(0., 0.)):
    action = neutral()
    action['sticks'][:2] = list(move)
    for button in buttons:
        action['buttons'][button] = 1
    return action


def _move(move):
    x, y = map(float, move)
    if not all(math.isfinite(v) for v in (x, y)) or math.hypot(x, y) > 1.000001:
        raise ValueError('movement must be a finite unit-circle stick vector')
    return x, y


class Plan:
    """Frame-bounded macro; observation gaps never silently skip input edges."""
    def __init__(self, obs, segments, *, ink=0., submerged=False, special=False):
        own = own_state(obs)
        self.match = obs['match_id']
        self.start = obs['frame']
        self.last = self.start
        self.end = sum(n for _, n, _ in segments)
        self.segments = segments
        self.cancelled = None
        if own is None:
            self.cancelled = 'unavailable'
        elif own['public'].get('weapon') != WEAPON_ID:
            self.cancelled = 'wrong_weapon'
        elif ink and (own.get('ink') is None or own['ink'] < ink):
            self.cancelled = 'insufficient_ink'
        elif submerged and own.get('submerged') is not True:
            self.cancelled = 'requires_own_ink'
        elif special and (own.get('special') is None or own['special'] < 1.):
            self.cancelled = 'requires_full_special'
        self.expected = self.start

    def tick(self, obs):
        frame = obs['frame']
        if obs['match_id'] != self.match or frame < self.last:
            self.cancelled = 'reset'
        elif own_state(obs) is None:
            self.cancelled = 'unavailable'
        elif frame > self.expected:
            self.cancelled = 'missed_boundary'
        self.last = frame
        if self.cancelled:
            return Result(neutral(), done=True, status=self.cancelled)
        elapsed = frame - self.start
        edge = 0
        for name, duration, action in self.segments:
            edge += duration
            if elapsed < edge:
                remaining = edge - elapsed
                # Freshness is checked again at least every six presents.
                budget = min(6, remaining)
                self.expected = frame + budget
                return Result({k: list(v) for k, v in action.items()}, budget, phase=name)
        return Result(neutral(), done=True, status='complete', phase='released')


def charge_slash(obs, hold_frames=FULL_CHARGE_FRAMES, *, dash=False,
                 after=(0., 0.), after_frames=14):
    """Hold then release ZR. Dash primes forward stick through the release."""
    if type(hold_frames) is not int or not 1 <= hold_frames <= 180:
        raise ValueError('hold_frames must be 1..180 presents')
    if type(after_frames) is not int or not 1 <= after_frames <= 180:
        raise ValueError('after_frames must be 1..180 presents')
    movement = _move(after)
    segments = [('charge', hold_frames, _action(0, move=(0., 1.) if dash else (0., 0.))),
                ('release', 1, _action(move=(0., 1.) if dash else (0., 0.))),
                ('recover_move', after_frames, _action(move=movement)),
                ('neutral', 1, neutral())]
    # Conservative across gear: an attempted charge must be able to reserve
    # the full unmodified cost, even when released earlier than the default.
    return Plan(obs, segments, ink=.117 if hold_frames >= 5 else .052)


def emerge_charge(obs, hold_frames=EMERGE_CHARGE_FRAMES, **kwargs):
    """Release ZL and press ZR in the first action after the swim approach.

    No charge is stored underwater: native IsEnableChargeKeep is false.
    The caller can use Skills.swim_to before constructing this plan.
    """
    plan = charge_slash(obs, hold_frames, **kwargs)
    if obs['own'].get('submerged') is not True:
        plan.cancelled = 'requires_own_ink'
    return plan


def light_combo(obs, count=3, *, period=LIGHT_PERIOD, after=(0., 0.), after_frames=14):
    if type(count) is not int or not 1 <= count <= 10:
        raise ValueError('count must be 1..10')
    if type(period) is not int or period < LIGHT_CYCLE_PARAMETER_FRAMES:
        raise ValueError('period must allow the native light swing cycle')
    if type(after_frames) is not int or not 1 <= after_frames <= 180:
        raise ValueError('after_frames must be 1..180')
    movement = _move(after)
    segments = []
    for index in range(count):
        segments.extend([(f'light_{index}', 1, _action(0)),
                         ('light_recovery', period - 1, _action(move=movement))])
    segments.extend([('after_move', after_frames, _action(move=movement)), ('neutral', 1, neutral())])
    return Plan(obs, segments, ink=.052 * count)


def squid_roll(obs, direction=(0., -1.), *, approach_frames=30):
    """In own ink, gain swim speed then reverse stick + B while holding ZL.

    Caller must choose an actual reversal of its approach; local forward is
    used for the approach. Native roll confirmation is separate from jumping.
    """
    x, y = _move(direction)
    if math.hypot(x, y) < .9 or y > -.5 or not 12 <= approach_frames <= 120:
        raise ValueError('roll requires a fast reversal of the forward approach')
    return Plan(obs, [('swim', approach_frames, _action(1, move=(0., 1.))),
                      ('roll_edge', 1, _action(1, 4, move=(x, y))),
                      ('roll_travel', 15, _action(1, move=(x, y))),
                      ('neutral', 1, neutral())], submerged=True)


def squid_surge(obs, *, charge_frames=60):
    """While clinging to an inked wall, stop the stick, hold ZL+B, release B."""
    if type(charge_frames) is not int or not 45 <= charge_frames <= 180:
        raise ValueError('surge charge must be at least 45 frames')
    # Wall clinging is not floor submergence; M6 ground-contact codes are not
    # an on-wall sensor. The caller must establish a climbable own-ink wall.
    return Plan(obs, [('wall_charge', charge_frames, _action(1, 4)),
                      ('surge_release', 24, _action(1, move=(0., 1.))),
                      ('neutral', 1, neutral())])


def burst_bomb(obs, *, hold_frames=1):
    if type(hold_frames) is not int or not 1 <= hold_frames <= 120:
        raise ValueError('invalid sub hold')
    return Plan(obs, [('bomb_aim', hold_frames, _action(2)),
                      ('bomb_release', 45, neutral())], ink=.45)


def zipcaster(obs, *, activation_frames=30, hook_frames=60):
    """EXPERIMENTAL: full-meter RS activation followed by an unverified R hook.

    This intentionally refuses unknown charge. Never infer charge from score
    or opponent state. Camera aiming can be composed before the hook phase.
    """
    if type(activation_frames) is not int or type(hook_frames) is not int or not 1 <= activation_frames <= 120 or not 1 <= hook_frames <= 180:
        raise ValueError('invalid special timing')
    return Plan(obs, [('special_press', 1, _action(3)),
                      ('special_activate', activation_frames, neutral()),
                      ('hook_press', hook_frames, _action(2)),
                      ('hook_release', 1, neutral())], special=True)


class FastTurn:
    """Calibrate virtual-controller Z yaw from OWN feedback, then turn.

    Six presents of .2 turns/s, eight neutral presents for packet feedback.
    The learned sign/gain avoids assuming that controller Y is game yaw.
    Caller must execute one present per result, including calibration pauses.
    """
    def __init__(self):
        self._clear()

    def _clear(self, match=None, player=None):
        self.match = match
        self.player = player
        self.start = None
        self.yaw = None
        self.last = None
        self.gain = None
        self.sign = None
        self.fallback = False

    def aim(self, obs, target):
        own = own_state(obs)
        if own is None or own.get('view_yaw') is None or own.get('view_pitch') is None:
            self._clear()
            return Result(neutral(), status='unavailable', phase='fast_turn')
        player = own['public'].get('player_id')
        frame = obs['frame']
        if self.match != obs['match_id'] or self.player != player or \
                self.last is not None and (frame < self.last or
                self.gain is None and not self.fallback and frame > self.last + 1):
            self._clear(obs['match_id'], player)
        self.last = frame
        if self.start is None:
            self.start = frame
            self.yaw = own['view_yaw']
        elapsed = frame - self.start
        if elapsed < 14:
            action = neutral()
            if elapsed < 6:
                action['gyro'][2] = .2
            return Result(action, phase='gyro_calibration')
        if self.gain is None and not self.fallback:
            delta = wrap(own['view_yaw'] - self.yaw)
            if abs(delta) >= .01:
                self.sign = math.copysign(1., delta)
                self.gain = max(.01, min(.5, abs(delta) / (6 * .2)))
            else:
                self.fallback = True
        if self.fallback:
            result = fast_turn(obs, target)
            return Result(result.action, 1, result.done, result.status, 'stick_fallback')
        result = aim_at(obs, target)
        p = own['position']
        error = wrap(math.atan2(target[0]-p[0], target[2]-p[2])-own['view_yaw'])
        result.action['sticks'][2] = -math.copysign(1., error) if abs(error)>.5 else 0.
        result.action['gyro'][2] = self.sign * max(-.35, min(.35, error/(12*self.gain))) if abs(error)>.035 else 0.
        return Result(result.action, 1, result.done, result.status, 'calibrated_gyro_turn')


class PredictiveAim:
    """Velocity uses only consecutive CURRENT visible samples of one enemy."""
    def __init__(self, projectile_speed=.8, windup_frames=6, max_speed=.8,
                 max_lead_frames=30):
        if not all(math.isfinite(x) and x > 0 for x in
                   (projectile_speed, max_speed, max_lead_frames)) or windup_frames < 0:
            raise ValueError('invalid aim bounds')
        self.speed = projectile_speed
        self.windup = windup_frames
        self.max_speed = max_speed
        self.max_lead = max_lead_frames
        self.previous = None
        self.match = None
        self.target = None
        self.velocity = (0., 0., 0.)
        self.turner = FastTurn()

    def aim(self, obs, enemy_id, *, fast=False):
        own = own_state(obs)
        enemy = next((e for e in obs['enemies'] if e['public']['player_id'] == enemy_id), None)
        if self.match != obs['match_id']:
            self.previous = None
        self.match = obs['match_id']
        if own is None or enemy is None or enemy.get('visible') is not True or \
                enemy.get('position') is None or enemy.get('sample_frame') is None or \
                not 0 <= obs['frame'] - enemy['sample_frame'] <= 8:
            self.previous = None
            self.target = None
            self.velocity = (0., 0., 0.)
            return Result(neutral(), status='target_unavailable')
        frame = enemy['sample_frame']
        position = tuple(enemy['position'])
        velocity = (0., 0., 0.)
        if self.previous is not None:
            old_id, old_frame, old_position = self.previous
            dt = frame - old_frame
            if old_id == enemy_id and 0 < dt <= 12:
                raw = tuple((p - q) / dt for p, q in zip(position, old_position))
                magnitude = math.sqrt(sum(v * v for v in raw))
                if magnitude <= self.max_speed:
                    velocity = raw
            elif old_id == enemy_id and dt == 0:
                velocity = self.velocity
        self.previous = (enemy_id, frame, position)
        self.velocity = velocity
        distance = math.dist(own['position'], position)
        lead = min(self.max_lead, obs['frame'] - frame + self.windup + distance / self.speed)
        self.target = tuple(p + v * lead + (1.1 if i == 1 else 0.)
                            for i, (p, v) in enumerate(zip(position, velocity)))
        aimed = self.turner.aim(obs, self.target) if fast else aim_at(obs, self.target)
        return Result(aimed.action, 1 if fast else 3, aimed.done, aimed.status, 'predictive_aim')


def fast_turn(obs, target):
    """Closed-loop yaw turn; re-sample after ONE present at full stick."""
    result = aim_at(obs, target)
    own = own_state(obs)
    if own is not None and own.get('view_yaw') is not None:
        p = own['position']
        error = wrap(math.atan2(target[0] - p[0], target[2] - p[2]) - own['view_yaw'])
        if abs(error) > .25:
            result.action['sticks'][2] = -math.copysign(1., error)
    return result
