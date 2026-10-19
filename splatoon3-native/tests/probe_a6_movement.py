#!/usr/bin/env python3
"""Native motion candidates: retain failed/unsupported effects, keep testing."""
import argparse
import math
import traceback
from a6_lab import Lab,neutral,uniform_loadout,aim_at,Skills
from stamper import squid_roll,squid_surge,zipcaster,fast_turn,FastTurn,PredictiveAim,burst_bomb,light_combo
from probe_a6_combat import prepare,trial


def motion(lab,name,plan):
    before=lab.info(0)
    if plan.cancelled:
        lab.add(dict(kind=name,status='unsupported',reason='controller precondition: '+plan.cancelled,
                     before=before,after=lab.info(0)))
        return
    history=lab.execute(0,plan,name)
    lab.add(dict(kind=name,before=before,after=lab.info(0),history=history))
    lab.capture(name)


def fast_align(lab,target):
    for _ in range(360):
        r=fast_turn(lab.obs(0),target)
        if r.done:
            lab.step(lab.actions(),'paint-aim-settle',8)
            if fast_turn(lab.obs(0),target).done:return
        else:lab.act(0,r.action,'paint-aim',1)
    lab.add(dict(kind='fast-aim-fallback',status='unsupported',reason='new fast aim did not converge'))
    lab.align(0,target)


def aim_checks(lab):
    for axis in (1,2):
        before=lab.info(0);a=neutral();a['gyro'][axis]=.25
        lab.act(0,a,'gyro-axis-pulse',6);lab.step(lab.actions(),'gyro-axis-settle',8)
        lab.add(dict(kind='gyro-axis-'+str(axis),before=before,after=lab.info(0)))
        a['gyro'][axis]=-.25;lab.act(0,a,'gyro-axis-undo',6);lab.step(lab.actions(),'gyro-axis-undo-settle',8)
    flick=FastTurn()
    for name,controller in [('fast-turn-gyro',flick.aim),('ordinary-turn-gyro-control',aim_at)]:
        p=lab.info(0)['position'];yaw=lab.obs(0)['own']['view_yaw']
        target=(p[0]-10*math.sin(yaw),p[1]+1.1,p[2]-10*math.cos(yaw))
        before=lab.info(0);history=[];converged=False
        for _ in range(360):
            r=controller(lab.obs(0),target)
            if r.done:
                lab.step(lab.actions(),name+'-settle',8)
                if controller(lab.obs(0),target).done:converged=True;break
            else:history.append(lab.act(0,r.action,name,1)['player_0'])
        lab.add(dict(kind=name,before=before,after=lab.info(0),history=history,converged=converged,
                     gyro_sign=flick.sign,gyro_gain=flick.gain,gyro_fallback=flick.fallback))
    prepare(lab,6,source=(8.,3.,8.))
    q=lab.info(1)['position'];lab.align(1,(q[0]+10,q[1]+1.1,q[2]))
    aim=PredictiveAim(projectile_speed=.8);history=[]
    for frame in range(60):
        r=aim.aim(lab.obs(0),'player_1',fast=True)
        a=lab.actions();a['player_0']=r.action;a['player_1']['sticks'][0]=.85 if frame<30 else -.85
        lab.step(a,'predictive-gyro-track',1)
        history.append(dict(frame=lab.obs(0)['frame'],target=aim.target,velocity=aim.velocity,
                            own=lab.obs(0)['own'],enemy=lab.obs(0)['enemies']))
    lab.add(dict(kind='predictive-track',history=history))


def surge_checks(lab):
    source=(0.,3.,8.);lab.navigate({0:source});lab.paint_floor(0);lab.refill(0)
    for height in (3.8,5.2,7.):
        fast_align(lab,(0.,height,4.2))
        for _ in range(3):
            a=neutral();a['buttons'][0]=1;lab.act(0,a,'surge-wall-paint',1)
            lab.step(lab.actions(),'surge-wall-paint-release',29)
    for charged in (False,True):
        name='surge-stopped-charge' if charged else 'surge-stopped-control'
        lab.navigate({0:source});lab.refill(0,180)
        p=lab.info(0)['position'];fast_align(lab,(0.,p[1]+1.1,4.5))
        a=neutral();a['buttons'][1]=1;a['sticks'][1]=1.
        contact=False
        for _ in range(30):
            lab.act(0,a,name+'-climb',3);i=lab.info(0)
            if i['position'][1]>=4.8 and i['referee_motion']['form_squid']==1:
                contact=True;break
        if not contact:
            lab.add(dict(kind=name,status='unsupported',reason='fully painted wall contact not established',after=lab.info(0)))
            return
        before=lab.info(0)
        if charged:history=lab.execute(0,squid_surge(lab.obs(0)),name)
        else:
            a=neutral();a['buttons'][1]=a['buttons'][4]=1
            history=[dict(phase='unpowered_press',infos=lab.act(0,a,name+'-press',1))]
            a['buttons'][4]=0;a['sticks'][1]=1.
            for _ in range(8):history.append(dict(phase='unpowered_release',infos=lab.act(0,a,name+'-release',3)))
        lab.add(dict(kind=name,before=before,after=lab.info(0),history=history));lab.capture(name)
        a=neutral();a['buttons'][1]=1;a['sticks'][1]=-1.
        lab.act(0,a,name+'-leave-wall',60);lab.step(lab.actions(),name+'-land',30)


