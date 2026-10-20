"""Sample/delivery clocks for offline protocol ablations; no native values.

Physics always advances at60. Only past SIMULATED snapshots are projected.
An empirical recording supplies timestamps, not future positions/HP/paint.
This is a conditional protocol reconstruction, not an identified packet model.
"""
from dataclasses import replace
import numpy as np


class RecordedClock:
    def __init__(self, env, stamps):
        self.env = env
        self.stamps = np.asarray(stamps)
        if self.stamps.shape != (env.duration+1,2):raise ValueError('clock shape')
        for role in range(2):
            known=self.stamps[:,role]>=0
            if (self.stamps[known,role]>np.flatnonzero(known)).any():raise ValueError('future sample')
        self.history={}
        self.special_history={}
        self.original_truth=env.truth
        # Prefix boundary has only a past-velocity estimate. Back-propagating
        # that estimate does not query any post-boundary native state.
        truth=self.original_truth()
        for age in range(9):
            f=env.frame-age
            if f<0:break
            players=tuple(replace(p,position=tuple(np.array(p.position)-age*env.players[i].velocity),sample_frame=f)
                          for i,p in enumerate(truth.players))
            self.history[f]=replace(truth,frame=f,players=players)
            self.special_history[f]=[p.special for p in env.players]

    def capture(self):
        truth=self.original_truth()
        self.history[self.env.frame]=truth
        self.special_history[self.env.frame]=[p.special for p in self.env.players]
        for f in list(self.history):
            if f<self.env.frame-128:
                del self.history[f];del self.special_history[f]

    def special(self, role):
        from arena.control_process import OwnSpecial
        stamp=int(self.stamps[self.env.frame,role])
        value=self.special_history.get(stamp)
        return OwnSpecial(f'player_{role}',stamp,value[role] if value is not None else None)

    def truth(self):
        f=self.env.frame;current=self.original_truth();players=[];public=[]
        for role,p in enumerate(current.players):
            stamp=int(self.stamps[f,role])
            past=self.history.get(stamp)
            if stamp<0 or past is None:
                players.append(replace(p,position=None,heading=None,hp=None,ink=None,
                    sample_frame=None,form_squid=None,submerged=None,view_yaw=None,view_pitch=None))
            else:
                players.append(past.players[role])
        for status in current.public_status:
            role=int(status.target.split('_')[-1]);p=players[role]
            public.append(replace(status,alive=p.alive,sample_frame=p.sample_frame if p.sample_frame is not None else f))
        return replace(current,players=tuple(players),public_status=tuple(public))


def from_policy_logs(env, logs):
    stamps=np.full((env.duration+1,2),-1,int)
    for role,rows in enumerate(logs):
        for j,row in enumerate(rows):
            obs=row['observation'];f=obs['frame']
            if f>env.duration:continue
            end=min(rows[j+1]['observation']['frame'] if j+1<len(rows) else env.duration+1,env.duration+1)
            stamp=obs['own']['sample_frame']
            stamps[f:end,role]=-1 if stamp is None else stamp
    return RecordedClock(env,stamps)
