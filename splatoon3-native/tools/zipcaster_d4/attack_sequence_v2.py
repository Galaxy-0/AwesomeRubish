"""Distinct native contact/projectile events, forced displacement and re-aim.

The fixture may change ideal aim between the two native births. Full contact
is4f after release; light contact9f after input. Projectiles are6/11f.
"""
import math
import numpy as np
from tools.zipcaster_d4.recoil import displacement


def sequence(shots,source_path,enemy,inputs,recoil,receive_delay=4):
    source_path=np.asarray(source_path,float)
    target_path=np.repeat(np.asarray(enemy,float)[None,:],len(source_path),axis=0)
    events=[];casts=[];unknown=[]

    def impulse(profile,style,due,yaw):
        direction=np.array([math.sin(yaw),0.,math.cos(yaw)])
        ages=np.arange(len(target_path))-due
        target_path[:]+=displacement(profile,style,ages)[:,None]*direction

    def event(release,birth,due,style,damage,channel):
        return dict(input=release,birth=birth,due=int(due),kind=style,damage=damage,source=channel)

    for release,style in inputs:
        cb=release+(4 if style=='full'else 9)
        pb=release+(6 if style=='full'else 11)
        if pb+27>=len(source_path):raise ValueError('finite trace too short')
        ca=shots.best_contact(source_path[cb],target_path[cb],style)
        contact=shots.contact(source_path[cb:cb+4],target_path[cb:cb+4],style,ca['yaw'],ca['native_pitch'])
        body=shots.contact(source_path[cb:cb+4],target_path[cb:cb+4],style,ca['yaw'],ca['native_pitch'],'Body-candidate')
        if contact['hit']!=body['hit']:unknown.append('contact receiver ambiguity at'+str(release))
        contact_event=None
        if contact['hit']:
            contact_event=event(release,cb,cb+contact['first_age']+receive_delay,style,contact['damage'],'contact-box-cylinder')
            events.append(contact_event)
            if style=='full':
                casts.append(dict(release=release,style=style,contact_aim=ca,contact=contact,projectile_aim=None))
                break #140 from one contact already defeats a100HP target.
        previous_path=target_path.copy()
        joint=style=='light'and contact_event is not None
        if joint and'light_contact_then_projectile'in recoil:
            impulse(recoil,'light_contact_then_projectile',contact_event['due'],ca['yaw'])
        pa=shots.best(source_path[pb],target_path[pb],style)
        times=np.r_[pb-1,np.arange(pb,pb+pa['lifetime']+1)]
        projectile=shots.evaluate(source_path[pb],target_path[pb],style,pa['yaw'],pa['native_pitch'],target_path[times])
        if projectile['assembly_uncertain']or pa.get('radius_bound_uncertain'):unknown.append('projectile assembly/radius ambiguity at'+str(release))
        if projectile['hit']:
            due=pb+math.ceil(projectile['player_contact_age'])+receive_delay
            events.append(event(release,pb,due,style,projectile['damage'],'projectile'))
            if joint:
                observed_gap=recoil.get('light_contact_then_projectile',{}).get('joint_hp_ages')
                if not observed_gap or abs((due-contact_event['due'])-observed_gap[-1]['age'])>1:
                    unknown.append('joint20+35 timing outside observed profile at'+str(release))
            elif style in recoil:impulse(recoil,style,due,pa['yaw'])
            else:unknown.append('missing recoil profile at'+str(release))
        elif joint:
            target_path[:]=previous_path
            unknown.append('contact-only20 recoil unmeasured at'+str(release))
        casts.append(dict(release=release,style=style,contact_aim=ca,contact=contact,
                          projectile_aim=pa,prediction=projectile,target_at_birth=previous_path[pb].tolist()))
    hp=100.;kill=None
    events.sort(key=lambda e:e['due'])
    for e in events:
        hp-=e['damage']
        if hp<=0:kill=e['due'];break
    for e in events:
        if e['source']=='contact-box-cylinder':continue
        for later in casts:
            if later['release']<=e['input']:continue
            profile='light_contact_then_projectile'if any(x['input']==e['input']and x['source']=='contact-box-cylinder'for x in events)else e['kind']
            age=later['release']+(6 if later['style']=='full'else 11)-e['due']
            if profile in recoil and age>recoil[profile]['measured_until']:unknown.append('unmeasured recoil tail before'+str(later['release']))
    return dict(kill_frame=kill,damage_events=events,casts=casts,target_path=target_path,
                uncertainties=sorted(set(unknown)),native_contact_verified=True,
                scope='Finite independently aimed native contact/projectile births; empirical recoil, receiver/assembly ambiguities explicit.')
