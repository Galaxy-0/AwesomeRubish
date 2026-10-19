"""Bravo: paint while traversing the open lanes, contest only nearby threats.

The atlas is static. We deliberately do not infer current turf ownership from it.
"""
import math

from atlas import MapAtlas
from skills import Skills, aim_at, neutral, own_state


_atlas = None
_nav = None
_match = None
_targets = ()
_target_index = 0
_dwell_start = None
_refill_start = None


def _reset(obs):
    global _atlas, _nav, _match, _targets, _target_index, _dwell_start, _refill_start
    _match = obs['match_id']
    _atlas = MapAtlas.load(obs['stage_id'])
    _nav = Skills(_atlas)
    # Go to the lane away from the example's central high ground first. It
    # paints a broad uncontested route rather than repeatedly crossing its arc.
    high = _atlas.region('central_high')
    lanes = [_atlas.region('west_lane'), _atlas.region('east_lane')]
    lanes.sort(key=lambda q: -math.hypot(q[0]-high[0], q[2]-high[2]))
    _targets = (lanes[0], _atlas.region('center'), lanes[1],
                _atlas.region('center'))
    _target_index = 0
    _dwell_start = None
    _refill_start = None


def _lookahead(position):
    """Ground point several metres down the current route for forward paint."""
    if not _nav.path:
        return _targets[_target_index]
    travelled = 0.0
    previous = position
    for q in _nav.path[_nav.index:]:
        travelled += math.hypot(q[0]-previous[0], q[2]-previous[2])
        if travelled >= 5.0:
            return q
        previous = q
    return _nav.path[-1]


def _swing(action, frame):
    # Releasing ZR is essential: holding it indefinitely only charges Stamper.
    action['buttons'][0] = int(frame % 36 < 12)
    return action


def act(obs):
    global _target_index, _dwell_start, _refill_start
    if _match != obs['match_id'] or _atlas is None:
        _reset(obs)
    own = own_state(obs)
    if own is None:
        return neutral()
    frame = obs['frame']
    position = own['position']

    # Refill on our freshly painted route. The cap avoids waiting forever if
    # the current tile cannot support submerged recovery.
    ink = own.get('ink')
    if ink is not None and ink < .19 and _refill_start is None:
        _refill_start = frame
    if _refill_start is not None:
        if ink is not None and ink >= .75:
            _refill_start = None
        elif frame-_refill_start < 240:
            action = neutral()
            action['buttons'][1] = 1
            return action
        else:
            _refill_start = None

    # Only fight a visible, nearby enemy. Chasing a remembered location spends
    # time without painting and visibility never implies knowledge of enemy HP.
    enemy = next((e for e in obs['enemies'] if e['visible'] and e['position']), None)
    if enemy and (obs.get('remaining_seconds') is None or obs['remaining_seconds'] > 22):
        distance = math.dist(position, enemy['position'])
        if distance < 7.0:
            target = list(enemy['position'])
            target[1] += .7
            sight = aim_at(obs, target)
            action = sight.action
            # A short sidestep makes a stationary exchange less predictable.
            action['sticks'][0] = .65 if frame % 120 < 60 else -.65
            if sight.done:
                return _swing(action, frame)
            return action

    target = _targets[_target_index]
    try:
        route = _nav.move_to(obs, target)
    except ValueError:
        route = None

    if route is None or route.status == 'blocked':
        _target_index = (_target_index+1) % len(_targets)
        _dwell_start = None
        return neutral()

    if route.done:
        if _dwell_start is None:
            _dwell_start = frame
        # Briefly sweep the patch at each lane endpoint before moving on.
        if frame-_dwell_start >= 180:
            _target_index = (_target_index+1) % len(_targets)
            _dwell_start = None
            return neutral()
        angle = (frame-_dwell_start)//36 * (math.pi/3)
        ground = (position[0]+5*math.sin(angle), position[1],
                  position[2]+5*math.cos(angle))
        sight = aim_at(obs, ground)
        return _swing(sight.action, frame)

    _dwell_start = None
    action = route.action
    if route.status in ('unavailable', 'replanning'):
        return action
    # Combine the tested route's movement with a forward, ground-level aim.
    # Turning the view does not change the route target; move_to compensates on
    # the next observation using the new view yaw.
    sight = aim_at(obs, _lookahead(position))
    if sight.status != 'unavailable':
        action['sticks'][2:] = sight.action['sticks'][2:]
        action['gyro'] = sight.action['gyro']
    if route.status == 'recovering_jump':
        return action
    return _swing(action, frame)
