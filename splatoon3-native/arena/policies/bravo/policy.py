"""Bravo v2: retain v1's combat, spend ink on fresh reachable floor.

CoverageTour is a belief about our past attempts, never a private ink map.
The archived v1 combat core is copied locally so this version is self-contained.
"""
import math

from skills import Skills, neutral, own_state, wrap
from v1_core import Bravo as CombatCore
from territory import CoverageTour


class Bravo(CombatCore):
    def __init__(self, obs):
        self.frame = obs['frame']
        self.ground_stable = None
        super().__init__(obs)
        self.tour = CoverageTour(self.atlas)
        self.motion_anchor = None
        self.motion_calls = 0

    def route_reset(self):
        self.nav = Skills(self.atlas, stall_frames=75)
        if hasattr(self, 'tour'):
            self.nav.blocked_edges = self.tour.active_blocks(self.frame)
        self.motion_anchor = None
        self.motion_calls = 0
        self.jump_until = -1
        self.dwell_start = None

    def reset_navigation(self):
        super().reset_navigation()
        self.route_reset()
        if hasattr(self, 'tour'):
            self.tour.goal = None

    def spawn_action(self, obs):
        own = obs['own']; p = own.get('position'); sample = own.get('sample_frame')
        if p is not None and sample is not None and 0 <= obs['frame']-sample <= 8:
            self.tour.set_home(p)
            spawn_zone = self.tour.sign*p[2] > abs(self.tour.home['ground'][2])-15
            if self.landing and own['public']['alive'] is True and (spawn_zone or self.was_dead):
                # R3 Yagara mistook decorative geometry at y=20.8 for landing,
                # then discarded four goals while still flying to y=13.5.
                i = self.ground(p)
                expected_y = self.tour.home['ground'][1]
                stable = p[1] <= expected_y+.7 and i is not None and \
                    abs(p[1]-self.atlas.points[i][1]) < .35 and \
                    math.hypot(p[0]-self.atlas.points[i][0], p[2]-self.atlas.points[i][2]) < 1.2
                if not stable:
                    self.ground_stable = None
                    return neutral()
                if self.ground_stable is None:
                    self.ground_stable = obs['frame']
                if obs['frame']-self.ground_stable < 8:
                    return neutral()
        result = super().spawn_action(obs)
        if self.was_dead:
            self.ground_stable = None
        return result

    def refill(self, obs, enemy):
        was_refilling = self.refill_start is not None
        result = super().refill(obs, enemy)
        if was_refilling and self.refill_start is None:
            # Waiting for ink is not evidence of a blocked route. Restart its
            # progress clock from the actual position; retain obstruction memory.
            self.route_reset()
        return result

    def paint_target(self, own, route_point):
        p = own['position']
        dx, dz = route_point[0]-p[0], route_point[2]-p[2]
        distance = math.hypot(dx, dz)
        if distance < 3 or abs(route_point[1]-p[1]) > .5:
            return route_point
        # Alternating shoulders widen the strip instead of spending every
        # shot on the same forward line. Only project onto nearby static floor.
        angle = math.atan2(dx, dz)+(.38 if self.frame//60 % 2 else -.38)
        length = min(6.5, max(4., distance))
        desired = (p[0]+length*math.sin(angle), route_point[1], p[2]+length*math.cos(angle))
        i = self.ground(desired)
        if i is not None:
            q = self.atlas.points[i]
            if self.atlas.swimmable[i] and abs(q[1]-p[1]) < .5 and \
                    math.hypot(q[0]-desired[0], q[2]-desired[2]) < 1.5:
                return q
        return route_point

    def patrol(self, obs):
        own = obs['own']; p = own['position']; frame = obs['frame']
        self.tour.observe(p)
        for _ in range(2):
            if self.tour.goal is None:
                i = self.ground(p)
                if i is None:
                    return neutral()
                self.tour.choose(p, i, frame, obs.get('remaining_seconds'))
                self.route_reset()
            self.targets = (self.tour.goal,)
            self.target_index = 0
            route = self.nav.move_to(obs, self.tour.goal)
            if not route.done:
                break
            # Do not idle/spray for 90 presents at every endpoint. Select the
            # next patch now; the arrival itself updates visit memory.
            self.tour.goal = None
        if route.status == 'blocked':
            self.tour.obstructed(self.nav, p, frame)
            self.route_reset()
            return neutral()
        a = route.action
        if route.status in ('unavailable', 'replanning'):
            return a
        if self.motion_anchor is None or math.hypot(p[0]-self.motion_anchor[0], p[2]-self.motion_anchor[2]) > .2:
            self.motion_anchor = tuple(p)
            self.motion_calls = 0
        elif any(abs(v) > .2 for v in a['sticks'][:2]):
            self.motion_calls += 1
        if self.motion_calls >= 105:
            # Jumping vertically does not count as horizontal progress.
            i = self.ground(p)
            if i is None:
                return neutral()
            floor = self.atlas.points[i]
            self.tour.obstructed(self.nav, (p[0], floor[1], p[2]), frame)
            self.route_reset()
            return neutral()
        q = self.paint_target(own, self.lookahead(p))
        sight = self.turn.aim(obs, q)
        a['sticks'][2:] = sight.action['sticks'][2:]
        a['gyro'] = sight.action['gyro']
        if route.status == 'recovering_jump':
            self.jump_until = frame+12
        if frame < self.jump_until:
            a['buttons'][4] = 1
        yaw_error = abs(wrap(math.atan2(q[0]-p[0], q[2]-p[2])-own['view_yaw']))
        if frame-self.last_light >= 30 and yaw_error < .65 and not a['buttons'][4] \
                and (own.get('ink') or 0) > .06:
            a['buttons'][0] = 1
            self.last_light = frame
            i = self.ground(p)
            foot = self.atlas.points[i] if i is not None else p
            self.tour.paint_attempt(foot, q)
        return a

    def act(self, obs):
        self.frame = obs['frame']
        spawn = self.spawn_action(obs)
        if spawn is not None:
            return spawn
        own = own_state(obs)
        if own is None or own.get('view_yaw') is None or own.get('view_pitch') is None:
            return neutral()
        enemy = next((e for e in obs['enemies'] if e.get('visible') is True and
                      e.get('position') is not None and e.get('sample_frame') is not None and
                      0 <= self.frame-e['sample_frame'] <= 8), None)
        recovery = self.refill(obs, enemy)
        if recovery is not None:
            return recovery
        fight = self.combat(obs, enemy)
        if fight is not None:
            self.in_combat = True
            return fight
        if self.in_combat:
            self.route_reset()
            self.in_combat = False
        return self.patrol(obs)


controller = None


def act(obs):
    global controller
    if controller is None or controller.match != obs['match_id']:
        controller = Bravo(obs)
    return controller.act(obs)
