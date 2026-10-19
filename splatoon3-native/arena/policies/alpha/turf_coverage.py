"""Public-geometry coverage goals and OWN route/paint-attempt memory.

The counters below are effort estimates, never a live ink map or scored area.
One bounded graph search chooses a reachable fresh patch; no fixed center loop.
"""
from collections import defaultdict
import heapq
import math


def cell(p):
    return (math.floor(p[0] / 7), round(p[1] / 3), math.floor(p[2] / 7))


class Coverage:
    def __init__(self, atlas, nav):
        self.atlas, self.nav = atlas, nav
        self.visits, self.attempts = defaultdict(float), defaultdict(float)
        self.last_cell = None
        self.last_visit = self.last_shot = -10000
        self.cooldown = {}
        self.goal = self.goal_node = None
        self.started = self.deadline = 0
        self.wait_started = None
        self.base = self.axis = None
        self.axis_length = 1.
        self.selections = []
        self.floor_index = defaultdict(list)
        groups = defaultdict(list)
        for i, p in enumerate(atlas.points):
            self.floor_index[round(p[0]), round(p[2])].append(i)
            flat = sum(abs(atlas.points[j][1] - p[1]) < .4 for j in atlas.edges[i])
            if atlas.swimmable[i] and flat >= 2 and len(atlas.edges[i]) >= 3:
                groups[cell(p)].append((i, flat))
        self.candidates = []
        self.patch_size = {}
        for key, nodes in groups.items():
            cx, cz = (key[0] + .5) * 7, (key[2] + .5) * 7
            i, _ = max(nodes, key=lambda v: 2 * min(4, v[1]) -
                       .12 * ((atlas.points[v[0]][0] - cx)**2 +
                              (atlas.points[v[0]][2] - cz)**2))
            self.candidates.append(i)
            self.patch_size[i] = len(nodes)

    def set_home(self, launch):
        self.base = min((self.atlas.region('alpha_base'), self.atlas.region('bravo_base')),
                        key=lambda p: math.hypot(p[0]-launch[0], p[2]-launch[2]))
        center = self.atlas.region('center')
        dx, dz = center[0]-self.base[0], center[2]-self.base[2]
        self.axis_length = max(1., math.hypot(dx, dz))
        self.axis = (dx/self.axis_length, dz/self.axis_length)

    def relaunch(self, frame):
        self.wait_started = frame
        self.goal = self.goal_node = None
        self.nav.target = None

    def waiting(self, obs):
        if self.wait_started is None:
            return False
        p = obs['own']['position']
        q = self.atlas.points[self.atlas.nearest(p)]
        if (obs['frame']-self.wait_started < 180 and
                (abs(p[1]-q[1]) > .6 or math.hypot(p[0]-q[0], p[2]-q[2]) > 1.5)):
            return True
        self.wait_started = None
        return False

    def observe(self, obs):
        p, f = obs['own']['position'], obs['frame']
        key = cell(p)
        if key != self.last_cell or f-self.last_visit >= 90:
            self.visits[key] += 1. if key != self.last_cell else .25
            self.last_cell, self.last_visit = key, f

    def note_paint(self, obs, action, target):
        # This records only an intended ground shot, not that it landed/lasted.
        if action['buttons'][0] and target is not None and obs['frame']-self.last_shot >= 30:
            p = obs['own']['position']
            yaw = math.atan2(target[0]-p[0], target[2]-p[2])
            error = math.atan2(math.sin(yaw-obs['own']['view_yaw']),
                               math.cos(yaw-obs['own']['view_yaw']))
            if abs(error) < .4:
                self.attempts[cell(target)] += 1.
                self.last_shot = obs['frame']

    def fresh(self, key):
        return 1. / (1. + .65*self.visits[key] + .45*self.attempts[key])

    def progress(self, p):
        if self.base is None:
            return .8, 0.
        x, z = p[0]-self.base[0], p[2]-self.base[2]
        return ((x*self.axis[0]+z*self.axis[1])/self.axis_length,
                abs(x*self.axis[1]-z*self.axis[0]))

    def choose(self, obs):
        p, f = obs['own']['position'], obs['frame']
        remaining = obs.get('remaining_seconds')
        remaining = remaining if remaining is not None else 90.
        # Conservative world units / game second; shorten late travel.
        horizon = min(48., max(9., (remaining-5)*.8))
        start = self.atlas.nearest(p)
        costs, lengths, jumps = {start: 0.}, {start: 0.}, {start: 0}
        queue = [(0., start)]
        # Bounds and penalties are geometry, not assumptions about enemy ink.
        while queue:
            cost, n = heapq.heappop(queue)
            if cost > costs[n] or cost > horizon:
                continue
            a = self.atlas.points[n]
            for j in self.atlas.edges[n]:
                if self.nav.blocked_edges.get((n, j), -1) > f:
                    continue
                b = self.atlas.points[j]
                distance = math.dist(a, b)
                jump = self.atlas.edge_kind(n, j) == 'jump'
                value = cost + distance + 2.5*jump + 5*max(0., a[1]-b[1]-.6)
                if value > horizon or value >= costs.get(j, math.inf):
                    continue
                costs[j] = value
                lengths[j] = lengths[n]+distance
                jumps[j] = jumps[n]+jump
                heapq.heappush(queue, (value, j))
        enemies = [e['position'] for e in obs['enemies']
                   if e.get('visible') is True and e.get('position') is not None]
        best, best_score = None, -math.inf
        for n in self.candidates:
            if n not in costs or self.cooldown.get(n, -1) > f:
                continue
            q = self.atlas.points[n]
            if math.hypot(q[0]-p[0], q[2]-p[2]) < 4.5:
                continue
            progress, lateral = self.progress(q)
            if self.base is not None and not (-.04 <= progress <= 1.6 and lateral <= 29):
                continue
            key = cell(q)
            neighbors = [(key[0]+x, key[1], key[2]+z)
                         for x, z in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            score = (8*self.fresh(key) + .5*sum(self.fresh(k) for k in neighbors)
                     + min(1., self.patch_size[n]/25) + 1.2*min(1.3, progress)
                     - .16*costs[n])
            if remaining > 125 and .05 < progress < .65:
                score += 1.4  # fresh home ground is available without a death
            if enemies:
                distance = min(math.dist(q, e) for e in enemies)
                score -= 3*max(0., 1-distance/20)
            if score > best_score:
                best, best_score = n, score
        # A fallen player can still paint their CURRENT directed component.
        # A tiny component gets a reachable local node, never an impossible
        # central label over and over. This does not promise a route upstairs.
        if best is None:
            local = [n for n in costs if costs[n] >= 2 and self.cooldown.get(n, -1) <= f]
            if local:
                best = max(local, key=lambda n: 5*self.fresh(cell(self.atlas.points[n])) +
                           min(8., lengths[n])*.2 - .1*costs[n])
        if best is None:
            self.goal = self.goal_node = None
            return False
        self.goal_node, self.goal = best, self.atlas.points[best]
        self.started = f
        self.deadline = f + max(360, min(1800, int(lengths[best]/.04)+240))
        self.nav.target = None
        self.selections.append((f, best, best_score))
        return True

    def move(self, obs):
        from skills import SkillResult, neutral
        f = obs['frame']
        if self.goal is None and not self.choose(obs):
            return SkillResult(neutral(), False, 'local_only')
        result = self.nav.move_to(obs, self.goal)
        if result.done or result.status == 'blocked' or f > self.deadline:
            self.cooldown[self.goal_node] = f + (600 if result.done else 3600)
            self.goal = self.goal_node = None
            if self.choose(obs):
                result = self.nav.move_to(obs, self.goal)
        return result

    def floor_target(self, wanted, height):
        x, z = round(wanted[0]), round(wanted[2])
        nodes = [n for dx in (-1, 0, 1) for dz in (-1, 0, 1)
                 for n in self.floor_index.get((x+dx, z+dz), ())
                 if abs(self.atlas.points[n][1]-height) < .6]
        if not nodes:
            return None
        return self.atlas.points[min(nodes, key=lambda n:
                    (self.atlas.points[n][0]-wanted[0])**2 +
                    (self.atlas.points[n][2]-wanted[2])**2)]
