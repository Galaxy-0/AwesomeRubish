"""Alpha: traverse useful ground and paint it, contesting only nearby threats.

The state machine is high ground -> center -> far lane -> center -> near lane.
Movement uses the accepted static route follower. Shooting is deliberately
independent of arrival: a moving Stamper can coat the route instead of spending
most of the match walking with its weapon idle. No live paint map is available.
"""
import math

from atlas import MapAtlas
from skills import Skills, aim_at, neutral, own_state


controller = None
match_key = None
route = ()
leg = 0
leg_started = 0
refilling = False


def _reset(obs):
    global controller, match_key, route, leg, leg_started, refilling
    controller = Skills(MapAtlas.load(obs['stage_id']))
    match_key = (obs['match_id'], obs['stage_id'])
    high = controller.atlas.region('central_high')
    # The first side trip paints the side opposite the high platform.
    far, near = ('east_lane', 'west_lane') if high[0] < 0 else ('west_lane', 'east_lane')
    route = ('central_high', 'center', far, 'center', near, 'center')
    leg = 0
    leg_started = obs['frame']
    refilling = False


def _shoot_window(frame):
    # A held ZR charges Stamper; releasing it regularly produces repeated swings.
    return frame % 36 < 12


def _paint_target(obs, move):
    """Aim ahead of travel, alternating left/center/right every few swings."""
    p = obs['own']['position']
    if move is not None and not move.done and controller.path:
        q = controller.path[min(controller.index + 4, len(controller.path) - 1)]
        dx, dz = q[0] - p[0], q[2] - p[2]
        distance = math.hypot(dx, dz)
        if distance > .2:
            ux, uz = dx / distance, dz / distance
            side = (-1, 0, 1)[(obs['frame'] // 108) % 3]
            return (p[0] + ux * 4 + uz * side * 1.7,
                    q[1], p[2] + uz * 4 - ux * side * 1.7)
    # At a stop, sweep the surrounding floor in eight fixed directions.
    angle = (obs['frame'] // 96 % 8) * math.tau / 8
    return (p[0] + 5 * math.sin(angle), p[1] - .5,
            p[2] + 5 * math.cos(angle))


def act(obs):
    global leg, leg_started, refilling
    if controller is None or match_key != (obs['match_id'], obs['stage_id']):
        _reset(obs)
    own = own_state(obs)
    if own is None:
        return neutral()
    p = own['position']
    frame = obs['frame']

    # A low tank needs a real pause to refill. ZL uses only known own ink state.
    ink = own.get('ink')
    if ink is not None:
        if ink < .24:
            refilling = True
        elif ink >= .85:
            refilling = False
    if refilling:
        a = neutral()
        a['buttons'][1] = 1
        return a

    goal = controller.atlas.region(route[leg % len(route)])
    try:
        move = controller.move_to(obs, goal)
    except ValueError:
        move = None
    # A single inaccessible or costly leg cannot consume the entire match.
    if ((move is not None and (move.done or move.status == 'blocked'))
            or frame - leg_started > 1500):
        leg += 1
        leg_started = frame
        goal = controller.atlas.region(route[leg % len(route)])
        try:
            move = controller.move_to(obs, goal)
        except ValueError:
            move = None

    a = move.action if move is not None else neutral()
    enemies = [e for e in obs['enemies'] if e['visible'] and e['position'] is not None]
    enemy = min(enemies, key=lambda e: math.dist(p, e['position'])) if enemies else None
    if enemy is not None and math.dist(p, enemy['position']) < 8 and abs(p[1] - enemy['position'][1]) < 2.5:
        # Nearby, visible opponents are worth interrupting the paint sweep.
        target = list(enemy['position'])
        target[1] += .7
        aim = aim_at(obs, target)
        a['sticks'][2:] = aim.action['sticks'][2:]
        a['gyro'] = aim.action['gyro']
        # Strafe while aiming; keep the route follower's B jump when needed.
        if move is None or move.done:
            a['sticks'][:2] = [.55, 0]
        a['buttons'][0] = int(_shoot_window(frame) and aim.status != 'unavailable')
        return a

    aim = aim_at(obs, _paint_target(obs, move))
    if aim.status != 'unavailable':
        a['sticks'][2:] = aim.action['sticks'][2:]
        a['gyro'] = aim.action['gyro']
        # Loose aim is enough for turf coverage; exact lock delays too many swings.
        a['buttons'][0] = int(_shoot_window(frame))
    return a
