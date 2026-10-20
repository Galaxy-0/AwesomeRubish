"""Optional native-calibrated foot splash; base blade grid stays explicit."""
import json


class PaintModel:
    def __init__(self,data):
        if data.get('schema')!='sim.paint.v1':raise ValueError('paint model schema')
        self.data=data
        for name in ('weak_radius','full_radius'):
            if not 0<=data[name]<=8:raise ValueError('foot paint radius')
        for name in ('weak_delay','full_delay'):
            if type(data[name])is not int or not 0<=data[name]<=60:raise ValueError('foot paint delay')

    @classmethod
    def load(cls,path):return cls(json.loads(path.read_text()))

    def release(self,env,owner,full):
        kind='full' if full else 'weak'
        env.paint_scheduled.append((env.frame+self.data[kind+'_delay'],owner,self.data[kind+'_radius']))

    def advance(self,env):
        pending=[]
        for frame,owner,radius in env.paint_scheduled:
            if frame>env.frame:pending.append((frame,owner,radius));continue
            p=env.players[owner]
            if p.alive and p.grounded and radius:
                env._paint(owner,p.position,radius)
                env.events.append(dict(kind='foot_paint',frame=env.frame,player=owner,radius=radius))
        env.paint_scheduled=pending
