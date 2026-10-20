"""A6 advanced calibration rechecks using recorded inputs, never native runs."""
import json

import numpy as np

from .advanced import AdvancedModel
from .engine import Simulator
from .motion import MotionModel
from .parameters import ROOT, Parameters, sha256
from .replay import compare, read_jsonl
from .terrain import Terrain
from .weapon import WeaponModel

WORK=ROOT/'work/sim/advanced'


def recheck(group, prefix, parameters, terrain, model):
    refs=json.loads((ROOT/'arena/results/a6-acceptance.json').read_text())['native']
    result=ROOT/refs[group]['path'];steps=result.parent/'steps.jsonl'
    if sha256(result)!=refs[group]['sha256'] or sha256(steps)!=refs[group]['attachments_sha256'][str(steps.relative_to(ROOT))]:
        raise ValueError('A6 comparison source drift')
    rows=read_jsonl(steps)
    intervals,barriers=[],[];indices=[];frame=0
    for row in rows:
        count=row['frames'];intervals.append(dict(frame_interval=[frame,frame+count],actions=row['actions']))
        frame+=count;barriers.append(dict(frame=frame,infos=row['infos']))
        if row['label'].startswith(prefix) and not any(w in row['label'] for w in ['-climb','-leave-wall','-land']):
            indices.append(len(barriers)-1)
    env=Simulator(1,parameters=parameters,terrain=terrain,duration_frames=frame,
                  motion_model=MotionModel.load(ROOT/'work/sim/fidelity/motion.json'),
                  weapon_model=WeaponModel.load(ROOT/'work/sim/fidelity/weapon.json'),advanced_model=model)
    def setup(env):
        p=env.players[0]
        if 'roll' in prefix or 'swim-' in prefix:
            env.paint.disk(p.position,9.,0)
            return 'A6 known painted swim strip approximated as radius-9 floor disk; unobserved full paint mask.'
        if 'surge' in prefix:
            start=p.position+[0,.7,0];direction=np.array([np.sin(p.yaw),0,np.cos(p.yaw)])
            hits=env.terrain.obstacles.hits(start,start+direction*1.5,.00001)
            if len(hits):
                point=start+direction*hits[0]
                for height in range(0,9):model.paint_wall(env,point+[0,height,0],0,1.5)
            return dict(known_painted_wall_fixture=True,wall_ray_found=bool(len(hits)),
                        unobserved_velocity='zero at stopped charge anchor; climb warmup excluded')
        return 'No additional precondition; initial positions/own HP/ink/camera from recorded packets.'
    report=compare(env,intervals,barriers,indices[0]-1,barriers[indices[-1]]['frame'],
                   own_ink_fixture=False,setup=setup)
    report.update(case=prefix,group=group,source=dict(result=str(result.relative_to(ROOT)),
                  result_sha256=sha256(result),steps_sha256=sha256(steps)),
                  interpretation='Same-room calibration recheck, not held-out advanced validation.',
                  event_counts={kind:sum(e['kind']==kind for e in env.events) for kind in sorted({e['kind'] for e in env.events})})
    # Include all HP drops; old replay direct-damage matcher deliberately ignores
    # sub-29-point packets and therefore cannot describe 25+35 burst damage.
    first=barriers[indices[0]-1]
    previous=first['infos']['player_1']['hp'];seen=set();drops=[]
    previous_frame=first['infos']['player_1']['position_sample_frame']
    origin=first['infos']['player_1']['frame']-first['frame']
    for row in barriers[indices[0]:indices[-1]+1]:
        info=row['infos']['player_1'];f=info['position_sample_frame']
        if f in seen:continue
        seen.add(f)
        if previous-info['hp']>.01:drops.append(dict(frame=f-origin,drop=previous-info['hp'],
                                                   interval=[previous_frame+1-origin,f-origin]))
        previous=info['hp']
        previous_frame=f
    report['native_all_damage_packets']=drops
    simulated=report['players']['player_1']['simulated_damage']
    report['ordered_packet_interval_errors']=[dict(native_interval=n['interval'],simulated_frame=s['frame'],
            native_drop=n['drop'],simulated_nominal_damage=s['amount'],
            violation=max(n['interval'][0]-s['frame'],0,s['frame']-n['interval'][1]))
            for s,n in zip(simulated,drops)]
    report['unmatched_packet_counts']=dict(simulated=max(0,len(simulated)-len(drops)),native=max(0,len(drops)-len(simulated)))
    (WORK/(prefix+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    return {k:v for k,v in report.items() if k not in ['sampled_curves','sources','notes']}


def main():
    model=AdvancedModel.load(WORK/'model.json')
    parameters,terrain=Parameters.local(),Terrain.load(1)
    cases=[('roll','squid-roll-matched'),('roll','swim-forward-jump-control'),('roll','swim-reverse-control'),
           ('aim_surge','surge-stopped-control'),('aim_surge','surge-stopped-charge'),
           ('combat','dash-full'),('combo_bomb','burst-bomb'),('zip_activation','zipcaster')]
    report=dict(schema='sim.advanced.comparison.v1',model_sha256=sha256(WORK/'model.json'),
                cases=[recheck(group,prefix,parameters,terrain,model) for group,prefix in cases])
    (WORK/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    for c in report['cases']:
        print(c['case'],c['event_counts'],'pos',round(c['players']['player_0']['position_world_units']['rmse'],4),
              'damage',[(v['cause'],v['amount']) for v in c['players']['player_1']['simulated_damage']],
              'native',c['native_all_damage_packets'])


if __name__=='__main__':main()
