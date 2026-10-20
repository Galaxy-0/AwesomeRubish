"""Bravo v1: return from spawn, paint lanes, and contest at Stamper range.

Uses only fresh own feedback, visible enemies and the public static atlas.
A one-present cadence preserves A6's charge/release input boundaries.
"""
import math
from atlas import MapAtlas
from skills import Skills, aim_at, neutral, own_state, wrap
from stamper import FastTurn, PredictiveAim, charge_slash, emerge_charge, light_combo


class Bravo:
    def __init__(self, obs):
        self.match = obs['match_id']
        self.atlas = MapAtlas.load(obs['stage_id'])
        # Static spatial buckets bound local ground checks; never live ink.
        self.buckets = {}
        for i, p in enumerate(self.atlas.points):
            self.buckets.setdefault((math.floor(p[0]/4), math.floor(p[2]/4)), []).append(i)
        high = self.atlas.region('central_high')
        lanes = [self.atlas.region('west_lane'), self.atlas.region('east_lane')]
        lanes.sort(key=lambda q: -math.hypot(q[0]-high[0], q[2]-high[2]))
        self.targets = (lanes[0], self.atlas.region('center'), lanes[1],
                        self.atlas.region('center'), high, self.atlas.region('center'))
        self.target_index = 0
        self.turn = FastTurn()
        self.aim = PredictiveAim(max_lead_frames=60)
        self.last_light = self.last_full = -1000
        self.full_enemy = self.enemy_id = None
        self.fight_start = None
        self.fight_pause_until = -1
        self.last_position = None
        self.was_dead = False
        self.landing = True
        self.refill_start = None
        self.refill_cooldown = -1
        self.refill_patch = -1000
        self.reset_navigation()

    def reset_navigation(self):
        self.nav = Skills(self.atlas)
        self.plan = None
        self.in_combat = False
        self.fight_start = None
        self.fight_pause_until = -1
        self.full_enemy = None
        self.dwell_start = None
        self.jump_until = -1

    def ground(self, p):
        bx, bz = math.floor(p[0]/4), math.floor(p[2]/4)
        candidates = [i for x in range(bx-1, bx+2) for z in range(bz-1, bz+2)
                      for i in self.buckets.get((x, z), ())]
        if not candidates:
            return None
        return min(candidates, key=lambda i: (p[0]-self.atlas.points[i][0])**2 +
                   4*(p[1]-self.atlas.points[i][1])**2 + (p[2]-self.atlas.points[i][2])**2)

    @staticmethod
    def move_vector(own, q, amplitude=.65):
        p = own['position']; yaw = own['view_yaw']
        dx, dz = q[0]-p[0], q[2]-p[2]
        x = -dx*math.cos(yaw)+dz*math.sin(yaw)
        y = dx*math.sin(yaw)+dz*math.cos(yaw)
        scale = amplitude/max(.001, abs(x), abs(y))
        scale = min(scale, .85/max(.001, math.hypot(x, y)))
        return [x*scale, y*scale]

    def safe_step(self, own, enemy, frame):
        """Small reversible walking edges only; no blind strafe off a ledge."""
        p = own['position']; i = self.ground(p)
        if i is None or math.dist(p, self.atlas.points[i]) > .85:
            return [0., 0.]
        dx, dz = enemy[0]-p[0], enemy[2]-p[2]
        d = max(.01, math.hypot(dx, dz))
        side = 1 if frame//90 % 2 else -1
        away = 1.4 if d < 8 or (own.get('hp') or 1.) < .55 else .15
        desired = (-away*dx/d+side*dz/d, -away*dz/d-side*dx/d)
        choices = []
        for j in self.atlas.edges[i]:
            q = self.atlas.points[j]
            if i not in self.atlas.edges[j] or self.atlas.edge_kind(i, j) != 'walk':
                continue
            if abs(q[1]-p[1]) > .25 or not .35 < math.dist(p, q) < 1.9:
                continue
            vx, vz = q[0]-p[0], q[2]-p[2]
            score = (vx*desired[0]+vz*desired[1])/max(.01, math.hypot(vx, vz))
            choices.append((score, q))
        if not choices or max(choices)[0] <= .15:
            return [0., 0.]
        return self.move_vector(own, max(choices)[1], .6)

    def spawn_action(self, obs):
        """R0's 43 deaths all ended here. Launch using ZR, never fake alive."""
        own = obs['own']; p = own.get('position'); sample = own.get('sample_frame')
        if p is None or sample is None or not 0 <= obs['frame']-sample <= 8:
            return neutral()
        if own['public']['alive'] is not True:
            if not self.was_dead:
                self.reset_navigation()
                self.aim = PredictiveAim(max_lead_frames=60)
                self.refill_start = None
            self.was_dead = True
            self.landing = True
            a = neutral()
            near_launcher = any(math.dist(p, s['launch_locator']) < 8
                                for s in self.atlas.spawns.values())
            # Fresh own HP and the public launcher coordinate distinguish the
            # normal respawn UI transition from an ordinary dead observation.
            if near_launcher and own.get('hp') is not None and own['hp'] > .9:
                a['buttons'][0] = int(obs['frame'] % 30 == 0)
            return a
        if self.was_dead:
            self.was_dead = False
            self.reset_navigation()
        if self.last_position is not None and math.dist(p, self.last_position) > 15:
            self.reset_navigation()
            self.landing = True
        self.last_position = tuple(p)
        if self.landing:
            i = self.ground(p)
            if i is None or abs(p[1]-self.atlas.points[i][1]) > 1.2:
                return neutral()
            self.landing = False
            self.reset_navigation()
        return None

    def refill(self, obs, enemy):
        own = obs['own']; frame = obs['frame']; ink = own.get('ink')
        if ink is None:
            return None
        if self.refill_start is None and self.plan is None and frame >= self.refill_cooldown and ink < .17:
            self.refill_start = frame
            self.plan = None
        if self.refill_start is None:
            return None
        if ink >= .82 or frame-self.refill_start >= 240:
            self.refill_start = None
            self.refill_cooldown = frame+60  # v0 restarted immediately after timeout
            return None
        a = neutral(); a['buttons'][1] = 1
        if enemy is not None and math.dist(own['position'], enemy['position']) < 13:
            a['sticks'][:2] = self.safe_step(own, enemy['position'], frame)
        # ZL on an unknown tile is not proof of recovery. Try one floor swing
        # after a short wait if there is enough ink, then attempt submergence.
        if own.get('submerged') is not True and frame-self.refill_start > 35 and \
                ink > .06 and frame-self.refill_patch >= 60:
            yaw = own['view_yaw']; p = own['position']
            q = (p[0]+2.5*math.sin(yaw), p[1], p[2]+2.5*math.cos(yaw))
            sight = aim_at(obs, q)
            if sight.done:
                sight.action['buttons'][0] = 1
                self.refill_patch = frame
            return sight.action
        return a

    def combat(self, obs, enemy):
        own = obs['own']; frame = obs['frame']
        if enemy is None and self.enemy_id is not None:
            # Notify the predictor even while a macro is finishing. Otherwise
            # a brief occlusion inside a charge could bridge two samples.
            self.aim.aim(obs, self.enemy_id, fast=True)
        if self.plan is not None:
            result = self.plan.tick(obs)
            if not result.done:
                if enemy is not None:
                    hold = self.plan.segments[0][1]
                    self.aim.windup = max(0, hold-(frame-self.plan.start))+6 \
                        if result.phase == 'charge' else 6
                    track = self.aim.aim(obs, enemy['public']['player_id'], fast=True)
                    if track.status != 'target_unavailable':
                        result.action['sticks'][2:] = track.action['sticks'][2:]
                        result.action['gyro'] = track.action['gyro']
                    if result.phase in ('recover_move', 'light_recovery', 'after_move'):
                        result.action['sticks'][:2] = self.safe_step(own, enemy['position'], frame)
                return result.action
            self.plan = None
        if enemy is None:
            return None
        distance = math.dist(own['position'], enemy['position'])
        if distance > 20.2:
            self.aim.previous = None
            self.aim.velocity = (0., 0., 0.)
            return None
        # Four seconds without ending a medium-range exchange is enough time
        # to have attempted several strikes. Resume map coverage briefly;
        # close threats still take priority. No hit or enemy HP is invented.
        if frame < self.fight_pause_until and distance > 9:
            return None
        if self.enemy_id != enemy['public']['player_id'] or self.fight_start is None:
            self.fight_start = frame
        if frame-self.fight_start >= 240 and distance > 9 and (own.get('hp') or 0) > .55:
            self.fight_pause_until = frame+90
            self.fight_start = None
            return None
        self.enemy_id = enemy['public']['player_id']
        self.aim.windup = 6
        sight = self.aim.aim(obs, self.enemy_id, fast=True)
        if sight.status == 'target_unavailable':
            return None
        p = own['position']; target = self.aim.target
        yaw_error = abs(wrap(math.atan2(target[0]-p[0], target[2]-p[2])-own['view_yaw']))
        pitch = math.atan2(target[1]-p[1]-1.1, max(.05, math.hypot(target[0]-p[0], target[2]-p[2])))
        pitch_error = abs(own['view_pitch']-max(-.9, min(.9, pitch)))
        calibrated = self.aim.turner.gain is not None or self.aim.turner.fallback
        # Align, then track throughout charge; no coincidence of an exact aim
        # threshold and an unrelated frame%36 fire window as in v0.
        if calibrated and yaw_error < .12 and pitch_error < .08 and (own.get('ink') or 0) >= .12:
            finisher = self.full_enemy == self.enemy_id and frame-self.last_full < 95 and distance < 17
            if distance < 4.5 or finisher:
                self.plan = light_combo(obs, count=1, period=30, after_frames=1)
                self.full_enemy = None
            else:
                self.plan = emerge_charge(obs, hold_frames=30, after_frames=22) \
                    if own.get('submerged') is True else charge_slash(obs, hold_frames=24, after_frames=22)
                self.last_full = frame
                self.full_enemy = self.enemy_id
            return self.plan.tick(obs).action
        if calibrated and yaw_error < .25:
            sight.action['sticks'][:2] = self.safe_step(own, enemy['position'], frame)
        return sight.action

    def lookahead(self, p):
        total = 0.; previous = p
        for q in self.nav.path[self.nav.index:]:
            total += math.hypot(q[0]-previous[0], q[2]-previous[2])
            if total >= 5:
                return q
            previous = q
        return self.nav.path[-1] if self.nav.path else self.targets[self.target_index]

    def patrol(self, obs):
        own = obs['own']; frame = obs['frame']; p = own['position']
        route = self.nav.move_to(obs, self.targets[self.target_index])
        if route.status == 'blocked':
            self.target_index = (self.target_index+1) % len(self.targets)
            self.reset_navigation()
            # Bounded physical recovery instead of cycling neutral targets
            # forever, as v0 did in a lower Yagara pocket.
            i = self.ground(p); a = neutral()
            if i is not None:
                a['sticks'][:2] = self.move_vector(own, self.atlas.points[i])
                a['buttons'][4] = 1
            return a
        a = route.action
        if route.done:
            if self.dwell_start is None:
                self.dwell_start = frame
            elapsed = frame-self.dwell_start
            if elapsed >= 90:
                self.target_index = (self.target_index+1) % len(self.targets)
                self.dwell_start = None
                return neutral()
            angle = (elapsed//30)*math.pi/3
            q = (p[0]+5*math.sin(angle), p[1], p[2]+5*math.cos(angle))
        else:
            self.dwell_start = None
            if route.status in ('unavailable', 'replanning'):
                return a
            q = self.lookahead(p)
        sight = self.turn.aim(obs, q)
        a['sticks'][2:] = sight.action['sticks'][2:]
        a['gyro'] = sight.action['gyro']
        if route.status == 'recovering_jump':
            self.jump_until = frame+12  # retain A4's tested B hold duration
        if frame < self.jump_until:
            a['buttons'][4] = 1
        yaw_error = abs(wrap(math.atan2(q[0]-p[0], q[2]-p[2])-own['view_yaw']))
        if frame-self.last_light >= 30 and yaw_error < .65 and not a['buttons'][4] \
                and (own.get('ink') or 0) > .06:
            a['buttons'][0] = 1
            self.last_light = frame
        return a

    def act(self, obs):
        spawn = self.spawn_action(obs)
        if spawn is not None:
            return spawn
        own = own_state(obs)
        if own is None or own.get('view_yaw') is None or own.get('view_pitch') is None:
            return neutral()
        frame = obs['frame']
        enemy = next((e for e in obs['enemies'] if e.get('visible') is True and
                      e.get('position') is not None and e.get('sample_frame') is not None and
                      0 <= frame-e['sample_frame'] <= 8), None)
        recovery = self.refill(obs, enemy)
        if recovery is not None:
            return recovery
        fight = self.combat(obs, enemy)
        if fight is not None:
            self.in_combat = True
            return fight
        if self.in_combat:
            # A fight may have displaced us or consumed the stall timer. Plan
            # again from the actual foot position, not a pre-fight waypoint.
            self.nav = Skills(self.atlas)
            self.dwell_start = None
            self.in_combat = False
        return self.patrol(obs)


controller = None


def act(obs):
    global controller
    if controller is None or controller.match != obs['match_id']:
        controller = Bravo(obs)
    return controller.act(obs)
