"""PettingZoo ParallelEnv with exact per-agent present-frame acknowledgements."""
from functools import lru_cache
import numpy as np
from gymnasium import spaces
from pettingzoo import ParallelEnv

from .protocol import Client
from .session import Session


def turf_kill_reward(previous, current, turf_weight=.001, kill_weight=1.0):
    """Example for verified internal counters; absent counters contribute zero."""
    reward=0.0
    for key,weight in (('paint_points',turf_weight),('kills',kill_weight)):
        if key in previous and key in current:reward+=weight*max(0,current[key]-previous[key])
    return float(reward)


class NativeParallelEnv(ParallelEnv):
    metadata={'name':'splatoon3_native_v1','render_modes':['rgb_array'],'is_parallelizable':True}

    def __init__(self, players=8, frame_skip=15, mode=0, stage_id=1, weapons=None,
                 timeout=2400, step_timeout=60, patched=None, render_mode=None, state_dump=False):
        if players not in (2,8):raise ValueError('players must be 2 or 8')
        if not isinstance(frame_skip,int) or not 1<=frame_skip<=3600:raise ValueError('frame_skip must be 1..3600')
        if render_mode not in (None,'rgb_array'):raise ValueError('unsupported render_mode')
        self.possible_agents=[f'player_{n}' for n in range(players)];self.agents=[]
        self.config=dict(players=players,mode=mode,stage_id=stage_id,weapons=weapons or [0]*players,timeout=timeout,patched=patched,state_dump=state_dump)
        self.frame_skip=frame_skip;self.step_timeout=step_timeout;self.render_mode=render_mode
        self.session=None;self.clients={};self.observations={};self.episode=0;self.artifacts=[]
        self.process_infos={};self.timed_out=False

    @lru_cache(None)
    def observation_space(self, agent):
        return spaces.Dict({'pixels':spaces.Box(0,255,(72,128,3),np.uint8),
                            'frame':spaces.Box(0,np.iinfo(np.int64).max,(1,),np.int64),'phase':spaces.Discrete(4),
                            'position':spaces.Box(-256,256,(3,),np.float32),'position_valid':spaces.Discrete(2),
                            'ink':spaces.Box(0,1,(1,),np.float32),'ink_valid':spaces.Discrete(2),
                            'heading':spaces.Box(-np.pi,np.pi,(1,),np.float32),'heading_valid':spaces.Discrete(2),
                            'hp':spaces.Box(0,1,(1,),np.float32),'hp_valid':spaces.Discrete(2),
                            'remaining_time':spaces.Box(0,600,(1,),np.float32),'time_valid':spaces.Discrete(2)})

    @lru_cache(None)
    def action_space(self, agent):
        return spaces.Dict({'sticks':spaces.Box(-1,1,(4,),np.float32),
                            'gyro':spaces.Box(-1,1,(3,),np.float32),'buttons':spaces.MultiBinary(6)})

    def reset(self, seed=None, options=None):
        if self.session and self.agents and not self.timed_out:
            raise RuntimeError('all agents must settle or time out before reset; close cancels a match')
        self.close();self.timed_out=False
        options=options or {}
        if set(options)-{'mode','stage_id','weapons'}:raise ValueError('reset options: mode, stage_id, weapons only')
        config=self.config|options
        self.episode+=1
        self.session=Session(**config);self.artifacts.append(self.session.out)
        try:
            self.session.start()
            for n,agent in enumerate(self.possible_agents):
                self.clients[agent]=Client(self.session.socket_dir/f'player-{n}.sock',self.step_timeout)
            observations={};infos={}
            for agent,client in self.clients.items():
                observations[agent],infos[agent]=client.receive()
                if infos[agent]['phase']!=1:raise RuntimeError(f'{agent}: attached outside InGame')
                if (infos[agent]['source_width'],infos[agent]['source_height'])!=(1280,720):raise RuntimeError('M6 requires native 720p crop')
                if seed is not None:self.action_space(agent).seed(seed+self.possible_agents.index(agent))
            self.session.clock.pause()
            self.agents=self.possible_agents[:];self.observations=observations;self.process_infos=infos
            return observations,infos
        except BaseException:
            self.close();raise

    def step(self, actions):
        if not self.agents:raise RuntimeError('reset required before step')
        if set(actions)!=set(self.agents):raise ValueError('one action required for every live agent')
        for agent in self.agents:
            if not self.action_space(agent).contains(actions[agent]):raise ValueError(f'{agent}: action is outside its space')
        active=self.agents[:]
        observations,infos=self._advance(actions)
        rewards={agent:0.0 for agent in active}
        terminations={agent:infos[agent]['phase']>=2 for agent in active}
        truncations={agent:self.timed_out and not terminations[agent] for agent in active}
        self.agents=[a for a in active if not terminations[a] and not truncations[a]]
        return ({a:observations[a] for a in active},rewards,terminations,truncations,{a:infos[a] for a in active})

    def _advance(self, actions):
        # Settled processes stay in the frame barrier with neutral input. Send
        # all processes before receiving any, including peers removed by PZ.
        neutral=dict(sticks=np.zeros(4,np.float32),gyro=np.zeros(3,np.float32),buttons=np.zeros(6,np.int8))
        self.session.clock.resume()
        for agent,client in self.clients.items():
            client.send_step(actions.get(agent,neutral),self.frame_skip)
        observations={};infos={}
        for agent,client in self.clients.items():observations[agent],infos[agent]=client.receive()
        barrier_time=self.session.clock.pause()
        for info in infos.values():info["barrier_guest_time_ns"]=barrier_time
        try:self.session.tick(sleep=False)
        except TimeoutError:self.timed_out=True
        self.observations=observations;self.process_infos=infos
        return observations,infos

    def advance_settlement(self):
        """After all agents terminate, advance neutral result animations to Winners."""
        if self.agents:raise RuntimeError('active agents still require actions')
        if self.timed_out:raise TimeoutError('match deadline exceeded')
        return self._advance({})

    def render(self):
        return self.observations.get('player_0',{}).get('pixels')

    def close(self):
        if self.session:self.session.clock.resume()
        for client in self.clients.values():client.close()
        self.clients={};self.agents=[]
        if self.session:
            session=self.session;self.session=None;session.close()


def parallel_env(**kwargs):return NativeParallelEnv(**kwargs)
