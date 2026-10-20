"""Read-only state recorder around two final offline ranking groups.

Does not request additional observations or change policy inputs. Exact
trajectory digests must match the already frozen final ranking results.
"""
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import numpy as np

from sim import engine
from sim.engine import Simulator
from sim.parameters import ROOT,sha256
from sim.diagnosis import route_summary
from .ranks import run

ENVS=[]


class RecordingSimulator(Simulator):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);ENVS.append(self)

    def reset(self,*args,**kwargs):
        self.route_states=np.full((self.duration+1,2,12),np.nan)
        self.route_actions=np.zeros((self.duration,2,13),np.float32)
        self.route_observations=[[],[]]
        result=super().reset(*args,**kwargs);self.capture_route();return result

    def typed_observation(self,role):
        obs=super().typed_observation(role)
        self.route_observations[role].append((self.frame,any(e.visible for e in obs.enemies)))
        return obs

    def _prepare_player(self,role,action):
        self.route_actions[self.frame-1,role]=[*action['sticks'],*action['gyro'],*action['buttons']]
        return super()._prepare_player(role,action)

    def capture_route(self):
        self.route_states[self.frame]=[[*p.position,p.heading,p.yaw,p.pitch,p.hp,p.ink,float(p.squid),
            5 if not p.grounded else 0 if self.paint.at(p.position)==i else 4,float(p.alive),p.special]
            for i,p in enumerate(self.players)]

    def _weapons(self):
        super()._weapons();self.capture_route()


def collect(job):
    engine.Simulator=RecordingSimulator
    run(job)
    pair,stage,swap,seeds,directory,models_dir,clock=job;out=Path(directory)
    result=json.loads((out/'result.json').read_text())
    reference=json.loads((out.parent.parent/'ranks-final'/out.name/'result.json').read_text())
    if len(ENVS)!=seeds:raise ValueError('recorder environment count')
    if [g['trajectory_sha256'] for g in result['games']]!=[g['trajectory_sha256'] for g in reference['games']]:
        raise ValueError('recorder changed trajectory; not a valid diagnosis')
    report=[]
    for j,env in enumerate(ENVS):
        visibility=np.zeros((env.duration+1,2),bool)
        for role,observations in enumerate(env.route_observations):
            for k,(frame,visible) in enumerate(observations):
                end=observations[k+1][0] if k+1<len(observations) else env.duration+1
                visibility[frame:end,role]=visible
        report.append(dict(seed=j,routes=route_summary(env.route_states,env.route_actions,stage,visibility)))
        if j==0:np.savez_compressed(out/'trace-0.npz',states=env.route_states,actions=env.route_actions,visibility=visibility)
    (out/'routes.json').write_text(json.dumps(dict(pair=pair,stage=stage,swap=swap,games=report,
        trajectory_digests_match=True,recorder_sha256=sha256(Path(__file__))),indent=2)+'\n')
    print(json.dumps(dict(pair=pair,routes=report[0])),flush=True)


if __name__=='__main__':
    base=ROOT/'work/sim/window-20261021'
    jobs=[(pair,1,swap,6,str(base/'route-check'/f'{pair}-map1-side{int(swap)}'),str(base/'models-v2'),4)
          for pair,swap in (('R1',True),('R2',False))]
    with ProcessPoolExecutor(max_workers=2) as pool:list(pool.map(collect,jobs))
