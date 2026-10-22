"""Exact finite reverse lower bounds + lazy cost-ordered route enumeration.

No ranked start/hook subset or beam cap. Combat is a callback over complete
paths: a cheap losing path cannot suppress a more expensive winning path.
Caller time limits MUST report unresolved, never unreachable/zero probability.
"""
import heapq,math
import numpy as np

def grade(remaining):
 if remaining<=1e-10:return'unreachable'
 return'stable'if remaining>.3 else'normal'if remaining>=.1 else'extreme'
class Reverse:
 def __init__(self,sources,destinations,costs,ground_count,wall_count,terminals,max_hooks=3,prefix_check=None):
  self.prefix_check=prefix_check
  self.sources=np.asarray(sources,int);self.destinations=np.asarray(destinations,int);self.costs=np.asarray(costs,float);self.ground_count=ground_count;self.wall_count=wall_count;self.max_hooks=max_hooks;self.terminals=terminals
  if not 1<=max_hooks<=3:raise ValueError('one to three hooks')
  if not(len(self.sources)==len(self.destinations)==len(self.costs))or(np.array(self.costs)<=0).any():raise ValueError('positive edge costs required')
  n=ground_count+wall_count
  if np.any(self.sources<0)or np.any(self.sources>=n)or np.any(self.destinations<0)or np.any(self.destinations>=wall_count):raise ValueError('invalid graph endpoint')
  self.adj=[[]for _ in range(n)];self.byterminal=[[]for _ in range(n)]
  for i,src in enumerate(self.sources):self.adj[src].append(i)
  base=np.full(n,np.inf)
  for i,t in enumerate(terminals):
   node=t['node'] if t.get('ground',False) else ground_count+t['node']
   limit=ground_count if t.get('ground',False) else wall_count
   if not 0<=t['node']<limit or t['cost']<0:raise ValueError('invalid terminal')
   self.byterminal[node].append(i);base[node]=min(base[node],t['cost'])
  self.lower=[base]
  for depth in range(1,max_hooks+1):
   candidate=self.costs+self.lower[-1][ground_count+self.destinations];value=base.copy();np.minimum.at(value,self.sources,candidate);self.lower.append(value)
 def candidates(self,start,budget=1.):
  if not 0<=start<self.ground_count:raise ValueError('start is a declared ground node')
  lower=self.lower[self.max_hooks][start]
  if not lower<budget-1e-10:return
  # lower_bound,type,node,remaining_hooks,spent,edges,terminal_index
  queue=[(lower,0,start,self.max_hooks,0.,(),-1)]
  while queue:
   bound,kind,node,left,spent,path,index=heapq.heappop(queue)
   if bound>=budget-1e-10:continue
   if kind==1:yield dict(edges=path,terminal=index,cost=spent,remaining=budget-spent,grade=grade(budget-spent));continue
   if path and self.prefix_check is not None and not self.prefix_check(path):continue
   for ti in self.byterminal[node]:
    cost=spent+self.terminals[ti]['cost']
    if cost<budget-1e-10:heapq.heappush(queue,(cost,1,node,left,cost,path,ti))
   if not left:continue
   for edge in self.adj[node]:
    nxt=self.ground_count+self.destinations[edge];cost=spent+self.costs[edge];lower=cost+self.lower[left-1][nxt]
    if lower<budget-1e-10:heapq.heappush(queue,(lower,0,nxt,left-1,cost,(*path,edge),-1))
