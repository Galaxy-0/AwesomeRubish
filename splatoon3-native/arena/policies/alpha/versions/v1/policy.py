"""Alpha v1: retain the successful paint circuit; defend its uptime.

Tactics use only current visible enemies, own feedback and the public atlas.
A6 combat runs at one present; ordinary painting retains v0's 12-present input
cadence. No private paint, enemy HP, native socket or test-only special is used.
"""
from collections import deque
import math

from atlas import MapAtlas
from skills import Skills, aim_at, neutral, own_state, wrap
from stamper import PredictiveAim, charge_slash, emerge_charge, light_combo


def clone(action):
    return {k: list(v) for k, v in action.items()}


def horizontal(p, q):
    return math.hypot(p[0] - q[0], p[2] - q[2])


class Alpha:
    def __init__(self, obs):
        self.key = (obs['match_id'], obs['stage_id'])
        self.atlas = MapAtlas.load(obs['stage_id'])
        self.nav = Skills(self.atlas)
        high = self.atlas.region('central_high')
        far, near = ('east_lane', 'west_lane') if high[0] < 0 else ('west_lane', 'east_lane')
        self.route = ('central_high', 'center', far, 'center', near, 'center')
        self.leg = 0
        self.leg_started = obs['frame']
        self.aim = PredictiveAim(windup_frames=30, max_lead_frames=48)
        self.plan = None
        self.charge_frames = 0
        self.fight_started = None
        self.paint_until = -1
        self.refilling = False
        self.retreat_until = -1
        self.retreat_goal = None
        self.evade_cache = None
        self.evade_frame = -100
        self.paint_cache = None
        self.paint_frame = -100
        self.last_hp = None
        self.trail = deque(maxlen=24)
        self.trail_frame = -120
        self.launch = None
        self.dead_since = None

    def invalidate(self):
        # Resuming after a pause replans from the actual position. A refill or
        # fight must not be misread as a stalled walking edge.
        self.nav.target = None
        self.paint_cache = self.evade_cache = None

    def visible_enemy(self, obs):
        p = obs['own']['position']
        enemies = [e for e in obs['enemies']
                   if e.get('visible') is True and e.get('position') is not None
                   and e['public'].get('alive') is not False
                   and e.get('sample_frame') is not None
                   and 0 <= obs['frame'] - e['sample_frame'] <= 8]
        return min(enemies, key=lambda e: math.dist(p, e['position'])) if enemies else None

    def unavailable(self, obs):
        own = obs['own']
        self.plan = None
        self.aim.aim(obs, None, fast=True)  # clear velocity on hidden/unavailable state
        self.invalidate()
        if own['public'].get('alive') is not False:
            return neutral()
        if self.dead_since is None:
            self.dead_since = obs['frame']
        sample, p = own.get('sample_frame'), own.get('position')
        ready = (sample is not None and 0 <= obs['frame'] - sample <= 8
                 and p is not None and self.launch is not None
                 and math.dist(p, self.launch) < 3
                 and own.get('hp') is not None and own['hp'] >= .99
                 and own.get('ink') is not None and own['ink'] >= .9
                 and obs['frame'] - self.dead_since >= 120)
        # v0 stayed neutral forever after Down. Try ordinary spawner launch
        # pulses only after fresh own HP/ink recover at the recorded launch.
        a = neutral()
        if ready and obs['frame'] % 30 == 0:
            a['buttons'][0] = 1
        return a

    def choose_retreat(self, obs, enemy):
        p = obs['own']['position']
        # Previously stood-on ground is preferable to an invented escape edge.
        for q in reversed(self.trail):
            if horizontal(p, q) >= 5 and abs(p[1] - q[1]) < 1.5:
                if enemy is None or horizontal(q, enemy['position']) > horizontal(p, enemy['position']) + 1:
                    return q
        if enemy is not None:
            dx, dz = p[0] - enemy['position'][0], p[2] - enemy['position'][2]
        elif self.launch is not None:
            dx, dz = self.launch[0] - p[0], self.launch[2] - p[2]
        else:
            dx, dz = 0., 1.
        norm = max(.01, math.hypot(dx, dz))
        wanted = (p[0] + 6 * dx / norm, p[1], p[2] + 6 * dz / norm)
        return self.atlas.points[self.atlas.nearest(wanted)]

    def evade(self, obs, enemy):
        f, own = obs['frame'], obs['own']
        if self.retreat_goal is None:
            self.retreat_goal = self.choose_retreat(obs, enemy)
            self.invalidate()
        if self.evade_cache is None or f - self.evade_frame >= 12:
            result = self.nav.move_to(obs, self.retreat_goal)
            if result.status == 'blocked' or (result.done and enemy is not None
                                             and horizontal(own['position'], enemy['position']) < 12):
                self.retreat_goal = self.choose_retreat(obs, enemy)
                self.nav.target = None
                result = self.nav.move_to(obs, self.retreat_goal)
            a = result.action
            ink = own.get('ink')
            if own.get('submerged') is True or ink is not None and ink < .4:
                a['buttons'][1] = 1
            else:
                # Paint the escape direction while walking; no blind enemy fire.
                p, q = own['position'], self.retreat_goal
                dx, dz = q[0] - p[0], q[2] - p[2]
                norm = max(.01, math.hypot(dx, dz))
                aim = aim_at(obs, (p[0] + 4 * dx / norm, p[1], p[2] + 4 * dz / norm))
                a['sticks'][2:] = aim.action['sticks'][2:]
                a['gyro'] = aim.action['gyro']
                a['buttons'][0] = int(f % 36 < 12)
            self.evade_cache, self.evade_frame = clone(a), f
        return clone(self.evade_cache)

    def paint(self, obs):
        f, p = obs['frame'], obs['own']['position']
        if self.paint_cache is not None and f - self.paint_frame < 12:
            return clone(self.paint_cache)
        goal = self.atlas.region(self.route[self.leg % len(self.route)])
        move = self.nav.move_to(obs, goal)
        if move.done or move.status == 'blocked' or f - self.leg_started > 1500:
            self.leg += 1
            self.leg_started = f
            goal = self.atlas.region(self.route[self.leg % len(self.route)])
            move = self.nav.move_to(obs, goal)
        target = None
        if not move.done and self.nav.path:
            q = self.nav.path[min(self.nav.index + 4, len(self.nav.path) - 1)]
            dx, dz = q[0] - p[0], q[2] - p[2]
            distance = math.hypot(dx, dz)
            if distance > .2:
                ux, uz = dx / distance, dz / distance
                side = (-1, 0, 1)[(f // 108) % 3]
                target = (p[0] + ux * 4 + uz * side * 1.7,
                          q[1], p[2] + uz * 4 - ux * side * 1.7)
        if target is None:
            angle = (f // 96 % 8) * math.tau / 8
            target = (p[0] + 5 * math.sin(angle), p[1] - .5, p[2] + 5 * math.cos(angle))
        aiming = aim_at(obs, target)
        a = move.action
        a['sticks'][2:] = aiming.action['sticks'][2:]
        a['gyro'] = aiming.action['gyro']
        a['buttons'][0] = int(f % 36 < 12 and aiming.status != 'unavailable')
        self.paint_cache, self.paint_frame = clone(a), f
        return a

    def combat(self, obs, enemy):
        f, own = obs['frame'], obs['own']
        eid = enemy['public']['player_id']
        if self.plan is not None:
            result = self.plan.tick(obs)
            if not result.done:
                self.aim.windup = max(0, self.charge_frames - (f - self.plan.start)) + 6
                tracking = self.aim.aim(obs, eid, fast=True)
                if tracking.status != 'target_unavailable':
                    result.action['sticks'][2:] = tracking.action['sticks'][2:]
                    result.action['gyro'] = tracking.action['gyro']
                return result.action
            self.plan = None
            return neutral()  # preserve the final neutral/release boundary
        self.aim.windup = 6
        aiming = self.aim.aim(obs, eid, fast=True)
        if self.aim.target is None:
            return neutral()
        p, target = own['position'], self.aim.target
        yaw_error = abs(wrap(math.atan2(target[0] - p[0], target[2] - p[2]) - own['view_yaw']))
        desired_pitch = max(-.9, min(.9, math.atan2(target[1] - p[1] - 1.1,
                                                   max(.05, horizontal(p, target)))))
        aligned = (aiming.done or yaw_error < .12 and abs(own['view_pitch'] - desired_pitch) < .09
                   and f - self.fight_started >= 14)
        if not aligned:
            return aiming.action
        distance = math.dist(p, enemy['position'])
        # Near targets get quick 30-present light cycles. Midrange gets a full
        # 24-present charge (30 when emerging); no unsupported charge keeping.
        if distance < 6:
            self.plan = light_combo(obs, count=1, period=30, after_frames=1)
            self.charge_frames = 0
        elif own.get('submerged') is True:
            self.plan = emerge_charge(obs, hold_frames=30, after_frames=12)
            self.charge_frames = 30
        else:
            self.plan = charge_slash(obs, hold_frames=24, after_frames=12)
            self.charge_frames = 24
        a = self.plan.tick(obs).action
        a['sticks'][2:] = aiming.action['sticks'][2:]
        a['gyro'] = aiming.action['gyro']
        return a

    def act(self, obs):
        own = own_state(obs)
        if own is None:
            return self.unavailable(obs)
        if own.get('view_yaw') is None or own.get('view_pitch') is None:
            self.plan = None
            return neutral()
        f, p = obs['frame'], own['position']
        if self.launch is None and f < 120 and p[1] > 20:
            self.launch = tuple(p)
        if self.dead_since is not None:
            self.dead_since = None
            self.refilling = False
            self.leg_started = f
            self.retreat_until = -1
            self.retreat_goal = None
            self.invalidate()
        enemy = self.visible_enemy(obs)
        hp, ink = own.get('hp'), own.get('ink')
        damaged = hp is not None and self.last_hp is not None and self.last_hp - hp > .15
        self.last_hp = hp
        if (hp is not None and hp < .55) or damaged or (
                ink is not None and ink < .24 and enemy is not None
                and horizontal(p, enemy['position']) < 16):
            self.retreat_until = f + 180
            self.plan = None
        if f < self.retreat_until:
            self.fight_started = None
            self.aim.aim(obs, None, fast=True)
            return self.evade(obs, enemy)
        if self.retreat_goal is not None:
            self.retreat_goal = None
            self.invalidate()
        if hp is not None and hp > .85 and enemy is None and f - self.trail_frame >= 120:
            if not self.trail or horizontal(p, self.trail[-1]) > 2:
                self.trail.append(tuple(p))
            self.trail_frame = f
        eligible = (enemy is not None and math.dist(p, enemy['position']) < 20
                    and abs(p[1] - enemy['position'][1]) < 3.5
                    and (f >= self.paint_until or horizontal(p, enemy['position']) < 6))
        if eligible and (ink is None or ink >= .15):
            if self.fight_started is None:
                self.fight_started = f
                self.paint_cache = None
            if f - self.fight_started < 360:
                return self.combat(obs, enemy)
            # Never spend the whole turf match staring at an unproductive duel.
            self.paint_until = f + 120
        if self.plan is not None or self.fight_started is not None:
            self.plan = None
            self.fight_started = None
            self.invalidate()
            self.aim.aim(obs, None, fast=True)
            return neutral()
        self.aim.aim(obs, None, fast=True)
        if ink is not None:
            if ink < .24:
                self.refilling = True
            elif ink >= .85:
                self.refilling = False
        if self.refilling:
            self.invalidate()
            a = neutral()
            a['buttons'][1] = 1
            return a
        return self.paint(obs)


agent = None


def act(obs):
    global agent
    if agent is None or agent.key != (obs['match_id'], obs['stage_id']):
        agent = Alpha(obs)
    return agent.act(obs)
