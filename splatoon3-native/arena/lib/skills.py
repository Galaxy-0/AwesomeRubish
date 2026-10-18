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
    def __init__(self,atlas,stall_frames=120,max_replans=3,waypoint_radius=.24):
        if stall_frames<1 or max_replans<1 or not 0<waypoint_radius<.5:raise ValueError('invalid navigation limits')
        self.atlas=atlas;self.stall_frames=stall_frames;self.max_replans=max_replans
        self.waypoint_radius=waypoint_radius;self.target=None;self.path=[];self.nodes=[];self.index=0
        self.blocked_edges={};self.events=[];self.replans=0
        self.start_frame=None;self.last_progress=None;self.last_position=None
        self.jump_sent=False;self.jump_started=None;self.jump_position=None;self.failed=False;self.last_jump_frame=-100000

    def _event(self,kind,frame,p,**details):
        self.events.append(dict(kind=kind,frame=frame,position=list(p),**details))

    def _plan(self,p,target,swim,frame,replan=False):
        if replan:self.replans+=1
        self.blocked_edges={edge:until for edge,until in self.blocked_edges.items() if until>frame}
        try:self.nodes=self.atlas.plan(p,target,swim,self.blocked_edges)
        except ValueError:
            self.nodes=[];self.path=[]
            self._event('no_route',frame,p,replans=self.replans)
            return False
        self.path=[self.atlas.points[i] for i in self.nodes];self.index=0
        # The nearest grid vertex is an A* projection anchor, not a demand to
        # enter its exact centre (which may be inside an omitted small prop).
        # A valid same-layer start cell starts at the measured foot position.
        if math.dist(p,self.path[0])<=.75 and abs(p[1]-self.path[0][1])<.3:self.path[0]=tuple(p)
        self.last_progress=self.start_frame=frame;self.last_position=tuple(p)
        self.jump_sent=False;self.jump_started=None;self.jump_position=None
        self.best_distance=math.hypot(p[0]-self.path[0][0],p[2]-self.path[0][2])
        if replan:self._event('replan',frame,p,replans=self.replans,nodes=len(self.path))
        return True

    def _replan(self,p,target,swim,frame):
        if self.replans>=self.max_replans:
            self.failed=True;self._event('blocked',frame,p,replans=self.replans)
            return SkillResult(neutral(),False,'blocked')
        if len(self.nodes)>1:
            a=self.nodes[max(0,self.index-1)];b=self.nodes[max(1,self.index)]
            self.blocked_edges[a,b]=frame+1800
            self._event('block_edge',frame,p,edge=[a,b],points=[self.atlas.points[a],self.atlas.points[b]])
        self._plan(p,target,swim,frame,True)
        if not self.path and self.replans>=self.max_replans:
            self.failed=True;return SkillResult(neutral(),False,'blocked')
        return SkillResult(neutral(),False,'replanning')

    def move_to(self,obs,target,swim=False):
        own=own_state(obs)
        if own is None or own.get('view_yaw') is None:return SkillResult(neutral(),False,'unavailable')
        p=own['position'];frame=obs['frame'];target=tuple(target);identity=(target,swim)
        if self.target!=identity:
            self.target=identity;self.replans=0;self.failed=False
            self._plan(p,target,swim,frame)
        if math.dist(p,target)<.7 and abs(p[1]-target[1])<.3:return SkillResult(neutral(),True,'arrived')
        if self.failed:return SkillResult(neutral(),False,'blocked')
        if not self.path:return self._replan(p,target,swim,frame)
        # A waypoint is reached in both horizontal position and height. In
        # particular, standing under/near a ramp corner never skips that bend.
        previous=self.index
        while self.index<len(self.path)-1:
            q=self.path[self.index]
            if math.hypot(p[0]-q[0],p[2]-q[2])>self.waypoint_radius or abs(p[1]-q[1])>.3:break
            self.index+=1
        if self.index!=previous:
            self.last_progress=frame;self.last_position=tuple(p)
            self.jump_sent=False;self.jump_started=None;self.jump_position=None
            self.best_distance=math.hypot(p[0]-self.path[self.index][0],p[2]-self.path[self.index][2])
        current_distance=math.hypot(p[0]-self.path[self.index][0],p[2]-self.path[self.index][2])
        if self.best_distance-current_distance>.15:
            self.last_progress=frame;self.last_position=tuple(p);self.best_distance=current_distance
        q=self.path[self.index];dx=q[0]-p[0];dz=q[2]-p[2];yaw=own['view_yaw']
        x=-dx*math.cos(yaw)+dz*math.sin(yaw);y=dx*math.sin(yaw)+dz*math.cos(yaw)
        norm=max(.001,math.hypot(x,y));distance=math.hypot(dx,dz)
        # Slow at actual bends, without shrinking diagonal components into
        # the native per-axis dead zone. Cap the final vector inside the stick
        # circle; every direction retains an effective dominant axis.
        corner=self.index==len(self.path)-1
        if 0<self.index<len(self.path)-1:
            prev=self.path[self.index-1];nxt=self.path[self.index+1]
            v=(q[0]-prev[0],q[2]-prev[2]);w=(nxt[0]-q[0],nxt[2]-q[2])
            cosine=(v[0]*w[0]+v[1]*w[1])/max(.001,math.hypot(*v)*math.hypot(*w))
            corner=cosine<.95 or self.atlas.edge_kind(self.nodes[self.index-1],self.nodes[self.index])=='jump'
        slow=(corner and distance<1.1) or distance<.32
        dominant=.65 if slow else .85;limit=.85 if slow else .95
        scale=dominant/max(.001,abs(x),abs(y))
        if scale*norm>limit:scale=limit/norm
        a=neutral();a['sticks'][:2]=[scale*x,scale*y]
        stalled=frame-self.last_progress>=self.stall_frames
        required_jump=self.index>0 and self.atlas.edge_kind(self.nodes[self.index-1],self.nodes[self.index])=='jump'
        if (stalled or required_jump) and not self.jump_sent and frame-self.last_jump_frame>=60:
            self.jump_sent=True;self.jump_started=frame;self.jump_position=tuple(p);self.last_jump_frame=frame
            self._event('jump',frame,p,reason='stall' if stalled else 'edge')
            a['buttons'][4]=1
            return SkillResult(a,False,'recovering_jump')
        if self.jump_started is not None and frame-self.jump_started>=60:
            advanced=math.hypot(p[0]-self.jump_position[0],p[2]-self.jump_position[2])>.3
            if not advanced or stalled:return self._replan(p,target,swim,frame)
        if swim:
            if own.get('submerged') is True:a['buttons'][1]=1
            else:
                aim=ink_at(obs,(q[0],q[1],q[2]));a=aim.action
                if frame%120>=75:
                    a=neutral();a['buttons'][1]=1;a['sticks'][:2]=[.6*x/norm,.6*y/norm]
        return SkillResult(a)

    def swim_to(self,obs,target):return self.move_to(obs,target,swim=True)
    def aim_at(self,obs,target):return aim_at(obs,target)
    def ink_at(self,obs,target):return ink_at(obs,target)
    def objective(self):return self.atlas.objective()
