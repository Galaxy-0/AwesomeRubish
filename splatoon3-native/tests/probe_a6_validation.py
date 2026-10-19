#!/usr/bin/env python3
"""Matched native movement controls and the final predictive controller."""
import argparse
import math
import traceback
from a6_lab import Lab, neutral, aim_at
from stamper import squid_roll, squid_surge, PredictiveAim, fast_turn


def roll_case(lab, name, reverse, jump):
    lab.navigate({0:(0.,3.,8.)})
    lab.paint_floor(0)
    p=lab.info(0)['position'];lab.align(0,(p[0]+12,p[1]+1.1,p[2]))
    lab.refill(0,180,surface=False)
    before=lab.info(0);history=[]
    if reverse and jump:
        plan=squid_roll(lab.obs(0))
        while True:
            r=plan.tick(lab.obs(0))
            if r.done:
                if r.status!='complete':raise AssertionError(r.status)
                break
            # One-present steps retain the early airborne trajectory.
            infos=lab.act(0,r.action,name+'-'+r.phase,1)
            history.append(dict(phase=r.phase,infos=infos))
            if lab.obs(0)['frame']-plan.start in (33,37,41):lab.capture(name+'-'+str(lab.obs(0)['frame']-plan.start))
    else:
        a=neutral();a['buttons'][1]=1;a['sticks'][1]=1.
        lab.act(0,a,name+'-swim',30)
        for frame in range(17):
            a=neutral();a['buttons'][1]=1;a['buttons'][4]=int(jump and frame==0)
            a['sticks'][1]=-1. if reverse else 1.
            infos=lab.act(0,a,name+'-edge-travel',1)
            history.append(dict(phase='control',infos=infos))
            if frame in (2,6,10):lab.capture(name+'-'+str(frame+1))
    lab.add(dict(kind=name,before=before,after=lab.info(0),history=history,
                 matched_run_up_frames=30,reverse=reverse,jump=jump))
    lab.step(lab.actions(),'roll-land',90)


def wall_case(lab, name, source, targets, approach):
    lab.navigate({0:source})
    # Paint the floor first, then both lower and upper wall. The former driver
    # aimed only above the foot of the wall and never established wall contact.
    lab.paint_floor(0);lab.refill(0)
    for target in targets:
        lab.align(0,target)
        for _ in range(4):
            a=neutral();a['buttons'][0]=1
            lab.act(0,a,name+'-paint',1);lab.step(lab.actions(),name+'-paint-release',30)
    lab.refill(0)
    p=lab.info(0)['position'];lab.align(0,(targets[0][0],p[1]+1.1,targets[0][2]))
    a=neutral();a['buttons'][1]=1;a['sticks'][1]=1.
    before=lab.info(0);history=[]
    for _ in range(approach//3):history.append(dict(phase='wall_approach',infos=lab.act(0,a,name+'-approach',3)))
    contact=lab.info(0);lab.capture(name+'-contact')
    plan=squid_surge(lab.obs(0))
    history+=lab.execute(0,plan,name)
    lab.add(dict(kind=name,before=before,contact=contact,after=lab.info(0),history=history,
                 identity='candidate_requires_delayed_release_height_witness'))
    lab.capture(name+'-release');lab.step(lab.actions(),name+'-land',90)
    # Same prepared wall/run-up, ordinary one-frame B release as control.
    lab.navigate({0:source});lab.paint_floor(0);lab.refill(0)
    p=lab.info(0)['position'];lab.align(0,(targets[0][0],p[1]+1.1,targets[0][2]))
    a=neutral();a['buttons'][1]=1;a['sticks'][1]=1.
    lab.act(0,a,name+'-control-approach',approach)
    before=lab.info(0);history=[];a['buttons'][4]=1
    history.append(dict(phase='unpowered_press',infos=lab.act(0,a,name+'-control-press',1)))
    a['buttons'][4]=0
    for _ in range(28):history.append(dict(phase='unpowered_release',infos=lab.act(0,a,name+'-control-release',3)))
    lab.add(dict(kind=name+'-control',before=before,after=lab.info(0),history=history))
    lab.step(lab.actions(),name+'-control-land',90)


def main(args):
    lab=Lab('validation',args.timeout)
    try:
        lab.start();lab.navigate({0:(0.,3.,8.),1:(18.,3.,8.)})
        for x in (3.,6.,0.):
            lab.navigate({0:(x,3.,8.)});lab.paint_floor(0)
        for name,reverse,jump in [('swim-forward-jump-control',False,True),
                                   ('swim-reverse-control',True,False),
                                   ('squid-roll-matched',True,True)]:
            roll_case(lab,name,reverse,jump)
        lab.navigate({0:(8.,3.,8.),1:(14.,3.,8.)})
        q=lab.info(1)['position'];lab.align(0,(q[0],q[1]+1.1,q[2]))
        a=neutral();a['sticks'][1]=.85;lab.act(0,a,'track-face',6);lab.step(lab.actions(),'track-settle',8)
        lab.align(1,(q[0]+10,q[1]+1.1,q[2]));aim=PredictiveAim(projectile_speed=.8);history=[]
        for frame in range(60):
            r=aim.aim(lab.obs(0),'player_1',fast=True)
            a=lab.actions();a['player_0']=r.action;a['player_1']['sticks'][0]=.85 if frame<30 else -.85
            lab.step(a,'predictive-final',1)
            history.append(dict(frame=lab.obs(0)['frame'],target=aim.target,velocity=aim.velocity,
                                own=lab.obs(0)['own'],enemy=lab.obs(0)['enemies']))
        lab.add(dict(kind='predictive-track',history=history))
        for name,controller in [('fast-turn-continuous',fast_turn),('ordinary-turn-continuous',aim_at)]:
            p=lab.info(0)['position'];yaw=lab.obs(0)['own']['view_yaw']
            target=(p[0]-10*math.sin(yaw),p[1]+1.1,p[2]-10*math.cos(yaw))
            before=lab.info(0);history=[];converged=False
            for _ in range(360):
                r=controller(lab.obs(0),target)
                if r.done:
                    lab.step(lab.actions(),name+'-settle',8)
                    if controller(lab.obs(0),target).done:converged=True;break
                else:history.append(lab.act(0,r.action,name,1)['player_0'])
            lab.add(dict(kind=name,before=before,after=lab.info(0),history=history,converged=converged))
        for name,source,targets,approach in [
                ('surge-central-wall',(0.,3.,8.),[(0.,4.1,4.),(0.,6.2,4.)],36),
                ('surge-low-crate',(-12.,3.,4.),[(-12.,3.5,1.),(-12.,4.3,1.)],24)]:
            try:wall_case(lab,name,source,targets,approach)
            except AssertionError as e:
                lab.add(dict(kind=name,status='unsupported',reason='native fixture: '+str(e),after=lab.info(0)))
        lab.result.update(passed=True,probe_completed=True)
    except BaseException as e:
        lab.result['errors'].append(repr(e));lab.result['traceback']=traceback.format_exc()
    finally:lab.close()
    print(lab.out,flush=True)
    return 0 if lab.result['passed'] and not lab.result['errors'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--timeout',type=float,default=3600)
    raise SystemExit(main(p.parse_args()))
