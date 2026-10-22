"""Finite combo accounting with forced displacement and re-aim after a hit.

Separate from the frozen old route bank. This does not certify unmeasured
contact transforms or project target recoil through arbitrary ledges.
"""
import math
import numpy as np
from tools.zipcaster_d4.recoil import displacement

def sequence(shots,source_path,enemy,inputs,recoil,include_contact=False,receive_delay=4):
    source_path=np.asarray(source_path,float);enemy=np.asarray(enemy,float)
    horizon=len(source_path);target_path=np.repeat(enemy[None,:],horizon,axis=0)
    damage_events=[];casts=[];unknown=[];hit_points=100.
    for release,style in inputs:
        birth=release+(6 if style=='full'else 11)
        if birth+27>=horizon:raise ValueError('source trace too short for full finite projectile lifetime')
        # The ideal fixture can update aim every present. The model uses the
        # predicted state at birth, including prior forced displacement.
        aim=shots.best(source_path[birth],target_path[birth],style)
        times=np.r_[birth-1,np.arange(birth,birth+aim['lifetime']+1)]
        moving=shots.evaluate(source_path[birth],target_path[birth],style,aim['yaw'],aim['native_pitch'],target_path[times])
        if moving['assembly_uncertain']:unknown.append('side consumption changes hit at'+str(release))
        candidates=[]
        if moving['hit']:
            candidates.append(dict(input=release,birth=birth,due=birth+math.ceil(moving['player_contact_age'])+receive_delay,kind=style,damage=moving['damage'],source='projectile',direction=shots.direction(aim['yaw'],aim['native_pitch'],style)[0]))
        if include_contact:
            cb=release+(5 if style=='full'else 8)
            contact=shots.contact(source_path[cb:cb+4],target_path[cb:cb+4],style,aim['yaw'],aim['native_pitch'])
            body=shots.contact(source_path[cb:cb+4],target_path[cb:cb+4],style,aim['yaw'],aim['native_pitch'],'Body-candidate')
            if contact['hit']!=body['hit']:unknown.append('unverified Body receiver changes contact at'+str(release))
            if contact['hit']:
                unknown.append('contact transform/timing unverified at'+str(release))
                candidates.append(dict(input=release,birth=cb,due=cb+contact['first_age']+receive_delay,kind=style,damage=contact['damage'],source='contact-box-cylinder',direction=shots.direction(aim['yaw'],aim['native_pitch'],style)[0]))
        # Contact and projectile may be separate objects. Native duplicate-hit
        # suppression is unverified; never add their damage blindly.
        event=min(candidates,key=lambda e:e['due'])if candidates else None
        if event:
            direction=np.array(event.pop('direction'));direction[1]=0;direction/=max(np.linalg.norm(direction),1e-12)
            ages=np.arange(horizon)-event['due']
            target_path+=displacement(recoil,style,ages)[:,None]*direction
            damage_events.append(event)
        casts.append(dict(release=release,style=style,aim=aim,prediction=moving,target_at_birth=target_path[birth].tolist()))
    kill=None
    for event in sorted(damage_events,key=lambda e:e['due']):
        hit_points-=event['damage']
        if hit_points<=0:kill=event['due'];break
    # An extrapolated recoil tail may change a later aim/collision. Keep that
    # uncertainty visible rather than certifying all combos from a flat sample.
    for i,event in enumerate(damage_events):
        for later in casts[i+1:]:
            age=later['release']-event['due']
            if age>recoil[event['kind']]['measured_until']:
                unknown.append('unmeasured recoil tail before'+str(later['release']))
    return dict(kill_frame=kill,damage_events=damage_events,casts=casts,target_path=target_path,uncertainties=sorted(set(unknown)),native_contact_verified=False)