def walking_fill(lab):
    """Ordinary moving light fire over fresh ground, with legal ink refills."""
    # Two flat rectangles avoid the omitted prop encountered at (-8,*,14).
    points=((-16.,3.,8.),(16.,3.,8.),(16.,3.,-8.),(-16.,3.,-8.),
            (-9.,3.,8.),(-9.,3.,-8.),(9.,3.,-8.),(9.,3.,8.))
    # Start painting along the spawn route as well; the previous fixture spent
    # a large part of the native 180-second game walking without painting.
    controller=Skills(lab.atlas);index=0;counter=0;charge=[]
    for _ in range(5000):
        info=lab.info(0)
        if info.get('special_valid') and info['special']>=1.:break
        if not info['alive']:raise AssertionError('paint route unexpectedly died')
        if info['ink']<.25:
            lab.step(lab.actions(),'paint-recovery-stop',30)
            for _ in range(10):
                previous=lab.info(0)['position'][1]
                lab.step(lab.actions(),'paint-recovery-land',6)
                if abs(lab.info(0)['position'][1]-previous)<.01:break
            lab.paint_floor(0);lab.refill(0,180)
            for _ in range(14):
                if lab.info(0)['ink']>=.99 or lab.info(0)['special']>=1.:break
                lab.refill(0,30,surface=False)
            lab.step(lab.actions(),'paint-recovery-surface',12)
            if lab.info(0)['ink']<.99 and lab.info(0)['special']<1.:
                raise AssertionError('paint route failed to recover native ink')
            controller=Skills(lab.atlas)  # deliberate refill is not a path stall
            continue
        obs=lab.obs(0);r=controller.move_to(obs,points[index%len(points)])
        if r.status=='blocked':
            lab.add(dict(kind='paint-route-skipped',goal=points[index%len(points)],
                         reason='public navigator exhausted its bounded replans',after=info))
            index+=1;controller=Skills(lab.atlas);continue
        if r.done:index+=1;continue
        p=obs['own']['position'];q=controller.path[controller.index]
        dx,dz=q[0]-p[0],q[2]-p[2];norm=max(.01,math.hypot(dx,dz))
        aimed=aim_at(obs,(p[0]+10*dx/norm,p[1]+1.1-10*math.tan(.45),p[2]+10*dz/norm))
        r.action['sticks'][2:]=aimed.action['sticks'][2:];r.action['gyro']=aimed.action['gyro']
        r.action['buttons'][0]=int(counter%30==0)
        lab.act(0,r.action,'special-walk-paint',1);counter+=1
        if counter%30==0:
            i=lab.info(0);charge.append(dict(frame=i['frame'],special=i['special'],position=i['position'],ink=i['ink']))
            lab.result['special_fill_progress']=charge;lab.save()
    return charge


