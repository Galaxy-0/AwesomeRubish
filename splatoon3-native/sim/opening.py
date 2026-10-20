"""Empirical first-launch model, fitted from an explicitly measured P0 trace.

Autopilot includes the measured launch drive after initial floor contact.
Ordinary collision, support and inertia take over after this finite phase.
No post-launch native state is injected. Non-neutral contact steering is only
an approximation and does not identify general slope/prop collision.
Optional respawn readiness/unlock coefficients are interval-censored P0 fits.
Launch requires a fresh ZR edge; no automatic return to a ground anchor.
"""
import json
import math
from pathlib import Path
import numpy as np


class OpeningModel:
    def __init__(self,data):
        if data.get('schema')!='sim.opening.v1':raise ValueError('opening schema')
        if data.get('respawn'):
            r=data['respawn']
            if any(type(r[k])is not int for k in ('ready_delay','unlock_delay')) or not 0<r['ready_delay']<=r['unlock_delay']:
                raise ValueError('respawn timing')
        self.data=data

    @classmethod
    def load(cls,path):return cls(json.loads(Path(path).read_text()))

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
            p.launch_at=0

    def on_death(self,env,i):
        p=env.players[i];r=self.data['respawn']
        p.respawn_ready_at=env.frame+r['ready_delay']
        p.respawn_at=env.frame+r['unlock_delay'];p.launch_at=None
        p.opening_delta[:]=0

    def dead_step(self,env,i,action):
        p=env.players[i];b=action['buttons'];side=i^env.swap
        if env.frame>=p.respawn_ready_at:
            p.position=self.point(env.stage_id,side,0);p.hp=p.ink=1.
            p.velocity[:]=0.;p.grounded=False
            p.yaw=p.heading=math.pi if side==0 else 0.;p.pitch=0.
            if env.frame>=p.respawn_at and b[0] and not p.previous[0]:
                p.alive=True;p.launch_at=env.frame;p.opening_delta[:]=0
                p.cooldown=p.emerge=p.recover_stop=0
                p.protected_until=env.frame+env.rules.spawn_protection_frames
                env.events.append(dict(kind='respawn',frame=env.frame,player=i))
        p.previous=list(b)

    def advance(self,env,i,action):
        row=self.data['stages'][str(env.stage_id)]
        p=env.players[i];side=i^env.swap
        if p.launch_at is None:return False
        frame=env.frame-p.launch_at
        if frame>row['end_frame']:return False
        before=p.position.copy()
        if frame>self.data['steer_start']:
            # The current P0 excites forward .85 only. Quartic amplitude is
            # shared with the independently identified ordinary human input;
            # lateral/other flight amplitudes are explicitly unvalidated.
            from .identify import response
            x,z=response(np.asarray(action['sticks'][:2]),0.,4.,'radial')
            direction=np.array([-x*math.cos(p.yaw)+z*math.sin(p.yaw),x*math.sin(p.yaw)+z*math.cos(p.yaw)])
            p.opening_delta+=direction*self.data['steer_speed']
        p.position=self.point(env.stage_id,side,frame)
        p.position[[0,2]]+=p.opening_delta
        p.velocity[:]=p.position-before
        p.grounded=frame>=row.get('ground_frame',row['end_frame']+1);p.submerged=False
        p.squid=row['squid_start']<=frame<row['squid_end']
        p.previous=list(action['buttons'])
        return True
