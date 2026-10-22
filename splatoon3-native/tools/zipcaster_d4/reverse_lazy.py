"""Exact lazy terminal resolution; stale optimistic bounds stay admissible."""
import heapq
from tools.zipcaster_d4.reverse_v2 import Reverse,grade


class LazyReverse(Reverse):
    def __init__(self,*args,resolver,**kwargs):
        super().__init__(*args,**kwargs)
        self.resolver=resolver
        self.resolved={}

    def actual(self,index):
        if index not in self.resolved:
            value=self.resolver(index)
            if value is not None and value['cost']<self.terminals[index]['cost']-1e-9:
                raise AssertionError('terminal lower bound exceeded actual cost')
            self.resolved[index]=value
        return self.resolved[index]

    def candidates(self,start,budget=1.):
        lower=self.lower[self.max_hooks][start]
        if not lower<budget-1e-10:return
        queue=[(lower,0,start,self.max_hooks,0.,(),-1)]
        while queue:
            bound,kind,node,left,spent,path,index=heapq.heappop(queue)
            if bound>=budget-1e-10:continue
            if kind==2:
                yield dict(edges=path,terminal=index,cost=spent,remaining=budget-spent,grade=grade(budget-spent))
                continue
            if kind==1:
                term=self.actual(index)
                if term is None:continue
                cost=spent+term['cost']
                if cost<budget-1e-10:heapq.heappush(queue,(cost,2,node,left,cost,path,index))
                continue
            if path and self.prefix_check is not None and not self.prefix_check(path):continue
            for ti in self.byterminal[node]:
                cost=spent+self.terminals[ti]['cost']
                if cost<budget-1e-10:heapq.heappush(queue,(cost,1,node,left,spent,path,ti))
            if not left:continue
            for edge in self.adj[node]:
                nxt=self.ground_count+self.destinations[edge]
                cost=spent+self.costs[edge];lower=cost+self.lower[left-1][nxt]
                if lower<budget-1e-10:heapq.heappush(queue,(lower,0,nxt,left-1,cost,(*path,edge),-1))
