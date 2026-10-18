"""Public static map atlas. Contains geometry only, never live match state."""
import heapq
import json
import math
from pathlib import Path

STAGES = {1: 'Yunohana', 2: 'District00', 3: 'Yagara'}


class MapAtlas:
    def __init__(self, data):
        if data.get('schema') != 'arena.map.v1':
            raise ValueError('unsupported map atlas')
        self.data = data
        self.points = [tuple(n[:3]) for n in data['nodes']]
        self.swimmable = [bool(n[3]) for n in data['nodes']]
        self.edges = data['edges']
        self.regions = data['regions']
        self.spawns = data['spawns']
        self.resolution = data['resolution']
        if not self.points or len(self.points) != len(self.edges):
            raise ValueError('invalid atlas graph')

    @classmethod
    def load(cls, stage_id):
        name = STAGES[int(stage_id)]
        path = Path(__file__).resolve().parents[2] / 'work/arena/maps' / name / 'navigation.json'
        return cls(json.loads(path.read_text()))

    def nearest(self, position, swim=False):
        candidates = (i for i in range(len(self.points)) if not swim or self.swimmable[i])
        return min(candidates, key=lambda i: sum((a-b)**2 * (4 if j == 1 else 1)
                                                for j, (a,b) in enumerate(zip(position,self.points[i]))))

    def route(self, start, end, swim=False):
        a, b = self.nearest(start,swim), self.nearest(end,swim)
        if math.dist(self.points[b],end) > 2*self.resolution:
            raise ValueError('target is outside the traversable atlas')
        queue = [(0.,a)];cost = {a:0.};prev = {a:None}
        while queue:
            _, p = heapq.heappop(queue)
            if p == b:break
            for q in self.edges[p]:
                if swim and not self.swimmable[q]:continue
                value = cost[p]+math.dist(self.points[p],self.points[q])
                if value >= cost.get(q,math.inf):continue
                cost[q]=value;prev[q]=p
                heapq.heappush(queue,(value+math.dist(self.points[q],self.points[b]),q))
        if b not in prev:raise ValueError('no static route to target')
        result=[];q=b
        while q is not None:result.append(self.points[q]);q=prev[q]
        return list(reversed(result))

    def region(self, name):
        """Named experimental regions, derived from map geometry, not game callouts."""
        return tuple(self.regions[name]['center'])

    def objective(self):
        # Turf has no portable objective entity; central traversable region is
        # a public reference point, not an inferred enemy position.
        return self.region('center')