def main(args):
    lab=Lab(args.phase+('-walk' if args.walk_paint else '-fast' if args.fast_paint else ''),args.timeout,loadouts=[uniform_loadout('special_charge_up'),uniform_loadout()])
    try:
        lab.start()
        if args.verify_aim:aim_checks(lab)
        if args.surge_controls:surge_checks(lab)
        if args.include_combo:
            prepare(lab,8,source=(8.,3.,8.))
            trial(lab,'light-combo-move',lambda obs:light_combo(obs,3,after=(-1.,0.)))
        if args.phase=='movement':
            lab.navigate({0:(0.,3.,8.),1:(14.,3.,8.)})
            lab.paint_floor(0);lab.refill(0)
            p=lab.info(0)['position'];yaw=lab.obs(0)['own']['view_yaw']
            target=(p[0]-10*math.sin(yaw),p[1]+1.1,p[2]-10*math.cos(yaw))
            before=lab.info(0);turn=[]
            for _ in range(160):
                result=fast_turn(lab.obs(0),target)
                if result.done:break
                lab.act(0,result.action,'fast-turn',1);turn.append(lab.info(0))
                lab.step(lab.actions(),'turn-sample',3)
            lab.add(dict(kind='fast-turn',converged=result.done,before=before,after=lab.info(0),history=turn))
            target=(p[0]+10*math.sin(yaw),p[1]+1.1,p[2]+10*math.cos(yaw))
            before=lab.info(0);turn=[]
            for _ in range(160):
                result=aim_at(lab.obs(0),target)
                if result.done:break
                lab.act(0,result.action,'ordinary-turn',1);turn.append(lab.info(0))
                lab.step(lab.actions(),'ordinary-turn-sample',3)
            lab.add(dict(kind='aim-at-turn-control',converged=result.done,before=before,after=lab.info(0),history=turn))
            # Paint the actual swim lane in both directions before reversing.
            p=lab.info(0)['position'];lab.align(0,(p[0]+12,p[1]+.15,p[2]))
            for _ in range(3):
                a=neutral();a['buttons'][0]=1;lab.act(0,a,'roll-lane-paint',1);lab.step(lab.actions(),'roll-lane-release',30)
            # Lay overlapping patches along the entire run-up. Merely firing
            # horizontally can leave a gap before the first falling droplets.
            for x in (3.,6.,0.):
                lab.navigate({0:(x,3.,8.)});lab.paint_floor(0)
            p=lab.info(0)['position'];lab.align(0,(p[0]+12,p[1]+1.1,p[2]))
            lab.refill(0,180,surface=False)
            motion(lab,'squid-roll-candidate',squid_roll(lab.obs(0)))
            # Same B edge without the speed prerequisite: ordinary jump control.
            lab.navigate({0:(0.,3.,8.)});lab.paint_floor(0);lab.refill(0,180,surface=False)
            before=lab.info(0);a=neutral();a['buttons'][1]=a['buttons'][4]=1;a['sticks'][1]=-1
            lab.act(0,a,'ordinary-jump-edge',1);history=[];a['buttons'][4]=0
            for _ in range(8):history.append(lab.act(0,a,'ordinary-jump',3)['player_0'])
            lab.add(dict(kind='ordinary-jump-control',before=before,after=lab.info(0),history=history))
            # Public predictive aiming sees only current visible samples.
            lab.navigate({0:(8.,3.,8.),1:(14.,3.,8.)})
            p=lab.info(0)['position'];q=lab.info(1)['position'];lab.align(0,(q[0],q[1]+1.1,q[2]))
            a=neutral();a['sticks'][1]=.85;lab.act(0,a,'track-face-target',6);lab.step(lab.actions(),'track-face-settle',8)
            lab.align(1,(q[0]+10,q[1]+1.1,q[2]))
            aim=PredictiveAim(projectile_speed=.8);history=[]
            for step in range(40):
                result=aim.aim(lab.obs(0),'player_1',fast=True)
                a=lab.actions();a['player_0']=result.action;a['player_1']['sticks'][0]=.85 if step<20 else -.85
                lab.step(a,'native-predictive-track',1)
                history.append(dict(frame=lab.obs(0)['frame'],target=aim.target,velocity=aim.velocity,own=lab.obs(0)['own'],enemy=lab.obs(0)['enemies']))
            lab.add(dict(kind='predictive-track',history=history))
            # This is an attempted wall operation. The audit needs native
            # height/state evidence; sending B is never a success criterion.
            lab.navigate({0:(0.,3.,8.)});p=lab.info(0)['position'];lab.align(0,(0.,5.5,4.))
            for _ in range(5):
                a=neutral();a['buttons'][0]=1;lab.act(0,a,'wall-paint',1);lab.step(lab.actions(),'wall-paint-release',30)
            lab.paint_floor(0);lab.refill(0,180,surface=False)
            a=neutral();a['buttons'][1]=1;a['sticks'][1]=1
            before=lab.info(0);lab.act(0,a,'wall-approach',30)
            if lab.obs(0)['own']['submerged'] is True:
                control_before=lab.info(0);control=[]
                jump=neutral();jump['buttons'][1]=jump['buttons'][4]=1;jump['sticks'][1]=1.
                control.append(dict(phase='unpowered_press',infos=lab.act(0,jump,'wall-jump-control',1)))
                jump['buttons'][4]=0
                for _ in range(8):control.append(dict(phase='unpowered_release',infos=lab.act(0,jump,'wall-jump-control-release',3)))
                lab.add(dict(kind='squid-surge-control',before=control_before,after=lab.info(0),history=control))
                lab.step(lab.actions(),'wall-control-land',60)
                lab.navigate({0:(0.,3.,8.)});lab.paint_floor(0);lab.refill(0,180,surface=False)
                lab.act(0,a,'wall-approach-charged',30)
                motion(lab,'squid-surge-candidate',squid_surge(lab.obs(0)))
            else:
                lab.add(dict(kind='squid-surge-candidate',status='unsupported',reason='native wall approach not submerged',before=before,after=lab.info(0)))
        else:
            if args.include_bomb:
                prepare(lab,6,source=(8.,3.,8.))
                trial(lab,'burst-bomb',lambda obs:burst_bomb(obs))
            # Full gauge comes only from native painting with a legal loadout.
            # Stop at a bounded guest budget and preserve an unsupported record
            # rather than injecting the meter or pressing RS below full.
            charge=walking_fill(lab) if args.walk_paint else []
            for point in (() if args.walk_paint else ((-20.,3.,8.),(-8.,3.,8.),(4.,3.,8.),(16.,3.,8.),(8.,3.,16.),(-16.,3.,-8.))):
                lab.navigate({0:point});lab.paint_floor(0);lab.refill(0)
                p=lab.info(0)['position']
                for index in range(16 if args.fast_paint else 8):
                    if args.fast_paint:
                        if index==0:fast_align(lab,(p[0],p[1]-.2,p[2]+12))
                        if index==8:lab.refill(0)
                        a=neutral();a['sticks'][2]=.55;a['buttons'][0]=1
                        lab.act(0,a,'special-circle-press',1);a['buttons'][0]=0
                        lab.act(0,a,'special-circle-release',29)
                        charge.append(dict(frame=lab.info(0)['frame'],special=lab.info(0).get('special'),position=lab.info(0)['position']))
                        lab.result['special_fill_progress']=charge;lab.save()
                        if lab.info(0).get('special_valid') and lab.info(0)['special']>=1.:break
                        continue
                    yaw=index*math.pi/4
                    lab.align(0,(p[0]+math.sin(yaw)*12,p[1]-.2,p[2]+math.cos(yaw)*12))
                    for _ in range(2):
                        a=neutral();a['buttons'][0]=1;lab.act(0,a,'special-paint',1);lab.step(lab.actions(),'special-paint-release',30)
                    charge.append(dict(frame=lab.info(0)['frame'],special=lab.info(0).get('special'),position=lab.info(0)['position']))
                    lab.result['special_fill_progress']=charge;lab.save()
                    if lab.info(0).get('special_valid') and lab.info(0)['special']>=1.:break
                if lab.info(0).get('special_valid') and lab.info(0)['special']>=1.:break
            lab.add(dict(kind='special-fill',history=charge,after=lab.info(0)))
            if lab.info(0).get('special_valid') and lab.info(0)['special']>=1.:
                p=lab.info(0)['position']
                if args.fast_paint:fast_align(lab,(0.,10.,0.))
                else:lab.align(0,(0.,10.,0.))
                motion(lab,'zipcaster',zipcaster(lab.obs(0)))
            else:
                lab.add(dict(kind='zipcaster',status='unsupported',reason='bounded native paint did not fill meter',after=lab.info(0)))
        lab.result.update(passed=True,probe_completed=True)
    except BaseException as e:
        lab.result['errors'].append(repr(e));lab.result['traceback']=traceback.format_exc()
    finally:lab.close()
    print(lab.out,flush=True)
    return 0 if lab.result['passed'] and not lab.result['errors'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--phase',choices=('movement','special'),required=True)
    p.add_argument('--include-bomb',action='store_true',help='Measure the bomb before filling the special in this same room')
    p.add_argument('--include-combo',action='store_true',help='Measure the light rhythm/post-movement before motion experiments')
    p.add_argument('--fast-paint',action='store_true',help='Paint a circle with ordinary continuous camera input; no gauge injection')
    p.add_argument('--walk-paint',action='store_true',help='Fill meter by native moving light fire across fresh ground')
    p.add_argument('--verify-aim',action='store_true',help='Calibrate gyro yaw and compare native fast turn/lead tracking')
    p.add_argument('--surge-controls',action='store_true',help='One-frame wall jump versus stopped-stick charged release')
    p.add_argument('--timeout',type=float,default=3600);raise SystemExit(main(p.parse_args()))
