"""Alpha v2: paint broadly, keep the attacker in view, and fight while moving.

Round 1 exposed blind retreat, cancelled counterattacks, and camera-relative
walking drift. Only own feedback/current visibility/timed memory/static atlas
enter this rule system. A remembered point is never updated as hidden truth.
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


def rebase_move(action, old_yaw, new_yaw):
    """Keep a cached movement vector fixed in WORLD space as the view turns."""
    a = clone(action)
    x, y = a['sticks'][:2]
    dx = -x * math.cos(old_yaw) + y * math.sin(old_yaw)
    dz = x * math.sin(old_yaw) + y * math.cos(old_yaw)
    a['sticks'][:2] = [-dx * math.cos(new_yaw) + dz * math.sin(new_yaw),
                       dx * math.sin(new_yaw) + dz * math.cos(new_yaw)]
    # Preserve world heading without rotating a slow axis input into the
    # native diagonal dead zone (the A4 controller uses the same principle).
    x, y = a['sticks'][:2]
    norm, dominant = math.hypot(x, y), max(abs(x), abs(y))
    if .01 < dominant < .6:
        scale = min(.65 / dominant, .85 / norm)
        a['sticks'][:2] = [x * scale, y * scale]
    return a


class Alpha:
    def __init__(self, obs):
        self.key = (obs['match_id'], obs['stage_id'])
        self.atlas = MapAtlas.load(obs['stage_id'])
        self.nav = Skills(self.atlas)
        self.escape_nav = Skills(self.atlas)
        high = self.atlas.region('central_high')
        far, near = ('east_lane', 'west_lane') if high[0] < 0 else ('west_lane', 'east_lane')
        self.route = ('central_high', 'center', far, 'center', near, 'center')
        self.leg, self.leg_started = 0, obs['frame']
        self.aim = PredictiveAim(windup_frames=30, max_lead_frames=36)
        self.plan = None
        self.plan_kind = None
        self.charge_frames = 0
        self.followup = False
        self.followup_frame = -10000
        self.fight_started = None
        self.paint_until = -1
        self.refilling = False
        self.retreat_until = -1
        self.retreat_goal = None
        self.evade_cache = self.paint_cache = None
        self.evade_frame = self.paint_frame = -100
        self.evade_yaw = self.paint_yaw = 0.
        self.last_hp = None
        self.last_damage = -10000
        self.threat_position = None
        self.threat_frame = -10000
        self.trail = deque(maxlen=24)
        self.trail_frame = -120
        self.launch = None
        self.dead_since = None
        self.saw_down = False
        self.last_death_position = None
        self.home_anchors = []
        self.home_prepared = False
        self.recovery_targets = deque()
        self.recovery_started = None
        self.recovery_launch = None

    def invalidate(self):
        self.nav.target = None
        self.paint_cache = None

    def visible_enemy(self, obs):
        p = obs['own']['position']
        enemies = [e for e in obs['enemies']
                   if e.get('visible') is True and e.get('position') is not None
                   and e['public'].get('alive') is not False
                   and e.get('sample_frame') is not None
                   and 0 <= obs['frame'] - e['sample_frame'] <= 8]
        return min(enemies, key=lambda e: math.dist(p, e['position'])) if enemies else None

    def memory(self, obs, max_age=240):
        if self.threat_position is not None and 0 <= obs['frame'] - self.threat_frame <= max_age:
            return {'position': self.threat_position}
        return None

    def unavailable(self, obs):
        own = obs['own']
        self.plan = None
        self.plan_kind = None
        self.followup = False
        self.aim.aim(obs, None, fast=False)
        self.invalidate()
        if own['public'].get('alive') is not False:
            return neutral()
        if self.dead_since is None:
            self.dead_since = obs['frame']
        if own.get('hp') is not None and own['hp'] <= .01 and not self.saw_down:
            self.saw_down = True
            if own.get('position') is not None:
                self.last_death_position = tuple(own['position'])
        sample, p = own.get('sample_frame'), own.get('position')
        ready = (sample is not None and 0 <= obs['frame'] - sample <= 8
                 and p is not None and self.launch is not None
                 and math.dist(p, self.launch) < 3
                 and own.get('hp') is not None and own['hp'] >= .99
                 and own.get('ink') is not None and own['ink'] >= .9
                 and obs['frame'] - self.dead_since >= 120)
        a = neutral()
        if ready and obs['frame'] % 30 == 0:
            a['buttons'][0] = 1
        return a

    def prepare_home(self):
        """Spawn -> flank -> center must exist; home drops may be one-way."""
        self.home_prepared = True
        if self.launch is None:
            return
        center = self.atlas.region('center')
        base = min((self.atlas.region('alpha_base'), self.atlas.region('bravo_base')),
                   key=lambda q: horizontal(q, self.launch))
        for side in (-1, 1):
            wanted = (base[0] * .48 + center[0] * .52 + side * 12,
                      base[1] * .48 + center[1] * .52,
                      base[2] * .48 + center[2] * .52)
            q = self.atlas.points[self.atlas.nearest(wanted)]
            try:
                forward = self.atlas.route(base, q)
                back = self.atlas.route(q, center)
            except ValueError:
                continue
            if (sum(math.dist(a, b) for a, b in zip(forward, forward[1:])) <= 90
                    and sum(math.dist(a, b) for a, b in zip(back, back[1:])) <= 90):
                if q not in self.home_anchors:
                    self.home_anchors.append(q)

    def choose_retreat(self, obs, enemy):
        p = obs['own']['position']
        enemy = enemy or self.memory(obs)
        if enemy is not None:
            dx, dz = p[0] - enemy['position'][0], p[2] - enemy['position'][2]
        elif self.launch is not None:
            dx, dz = self.launch[0] - p[0], self.launch[2] - p[2]
        else:
            dx, dz = 0., 1.
        norm = max(.01, math.hypot(dx, dz))
        ux, uz = dx / norm, dz / norm
        candidates = []
        for q in reversed(self.trail):
            if 5 <= horizontal(p, q) <= 16 and abs(p[1] - q[1]) < 1.5:
                candidates.append(q)
                if len(candidates) == 3:
                    break
        # Diagonals and path bends are cover PROXIES, not an LOS assertion.
        for angle in (-.9, .9, 0.):
            vx = ux * math.cos(angle) - uz * math.sin(angle)
            vz = ux * math.sin(angle) + uz * math.cos(angle)
            wanted = (p[0] + 8 * vx, p[1], p[2] + 8 * vz)
            candidates.append(self.atlas.points[self.atlas.nearest(wanted)])
        best, best_score = None, -math.inf
        for q in candidates:
            if abs(q[1] - p[1]) > 1.5:
                continue
            try:
                nodes = self.atlas.plan(p, q)
            except ValueError:
                continue
            path = [self.atlas.points[n] for n in nodes]
            length = sum(math.dist(a, b) for a, b in zip(path, path[1:]))
            if length > 24 or horizontal(p, q) < 3:
                continue
            jumps = sum(self.atlas.edge_kind(a, b) == 'jump' for a, b in zip(nodes[:8], nodes[1:9]))
            bends = 0
            for a, b, c in zip(path, path[1:], path[2:]):
                v, w = (b[0]-a[0], b[2]-a[2]), (c[0]-b[0], c[2]-b[2])
                cosine = (v[0]*w[0] + v[1]*w[1]) / max(.01, math.hypot(*v)*math.hypot(*w))
                bends += cosine < .8
            lateral = abs((q[0] - p[0]) * uz - (q[2] - p[2]) * ux) / max(1., horizontal(p, q))
            gain = (horizontal(q, enemy['position']) - horizontal(p, enemy['position'])) if enemy else 0.
            score = 2 * gain + 6 * lateral + 2 * min(3, bends) - .35 * length - 8 * jumps
            if score > best_score:
                best, best_score = q, score
        return best or self.atlas.points[self.atlas.nearest((p[0]+6*ux, p[1], p[2]+6*uz))]

    def retreat_motion(self, obs, enemy):
        f, own = obs['frame'], obs['own']
        threat = enemy or self.memory(obs)
        if self.retreat_goal is None:
            self.retreat_goal = self.choose_retreat(obs, threat)
            self.escape_nav.target = None
            self.evade_cache = None
        if self.evade_cache is None or f - self.evade_frame >= 6:
            r = self.escape_nav.move_to(obs, self.retreat_goal)
            if r.status == 'blocked' or (r.done and threat is not None
                                        and horizontal(own['position'], threat['position']) < 22):
                self.retreat_goal = self.choose_retreat(obs, threat)
                self.escape_nav.target = None
                r = self.escape_nav.move_to(obs, self.retreat_goal)
            self.evade_cache, self.evade_frame = clone(r.action), f
            self.evade_yaw = own['view_yaw']
        return rebase_move(self.evade_cache, self.evade_yaw, own['view_yaw'])

    def track(self, obs, enemy):
        if enemy is not None:
            return self.aim.aim(obs, enemy['public']['player_id'], fast=True)
        self.aim.aim(obs, None, fast=False)  # hidden targets have no velocity estimate
        remembered = self.memory(obs)
        if remembered is not None:
            p = remembered['position']
            return self.aim.turner.aim(obs, (p[0], p[1]+1.1, p[2]))
        return None

    def evade(self, obs, enemy):
        """Move away without turning the camera toward the escape destination."""
        own, f = obs['own'], obs['frame']
        a = self.retreat_motion(obs, enemy)
        tracking = self.track(obs, enemy)
        if tracking is not None:
            a['sticks'][2:] = tracking.action['sticks'][2:]
            a['gyro'] = tracking.action['gyro']
        # Try entering previously painted escape ground, then trust ONLY actual
        # submerged feedback. Never keep human-painting forever to the rear.
        if own.get('submerged') is True or (own.get('ink') is not None and own['ink'] < .22) or f % 60 < 18:
            a['buttons'][1] = 1
        return a

    def paint(self, obs):
        f, p = obs['frame'], obs['own']['position']
        if self.recovery_targets and self.recovery_launch is not None:
            # Alive becomes true while the native spawn launcher is airborne.
            # Do not interpret that temporary off-atlas position as a failed
            # route and discard every home target. Feet near the static layer
            # are a readiness proxy, not a private ground-contact signal.
            q = self.atlas.points[self.atlas.nearest(p)]
            if (f - self.recovery_launch < 180
                    and (horizontal(p, q) > 1.5 or abs(p[1] - q[1]) > .6)):
                return neutral()
            self.recovery_launch = None
            self.recovery_started = f
        if self.paint_cache is not None and f - self.paint_frame < 6:
            return rebase_move(self.paint_cache, self.paint_yaw, obs['own']['view_yaw'])
        if self.recovery_targets:
            if self.recovery_started is None:
                self.recovery_started = f
            goal = self.recovery_targets[0]
        else:
            goal = self.atlas.region(self.route[self.leg % len(self.route)])
        move = self.nav.move_to(obs, goal)
        start = self.recovery_started if self.recovery_targets else self.leg_started
        if move.done or move.status == 'blocked' or f - start > 1500:
            if self.recovery_targets:
                self.recovery_targets.popleft()
                self.recovery_started = f if self.recovery_targets else None
                if not self.recovery_targets:
                    self.leg, self.leg_started = 1, f
                goal = self.recovery_targets[0] if self.recovery_targets else self.atlas.region('center')
            else:
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
                target = (p[0]+ux*4+uz*side*1.7, q[1], p[2]+uz*4-ux*side*1.7)
        if target is None:
            angle = (f // 96 % 8) * math.tau / 8
            target = (p[0]+5*math.sin(angle), p[1]-.5, p[2]+5*math.cos(angle))
        aiming = aim_at(obs, target)
        a = move.action
        a['sticks'][2:] = aiming.action['sticks'][2:]
        a['gyro'] = aiming.action['gyro']
        # Keep jumps/large layer transitions free of weapon-induced movement.
        level = not self.nav.path or abs(self.nav.path[self.nav.index][1] - p[1]) < .4
        a['buttons'][0] = int(f % 36 < 12 and level and not a['buttons'][4]
                              and aiming.status != 'unavailable')
        self.paint_cache, self.paint_frame, self.paint_yaw = clone(a), f, obs['own']['view_yaw']
        return a

    def tick_attack(self, obs, enemy, moving):
        f = obs['frame']
        if enemy is None and self.memory(obs, max_age=45) is None:
            self.plan = None
            self.followup = False
            self.aim.aim(obs, None, fast=False)
            return neutral()
        result = self.plan.tick(obs)
        if result.done:
            self.followup = result.status == 'complete' and self.plan_kind == 'charge'
            if self.followup:
                self.followup_frame = f
            self.plan = None
            self.plan_kind = None
            return neutral()
        self.aim.windup = max(0, self.charge_frames - (f - self.plan.start)) + 6
        tracking = self.track(obs, enemy)
        a = result.action
        if tracking is not None:
            a['sticks'][2:] = tracking.action['sticks'][2:]
            a['gyro'] = tracking.action['gyro']
        if moving:
            motion = self.retreat_motion(obs, enemy)
            a['sticks'][:2] = motion['sticks'][:2]
        # No ZL during a committed charge: diving would cancel it.
        return a

    def combat(self, obs, enemy, moving=False):
        f, own = obs['frame'], obs['own']
        self.aim.windup = 6
        aiming = self.track(obs, enemy)
        if aiming is None or self.aim.target is None:
            return neutral()
        p, target = own['position'], self.aim.target
        yaw_error = abs(wrap(math.atan2(target[0]-p[0], target[2]-p[2])-own['view_yaw']))
        desired = max(-.9, min(.9, math.atan2(target[1]-p[1]-1.1, max(.05, horizontal(p, target)))))
        aligned = (aiming.done or yaw_error < .12 and abs(own['view_pitch']-desired) < .09
                   and f - self.fight_started >= 14)
        a = aiming.action
        if not aligned:
            if moving:
                a['sticks'][:2] = self.retreat_motion(obs, enemy)['sticks'][:2]
            return a
        distance = math.dist(p, enemy['position'])
        if distance < 6 or (self.followup and f-self.followup_frame <= 90 and distance < 14):
            self.plan = light_combo(obs, count=1, period=30, after_frames=1)
            self.plan_kind, self.charge_frames = 'light', 0
        elif own.get('submerged') is True:
            self.plan = emerge_charge(obs, hold_frames=30, after_frames=30)
            self.plan_kind, self.charge_frames = 'charge', 30
        else:
            self.plan = charge_slash(obs, hold_frames=24, after_frames=30)
            self.plan_kind, self.charge_frames = 'charge', 24
        self.followup = False
        return self.tick_attack(obs, enemy, moving)

    def act(self, obs):
        own = own_state(obs)
        if own is None:
            return self.unavailable(obs)
        if own.get('view_yaw') is None or own.get('view_pitch') is None:
            self.plan = None
            self.followup = False
            self.aim.aim(obs, None, fast=False)
            return neutral()
        f, p = obs['frame'], own['position']
        if self.launch is None and f < 120 and p[1] > 20:
            self.launch = tuple(p)
        if self.launch is not None and not self.home_prepared:
            self.prepare_home()
        if self.dead_since is not None:
            if self.saw_down and self.last_death_position is not None:
                self.recovery_targets = deque(sorted(self.home_anchors,
                    key=lambda q: horizontal(q, self.last_death_position), reverse=True))
                self.recovery_started = f
                self.recovery_launch = f if self.recovery_targets else None
            self.dead_since, self.saw_down = None, False
            self.refilling = False
            self.followup = False
            self.leg_started = f
            self.retreat_until = -1
            self.retreat_goal = None
            self.threat_position = None
            self.threat_frame = -10000
            self.invalidate()
        enemy = self.visible_enemy(obs)
        if enemy is not None and math.dist(p, enemy['position']) < 24:
            self.threat_position = tuple(enemy['position'])
            self.threat_frame = enemy['sample_frame']
        hp, ink = own.get('hp'), own.get('ink')
        drop = self.last_hp - hp if hp is not None and self.last_hp is not None else 0.
        self.last_hp = hp
        if drop > .02:
            self.last_damage = f
        hurt = hp is not None and hp < .85
        danger = self.memory(obs) is not None or f-self.last_damage < 180
        if (hp is not None and hp < .55) or drop > .15 or (ink is not None and ink < .18 and danger):
            self.retreat_until = max(self.retreat_until, f+120)
        retreating = f < self.retreat_until or (self.refilling and danger)
        moving_fight = retreating or hurt or (enemy is not None and horizontal(p, enemy['position']) < 9)
        # Taking damage changes our movement, not an already committed slash.
        if self.plan is not None:
            return self.tick_attack(obs, enemy, moving_fight)
        distance = math.dist(p, enemy['position']) if enemy is not None else math.inf
        fight_range = 18 if retreating or hurt else 14
        eligible = (enemy is not None and distance < fight_range
                    and abs(p[1]-enemy['position'][1]) < 3.5
                    and (f >= self.paint_until or hurt or distance < 8))
        if eligible and (ink is not None and ink >= .18):
            if self.fight_started is None:
                self.fight_started = f
                self.paint_cache = None
            budget = 240 if self.followup and f-self.followup_frame <= 90 else 180
            if f-self.fight_started < budget or hurt:
                return self.combat(obs, enemy, moving_fight)
            self.paint_until = f+120
        if self.fight_started is not None:
            self.fight_started = None
            self.invalidate()
        if ink is not None:
            if ink < .22:
                self.refilling = True
            target = .70 if horizontal(p, self.atlas.region('center')) < 45 else .85
            if ink >= target:
                self.refilling = False
        if retreating or hurt and danger or self.refilling and danger:
            return self.evade(obs, enemy)
        if self.retreat_goal is not None:
            self.retreat_goal = None
            self.escape_nav.target = None
            self.evade_cache = None
            self.invalidate()
        self.aim.aim(obs, None, fast=False)
        if self.refilling:
            self.invalidate()
            a = neutral()
            a['buttons'][1] = 1
            return a
        if hp is not None and hp > .98 and not danger and f-self.trail_frame >= 120:
            if not self.trail or horizontal(p, self.trail[-1]) > 2:
                self.trail.append(tuple(p))
            self.trail_frame = f
        a = self.paint(obs)
        # Seeing a threat outside our reliable charge range must not make us
        # turn our back to it. Continue the navigation vector while watching;
        # keep the weapon released until combat explicitly accepts the shot.
        # Hidden memory is a fixed point, never a new predicted enemy sample.
        watch_enemy = enemy if distance < 24 else None
        watch = watch_enemy or self.memory(obs, max_age=120)
        if watch is not None and math.dist(p, watch['position']) < 24:
            tracking = self.track(obs, watch_enemy)
            if tracking is not None:
                a['sticks'][2:] = tracking.action['sticks'][2:]
                a['gyro'] = tracking.action['gyro']
            a['buttons'][0] = 0
        return a


agent = None


def act(obs):
    global agent
    if agent is None or agent.key != (obs['match_id'], obs['stage_id']):
        agent = Alpha(obs)
    return agent.act(obs)
