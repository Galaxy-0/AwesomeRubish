"""Static coverage tour, with memory of OUR attempts, not a live paint map.

R3 spent about the same ink as the winner but retraced the central lanes. Here
we score reachable patches by likely fresh coverage per travel cost. Memory
can be wrong after misses or enemy repaint; it is never exposed as turf truth.
"""
import collections
import heapq
import math


def key(p):
    return (math.floor(p[0]/4), math.floor((p[1]+.7)/2.5), math.floor(p[2]/4))


class CoverageTour:
    def __init__(self, atlas):
        self.atlas = atlas
        self.home = None
        self.sign = 1
        self.attempts = collections.defaultdict(float)
        self.visits = collections.Counter()
        self.last_cell = None
        self.goal = None
        self.reserved = {}
        self.bad_edges = {}
        self.events = []
        reverse = [[] for _ in atlas.points]
        for i, edges in enumerate(atlas.edges):
            for j in edges:
                reverse[j].append(i)
        center = atlas.nearest(atlas.region('center'))
        self.returns = {center}
        queue = [center]
        while queue:
            for i in reverse[queue.pop()]:
                if i not in self.returns:
                    self.returns.add(i)
                    queue.append(i)
        groups = collections.defaultdict(list)
        max_y = max(s['ground'][1] for s in atlas.spawns.values())+1
        max_z = max(abs(s['ground'][2]) for s in atlas.spawns.values())+3
        for i in self.returns:
            p = atlas.points[i]
            if not atlas.swimmable[i] or abs(p[0]) > 34 or abs(p[2]) > max_z or p[1] > max_y:
                continue
            flat = sum(abs(atlas.points[j][1]-p[1]) < .25 for j in atlas.edges[i])
            if flat < 3:
                continue
            groups[(math.floor(p[0]/8), math.floor((p[1]+.7)/2.5), math.floor(p[2]/8))].append(i)
        self.candidates = []
        for tile, nodes in sorted(groups.items()):
            x, _, z = tile
            i = min(nodes, key=lambda n: (atlas.points[n][0]-(x*8+4))**2 +
                    (atlas.points[n][2]-(z*8+4))**2)
            samples = tuple(set(key(atlas.points[j]) for j in nodes))
            self.candidates.append((i, tile, samples, min(1.25, len(nodes)/32)))

    def set_home(self, p):
        if self.home is None:
            self.home = min(self.atlas.spawns.values(), key=lambda s: math.dist(p, s['launch_locator']))
            self.sign = 1 if self.home['ground'][2] > 0 else -1

    def observe(self, p):
        cell = key(p)
        if cell != self.last_cell:
            self.visits[cell] += 1
            self.last_cell = cell

    def novelty(self, cell):
        return 1/(1+self.attempts[cell]+.25*self.visits[cell])

    def paint_attempt(self, foot, target):
        # Mark expected local coverage only after a new light input. A missed
        # shot or an unpaintable surface can make this belief too optimistic.
        for p, strength in ((foot, .65), (target, 1.0)):
            for dx, dz in ((0, 0), (-1.7, 0), (1.7, 0), (0, -1.7), (0, 1.7)):
                self.attempts[key((p[0]+dx, p[1], p[2]+dz))] += strength/2

    def active_blocks(self, frame):
        self.bad_edges = {e: until for e, until in self.bad_edges.items() if until > frame}
        return dict(self.bad_edges)

    def obstructed(self, nav, p, frame):
        """Expand an observed blocked direction locally, preserving escape.

        R3 Yagara spent over twenty seconds trying parallel edges at one lip.
        Do not claim new collision geometry: this is temporary failure memory.
        """
        self.bad_edges.update(nav.blocked_edges)
        if not nav.path or nav.index >= len(nav.path):
            return
        q = nav.path[nav.index]
        dx, dz = q[0]-p[0], q[2]-p[2]
        norm = math.hypot(dx, dz)
        if norm < .1:
            return
        for i, a in enumerate(self.atlas.points):
            if abs(a[1]-p[1]) > .4 or math.hypot(a[0]-p[0], a[2]-p[2]) > 2.5:
                continue
            for j in self.atlas.edges[i]:
                b = self.atlas.points[j]
                vx, vz = b[0]-a[0], b[2]-a[2]
                if abs(b[1]-a[1]) < .3 and (vx*dx+vz*dz)/max(.01, math.hypot(vx, vz)*norm) > .65:
                    self.bad_edges[i, j] = frame+1800
        self.events.append(dict(kind='local_obstruction', frame=frame, position=list(p)))
        self.goal = None

    def choose(self, p, start, frame, remaining):
        self.set_home(p)
        blocked = self.active_blocks(frame)
        costs = {start: 0.}
        prev = {start: None}
        queue = [(0., start)]
        # One bounded Dijkstra per new goal; no search or graph read per shot.
        while queue:
            cost, i = heapq.heappop(queue)
            if cost != costs[i] or cost > 65:
                continue
            for j in self.atlas.edges[i]:
                if (i, j) in blocked:
                    continue
                step = math.dist(self.atlas.points[i], self.atlas.points[j])
                if self.atlas.edge_kind(i, j) == 'jump':
                    step += 1.5
                value = cost+step
                if value <= 65 and value < costs.get(j, math.inf):
                    costs[j] = value
                    prev[j] = i
                    heapq.heappush(queue, (value, j))
        frontier = -12 if remaining is None or remaining > 40 else -35
        best = None
        for i, tile, samples, density in self.candidates:
            q = self.atlas.points[i]
            distance = costs.get(i, math.inf)
            if not 5.5 <= distance <= 65 or self.sign*q[2] < frontier:
                continue
            gain = sum(self.novelty(k) for k in samples)/len(samples)
            # Sample the reconstructed path: a long route through fresh floor
            # can be better than a short return to a repeatedly sprayed center.
            j = i; path = []
            while j is not None:
                path.append(j); j = prev[j]
            path_gain = sum(self.novelty(key(self.atlas.points[j])) for j in path[::4])/len(path[::4])
            recency = .18 if self.reserved.get(tile, -1) > frame else 1.
            drop = max(0., p[1]-q[1]-.75)
            score = recency*(2.5*gain*density+1.3*path_gain)/(8+distance+2*drop)
            item = (score, -distance, -i)
            if best is None or item > best[0]:
                best = (item, i, tile, gain, distance)
        if best is None:
            self.goal = self.atlas.region('center')
            return self.goal
        _, i, tile, gain, distance = best
        self.reserved[tile] = frame+1800
        self.goal = self.atlas.points[i]
        self.events.append(dict(kind='goal', frame=frame, position=list(p), target=list(self.goal),
                                expected_novelty=round(gain, 3), route_cost=round(distance, 2)))
        return self.goal
