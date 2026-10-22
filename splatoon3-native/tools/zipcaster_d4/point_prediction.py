"""Predict the actual measured ground pose before combat, without filtering it."""
import numpy as np
from tools.zipcaster_d4.model_v3 import schedule
from tools.zipcaster_d4.attack_sequence_v2 import sequence


def ground_prediction(world,source,enemy,speed,program,heading):
    inputs=schedule(speed,program,world.cfg)
    if not inputs:return dict(probability=0,reason='unsupported input schedule')
    body=np.repeat(np.asarray(source,float)[None,:],inputs[-1][0]+81,axis=0)
    attack=sequence(world.shots,body,enemy,inputs,world.recoil,world.cfg.receive_delay)
    kill=attack['kill_frame']
    if kill is None:return dict(probability=0,reason='no predicted attack KO',uncertainties=attack['uncertainties'])
    term=dict(post=body[:kill+1],enemy_path=attack['target_path'][:kill+1],
              damage_events=attack['damage_events'],kill_frame=kill,uncertainties=attack['uncertainties'])
    arrival=world.cfg.activation_frames
    path=np.concatenate([np.repeat(np.asarray(source,float)[None,:],arrival,axis=0),term['post']])
    out=world.simulate(path,arrival,term,enemy,heading)
    used=[(t,k)for t,k in inputs if t<=kill]
    cost=(kill+arrival-world.cfg.activation_drain_grace)*world.cfg.drain+sum(world.cfg.full_cost if k=='full'else world.cfg.light_cost for t,k in used)
    return dict(probability=int(out['kill']and cost<1),remaining=max(0.,1-cost),cost=cost,
                enemy_down=out['enemy_down'],attacker_down=out['attacker_down'],
                exposure_frames=out['exposure_frames'],stealth=out['stealth'],
                uncertainties=attack['uncertainties'],source=list(source),enemy=list(enemy),
                scope='Actual pose prediction recorded beforeRS; never used to discard combat outcomes or reselect a winner.')
