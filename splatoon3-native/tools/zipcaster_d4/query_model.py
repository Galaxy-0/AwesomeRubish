"""Query-only wall-terminal generation after falling; no attach-height cutoff."""
import numpy as np
from tools.zipcaster_d4.model_v3 import World as CombatWorld,schedule,post_path
from tools.zipcaster_d4.attack_sequence_v2 import sequence


class World(CombatWorld):
    def terminal(self,node,enemy,speed,program,ground=False):
        if ground:return super().terminal(node,enemy,speed,program,True)
        inputs=schedule(speed,program,self.cfg)
        if not inputs:return None
        position=self.graph['attach'][node]
        if np.linalg.norm((position-enemy)[[0,2]])>27:return None
        # An initially high anchor may fall into range before the attack.
        body=post_path(position,self.graph['floor'][node],inputs[-1][0]+80)
        if program=='full1'and not self.shots.best_contact(body[speed+4],enemy,'full')['hit']:return None
        result=sequence(self.shots,body,enemy,inputs,self.recoil,self.cfg.receive_delay)
        kill=result['kill_frame']
        if kill is None:return None
        used=[(t,k)for t,k in inputs if t<=kill]
        cost=kill*self.cfg.drain+sum(self.cfg.full_cost if k=='full'else self.cfg.light_cost for t,k in used)
        return dict(node=node,ground=False,speed=speed,program=program,cost=cost,kill_frame=kill,
            damage_events=result['damage_events'],inputs=used,post=body[:kill+1],enemy_path=result['target_path'][:kill+1],
            uncertainties=result['uncertainties'],program_native_verified=False,
            scope='Corrected finite model; wall range checked after falling, not initial anchor height.')
