"""Empirical first-launch model, fitted from an explicitly measured P0 trace.

Autopilot includes the measured launch drive after initial floor contact.
Ordinary collision, support and inertia take over after this finite phase.
No post-launch native state is injected. Non-neutral contact steering is only
an approximation and does not identify general slope/prop collision.
Respawn launcher readiness is a separate, still-measured obligation.
"""
import json
import math
import numpy as np


class OpeningModel:
    def __init__(self,data):
        if data.get('schema')!='sim.opening.v1':raise ValueError('opening schema')
        self.data=data

    @classmethod
    def load(cls,path):return cls(json.loads(path.read_text()))

    def point(self,stage,side,frame):
        row=self.data['stages'][str(stage)]
        knots=np.asarray(row['knots'])
        p=np.array([np.interp(frame,knots[:,0],knots[:,j]) for j in (1,2,3)])
        if side:p[[0,2]]*=-1
        return p

    def initialize(self,env):
        for i,p in enumerate(env.players):
            p.position=self.point(env.stage_id,i^env.swap,0)
            p.grounded=False;p.squid=False;p.velocity[:]=0
            p.opening_delta[:]=0

    def advance(self,env,i,action):
        row=self.data['stages'][str(env.stage_id)]
        if env.frame>row['end_frame']:return False
        p=env.players[i];side=i^env.swap
        before=p.position.copy()
        if env.frame>self.data['steer_start']:
            # The current P0 excites forward .85 only. Quartic amplitude is
            # shared with the independently identified ordinary human input;
            # lateral/other flight amplitudes are explicitly unvalidated.
            from .identify import response
            x,z=response(np.asarray(action['sticks'][:2]),0.,4.,'radial')
            direction=np.array([-x*math.cos(p.yaw)+z*math.sin(p.yaw),x*math.sin(p.yaw)+z*math.cos(p.yaw)])
            p.opening_delta+=direction*self.data['steer_speed']
        p.position=self.point(env.stage_id,side,env.frame)
        p.position[[0,2]]+=p.opening_delta
        p.velocity[:]=p.position-before
        p.grounded=env.frame>=row.get('ground_frame',row['end_frame']+1);p.submerged=False
        p.squid=row['squid_start']<=env.frame<row['squid_end']
        p.previous=list(action['buttons'])
        return True
