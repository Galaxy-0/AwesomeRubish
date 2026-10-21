"""Known-failed native pulse prototype; retained for evidence, not benchmarks.

Own public feedback and bounded normal inputs; native convergence not proven."""
import math
from arena.lib.skills import neutral,wrap
class PulseAim:
    def __init__(self,yaw_gain,yaw_sign,pitch_gain=.145):
        self.gain=yaw_gain;self.sign=yaw_sign;self.pitch_gain=pitch_gain;self.tick=0;self.pulse=[0.,0.,0.]
    def act(self,obs,target):
        own=obs['own'];p=own['position'];dx,dz=target[0]-p[0],target[2]-p[2]
        yaw=wrap(math.atan2(dx,dz)-own['view_yaw']);desired=max(-.9,min(.9,math.atan2(target[1]-p[1]-1.1,max(math.hypot(dx,dz),.05))));pitch=own['view_pitch']-desired
        done=abs(yaw)<.035 and abs(pitch)<.025;a=neutral()
        if self.tick%8==0:
            self.pulse=[max(-.7,min(.7,pitch/(4*self.pitch_gain))),0.,self.sign*max(-1.,min(1.,yaw/(4*self.gain)))]
        if self.tick%8<4 and not done:a['gyro']=list(self.pulse)
        self.tick+=1;return a,done,dict(yaw=yaw,pitch=pitch,phase=(self.tick-1)%8)
