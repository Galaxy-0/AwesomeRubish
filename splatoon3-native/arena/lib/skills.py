"""Shared bounded controller primitives; input is allowlisted policy JSON only."""
from dataclasses import dataclass
import math


def neutral():
    return dict(sticks=[0.,0.,0.,0.],gyro=[0.,0.,0.],buttons=[0]*6)


def wrap(angle):return math.atan2(math.sin(angle),math.cos(angle))
def clamp(value,limit):return max(-limit,min(limit,value))


def own_state(obs):
    own=obs['own'];position=own.get('position');sample=own.get('sample_frame')
    if position is None or sample is None or not 0 <= obs['frame']-sample <= 8:
        return None
    if own['public']['alive'] is not True:return None
    return own


@dataclass
class SkillResult:
    action: dict
    done: bool = False
    status: str = 'running'


def aim_at(obs,target,eye_height=1.1,pitch_scale=1.):
    own=own_state(obs)
    if own is None or own.get('view_yaw') is None or own.get('view_pitch') is None:
        return SkillResult(neutral(),False,'unavailable')
    p=own['position'];dx=target[0]-p[0];dz=target[2]-p[2]
    yaw=wrap(math.atan2(dx,dz)-own['view_yaw'])
    desired=clamp(math.atan2(target[1]-p[1]-eye_height,max(math.hypot(dx,dz),.05))*pitch_scale,.9)
    pitch=own['view_pitch']-desired
    action=neutral()
    if abs(yaw)>.035:action['sticks'][2]=-math.copysign(max(.35,min(.7,abs(yaw)*.8)),yaw)
    if abs(pitch)>.025:action['gyro'][0]=clamp(pitch*.16,.12)
    return SkillResult(action,abs(yaw)<=.035 and abs(pitch)<=.025)


def ink_at(obs,target):
    result=aim_at(obs,target)
    if result.status=='unavailable':return result
    own=obs['own']
    if own.get('ink') is not None and own['ink']<.1:
        result.action=neutral();result.action['buttons'][1]=1;result.status='refilling';return result
    if result.done:result.action['buttons'][0]=1
    return result


class Skills:
    def __init__(self,atlas):
        self.atlas=atlas;self.target=None;self.path=[];self.index=0
        self.start_frame=None;self.last_progress=None;self.last_position=None

    def move_to(self,obs,target,swim=False):
        own=own_state(obs)
        if own is None or own.get('view_yaw') is None:return SkillResult(neutral(),False,'unavailable')
        p=own['position'];target=tuple(target);identity=(target,swim)
        if self.target!=identity:
            self.path=self.atlas.route(p,target,swim);self.index=0;self.target=identity
            self.start_frame=self.last_progress=obs['frame'];self.last_position=tuple(p)
        if math.dist(p,target)<.7:return SkillResult(neutral(),True,'arrived')
        if math.dist(p,self.last_position)>.3:
            self.last_progress=obs['frame'];self.last_position=tuple(p)
        if obs['frame']-self.last_progress>180 or obs['frame']-self.start_frame>3600:
            return SkillResult(neutral(),False,'blocked')
        while self.index<len(self.path)-1 and math.hypot(p[0]-self.path[self.index][0],p[2]-self.path[self.index][2])<.8:
            self.index+=1
        q=self.path[self.index];dx=q[0]-p[0];dz=q[2]-p[2];yaw=own['view_yaw']
        x=-dx*math.cos(yaw)+dz*math.sin(yaw);y=dx*math.sin(yaw)+dz*math.cos(yaw)
        norm=max(.001,math.hypot(x,y));a=neutral();a['sticks'][:2]=[.85*x/norm,.85*y/norm]
        if swim:
            if own.get('submerged') is True:
                a['buttons'][1]=1
            else:
                # Unknown ink ahead is never marked swimmable ink. Paint an
                # explicit corridor before trying ZL, using only own feedback.
                aim=ink_at(obs,(q[0],q[1],q[2]));a=aim.action
                if obs['frame']%120>=75:
                    a=neutral();a['buttons'][1]=1;a['sticks'][:2]=[.6*x/norm,.6*y/norm]
        return SkillResult(a)

    def swim_to(self,obs,target):return self.move_to(obs,target,swim=True)
    def aim_at(self,obs,target):return aim_at(obs,target)
    def ink_at(self,obs,target):return ink_at(obs,target)
    def objective(self):return self.atlas.objective()
