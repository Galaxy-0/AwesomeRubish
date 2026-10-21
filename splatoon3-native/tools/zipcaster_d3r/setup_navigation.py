"""Fixture-only static projection for pre-R placement, ordinary stick movement.

A close overlay/decal can be nearest yet belong to another graph component.
Project to a node able to reach the fixed goal, only within2 atlas cells.
Never patches arena navigation, live pose, HP, enemy observations or combat.
"""
import copy,math
from types import MethodType

def route_view(atlas,goal):
    target=atlas.nearest(goal);reverse=[[]for _ in atlas.points]
    for i,neighbors in enumerate(atlas.edges):
        for j in neighbors:reverse[j].append(i)
    todo=[target];allowed={target}
    for i in todo:
        for j in reverse[i]:
            if j not in allowed:allowed.add(j);todo.append(j)
    view=copy.copy(atlas)
    def nearest(self,position,swim=False):
        pool=[i for i in allowed if not swim or self.swimmable[i]]
        if not pool:raise ValueError('fixture goal component has no valid form node')
        n=min(pool,key=lambda i:sum((a-b)**2*(4 if k==1 else 1)for k,(a,b)in enumerate(zip(position,self.points[i]))))
        if math.dist(position,self.points[n])>2*self.resolution:raise ValueError('fixture cannot project across distant/unreachable ground')
        return n
    view.nearest=MethodType(nearest,view);return view,len(allowed)

def place(lab,goals):
    original=lab.atlas
    for n,goal in goals.items():
        view,count=route_view(original,goal);lab.atlas=view
        try:
            lab.navigate({n:goal},'ideal-retry-component-'+str(n))
            lab.result.setdefault('setup_projection',[]).append(dict(player=n,goal=goal,reachable_to_goal_nodes=count,method='static directed reverse reach, max2 cells; ordinary inputs only'))
        finally:lab.atlas=original
