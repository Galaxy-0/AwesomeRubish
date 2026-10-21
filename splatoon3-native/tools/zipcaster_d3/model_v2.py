"""Resumed finite model: B trajectory and gauge budget, NOT native certified.

The sampled B profile is one native low-wall jump. It is a conditional template,
not a general character physics solution. Landing points remain static candidates.
"""
from dataclasses import dataclass
import math
import numpy as np
from model import Config as OldConfig,duel_batch,wilson,gun_flight_frames,wrap
from budget import Gauge
@dataclass(frozen=True)
class Config(OldConfig):
    arrival_setup:int=117 # native resumed C pilot: B6 + aim97 + face/settle14
    duration:int=600
    rehook_preaim:int=146 # witnessed hang pre-aim; not charged as zero-cost wait
    jump_button_frames:int=6
    return_frames:int=96

# Native B6 low-wall measured increments; packet feedback is ~4f, so this is
# interpolation of observations, not finer-than-sampled game physics evidence.
JUMP_T=np.array([0,1,5,9,13,17,21,25,29,33,37,41,45,49,53,57,61])
JUMP_Y=np.array([0,0,.8939008,1.6704044,2.1048774,2.1010532,2.0087089,1.7999191,1.4833355,1.0670461,.5585909,-.035017,-.7072706,-1.452138,-2.2640333,-3.1377926,-3.5322294])

def hook_path(start,anchors,landings,cfg=Config(),ground_landings=None):
    pos=np.asarray(start,float);path=[pos.copy()];events=[];gauge=Gauge();extra=[]
    ground_landings=ground_landings or landings
    for j,(anchor,attach,ground)in enumerate(zip(anchors,landings,ground_landings)):
        anchor=np.asarray(anchor,float);attach=np.asarray(attach,float);ground=np.asarray(ground,float)
        d=np.linalg.norm(anchor-pos-[0,1.1,0])
        if d<=0 or d>cfg.hook_range:return None,[]
        t=len(path)-1;events.append(dict(frame=t,event='出钩',hook=j));extra.append((t,gauge.hook_ink/gauge.capacity))
        path.extend([pos.copy()for _ in range(math.ceil(d/cfg.hook_tip_speed)+cfg.bind_wait)])
        events.append(dict(frame=len(path)-1,event='挂住',hook=j));delta=attach-pos;length=np.linalg.norm(delta);speed=cfg.hook_initial_speed;travel=0.
        while travel<length:
            speed=min(cfg.hook_body_speed,speed+cfg.hook_acceleration);travel=min(length,travel+speed);path.append(pos+delta*travel/max(length,1e-9))
        pos=attach.copy();events.append(dict(frame=len(path)-1,event='到达',hook=j))
        if j<len(anchors)-1:
            path.extend([pos.copy()for _ in range(cfg.rehook_preaim)])
            events.append(dict(frame=len(path)-1,event='B跳离',hook=j))
            for f in range(1,cfg.jump_button_frames+1):path.append(pos+[0,float(np.interp(f,JUMP_T,JUMP_Y)),0])
            pos=path[-1].copy()
        else:
            events.append(dict(frame=len(path)-1,event='B跳离',hook=j))
            for f in range(1,cfg.arrival_setup+1):
                y=pos[1]+(float(np.interp(f,JUMP_T,JUMP_Y))if f<=61 else JUMP_Y[-1]-.24*(f-61))
                # A static terminal floor assumption, openly separate from rays.
                q=pos.copy();q[1]=max(ground[1],y);path.append(q)
            pos=path[-1].copy()
    arrival=len(path)-1;events.append(dict(frame=arrival,event='开始蓄力'))
    extra.append((arrival,gauge.full_ink/gauge.capacity))
    extra.append((arrival+cfg.light_input_after_charge,gauge.light_ink/gauge.capacity))
    path.extend([pos.copy()for _ in range(cfg.light_input_after_charge+cfg.light_spawn_after_input+40)])
    cost=gauge.cost(len(path)-1,hooks=len(anchors),lights=1,fulls=1)
    if cost>=1:return None,[]
    events.append(dict(frame=len(path)-1,event='预算',spent=cost,remaining=1-cost,mandatory_return_at_or_before=math.ceil((1-sum(c for _,c in extra))/gauge.drain)))
    return np.asarray(path),events
