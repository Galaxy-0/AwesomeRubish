"""Finite-resource D3 search primitives; no native-success claim.

Units are normalized full special gauge. Default costs are the local 11.3.0
sparse overrides divided by Zipcaster capacity (1.5), with the natural drain
confirmed independently by D3 hint native records. Costs occur at emission
(hook/light) or throughout charging (full); reserving the whole action up front
is conservative for feasibility. Return is mandatory, with unknown hit risk.
"""
from dataclasses import dataclass
from functools import lru_cache
import math

@dataclass(frozen=True)
class Gauge:
    capacity:float=1.5
    natural_ink_per_second:float=.15
    hook_ink:float=.04
    light_ink:float=.052
    full_ink:float=.117
    return_frames:int=96
    @property
    def drain(self):return self.natural_ink_per_second/self.capacity/60
    def cost(self,frames,*,hooks=0,lights=0,fulls=0):
        if frames<0 or min(hooks,lights,fulls)<0:raise ValueError('negative budget expenditure')
        return frames*self.drain+(hooks*self.hook_ink+lights*self.light_ink+fulls*self.full_ink)/self.capacity
    def exhaust(self,events,budget=1.):
        """First zero budget present, including charge costs spread over frames.

        events: (frame, normalized extra cost), no double-counting natural drain.
        Returns gauge per-frame and mandatory return interval, never invulnerability.
        """
        costs={}
        for t,c in events:
            if t<0 or c<0:raise ValueError('invalid expenditure')
            costs[t]=costs.get(t,0.)+c
        trajectory=[];t=0
        while budget>1e-10:
            budget=max(0.,budget-self.drain-costs.get(t,0.));trajectory.append(budget);t+=1
            if t>36000:raise ValueError('invalid draining budget')
        return dict(gauge=trajectory,zero_frame=t-1,return_end_frame=t-1+self.return_frames,return_damage_rule='unknown')

@dataclass(frozen=True)
class Action:
    id:str
    node:int
    destination:int
    frames:int
    hook:int=0
    light:int=0
    full:int=0
    target:int=-1
    # One probability per finite defender behavior, conditional on arriving alive.
    kill:tuple=(0.,)
    survival:tuple=(1.,)

def optimize(actions,start,targets,*,gauge=Gauge(),budget=1.,quantum=.001,mode='expected',behavior_weights=None):
    """Exact finite stochastic DP on (node, remaining resource, killed mask).

    A target is rewarded at most once. Kill/no-kill branches update its mask;
    survival gates continuation. Thus expectation can exceed one kill without
    treating repeated attempts on the same enemy as additional kills. Kill and
    survival dependence is NOT independently assumed: to keep the primitive
    explicit, action inputs must supply a common continuation survival on both
    kill branches. Richer native-conditioned joint outcomes need a new schema.
    `worst` lets the defender select behavior anew at every action, a lower
    bound for choosing one fixed behavior for the whole sequence.
    Resource rounding is upward, never invents gauge. Both move and attacks
    strictly cost resource, so cycles terminate. Not a continuous global proof.
    """
    if mode not in ('expected','worst'):raise ValueError('unknown objective')
    if not 0<quantum<=budget or targets<0:raise ValueError('invalid finite budget')
    bynode={};behaviors=max((len(a.kill)for a in actions),default=1)
    weights=behavior_weights or [1/behaviors]*behaviors
    if len(weights)!=behaviors or any(x<0 for x in weights)or abs(sum(weights)-1)>1e-8:raise ValueError('invalid behavior prior')
    for a in actions:
        if len(a.kill)!=behaviors or len(a.survival)!=behaviors or any(not 0<=p<=1 for p in (*a.kill,*a.survival)):raise ValueError('invalid conditional probability')
        if not -1<=a.target<targets:raise ValueError('invalid target')
        c=max(1,math.ceil((gauge.cost(a.frames,hooks=a.hook,lights=a.light,fulls=a.full)-1e-12)/quantum))
        bynode.setdefault(a.node,[]).append((a,c))
    policy={}
    @lru_cache(None)
    def value(node,remaining,mask):
        best=0.;choice=None
        for a,c in bynode.get(node,[]):
            if c>=remaining:continue # Reserve positive gauge until the action completes.
            if a.target>=0 and mask&(1<<a.target):continue
            missed=value(a.destination,remaining-c,mask)
            hit=value(a.destination,remaining-c,mask|(1<<a.target))if a.target>=0 else missed
            scores=[]
            for p,s in zip(a.kill,a.survival):
                scores.append((p if a.target>=0 else 0.)+s*(p*hit+(1-p)*missed))
            score=min(scores)if mode=='worst'else sum(w*x for w,x in zip(weights,scores))
            if score>best+1e-12:best=score;choice=a.id
        if choice:policy[(node,remaining,mask)]=choice
        return best
    units=math.floor(budget/quantum+1e-10);score=value(start,units,0)
    return dict(expected_kills=score,first_action=policy.get((start,units,0)),states=value.cache_info().currsize,resource_quantum=quantum,mode=mode,certified_scope='Finite supplied conditional outcomes only; native transition/calibration required',policy=policy)
