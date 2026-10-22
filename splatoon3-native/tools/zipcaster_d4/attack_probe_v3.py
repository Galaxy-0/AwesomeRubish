"""Eight-shot, independently restored native test of the v3 attack model.

No pose/HP writes. Requested<=.05u placement uses ordinary sticks only; a
failure to attain it triggers actual-pose recomputation and loses paired status.
One invocation owns one room, with a predeclared finite case list.
"""
import argparse,json,math,sys,traceback
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.control import new_lab,fixture,neutral,sha
from tools.zipcaster_d3r.setup_navigation import place
from tools.zipcaster_d3r.weapon_aim import blade_angles
from tools.zipcaster_d4.model_v2 import World
from tools.zipcaster_d4.attack_model_v3 import Shots

def refine(lab,n,goal,limit=48):
    best=math.inf;stale=0
    for tick in range(limit):
        info=lab.info(n);p=np.array(info['position']);delta=np.asarray(goal)-p
        error=float(np.linalg.norm(delta))
        if error<=.05:
            lab.step(lab.actions(),'v3-refine-settle',8)
            if math.dist(lab.info(n)['position'],goal)<=.05:return True
        if error<best-.002:best=error;stale=0
        else:stale+=1
        if stale>=12:break
        yaw=info['own_view']['yaw']
        local=np.array([-delta[0]*math.cos(yaw)+delta[2]*math.sin(yaw),
                         delta[0]*math.sin(yaw)+delta[2]*math.cos(yaw)])
        axis=int(np.argmax(np.abs(local)))
        act=neutral();act['sticks'][axis]=math.copysign(.45 if error<.35 else .65,local[axis])
        lab.act(n,act,'v3-refine-stick',1 if error<.35 else 2)
        lab.step(lab.actions(),'v3-refine-observe',8)
    lab.step(lab.actions(),'v3-refine-bounded-fallback',8)
    return math.dist(lab.info(n)['position'],goal)<=.05

def main(a):
    plan=json.loads(a.plan.read_text());group=plan['groups'][a.group]
    world=World(ROOT/group['graph']);model=Shots(world,a.fit)
    # Complete local preflight before even constructing a game lab.
    for style in ['full','light']:
        model.contact(np.repeat([[0.,0.,0.]],4,axis=0),np.repeat([[0.,0.,3.]],4,axis=0),style,0.,0.)
    lab=new_lab('d4-attack3-'+a.group,world.meta['stage'],a.host);records=[]
    sources=[Path(__file__),Path(__file__).with_name('attack_model_v3.py'),Path(__file__).with_name('attack_geometry.py'),a.plan,a.fit]
    lab.result.update(schema='inklab.d4.attack.confirm.v3',point=dict(id=a.group,graph=group['graph'],source=group['cases'][0]['source'],enemy=group['cases'][0]['enemy']),records=records,predeclared_cases=group['cases'],source_sha256={str(p.resolve()):sha(p)for p in sources},ideal_operation_fixture=True,special_fixture='infinite',calibration_eligible=False,full_d4_passed=False,scope='Single-slash mechanism confirmation, not win-rate or finite-gauge validation. Each shot natural full health and ordinary placement; inaccurate requested pose is recomputed, never treated as an identical pair.')
    for p in sources:(lab.out/('tested-'+p.name)).write_bytes(p.read_bytes())
    try:
        with fixture(lab,roles=(0,),meter='infinite')as aim:
            lab.start();first=True
            for index,case in enumerate(group['cases']):
                if lab.info(0)['remaining_time']<18:
                    lab.result['bounded_stop']='less18s native time; unattempted cases retained';break
                if not all(lab.info(n)['alive']for n in[0,1]):
                    lab.result['bounded_stop']='native KO; no forced repair';break
                aim.off();place(lab,{0:case['source'],1:case['enemy']})
                # Painting/recovery happens after restoring the target, so old
                # enemy ink at the requested pose cannot masquerade as a hit.
                refine(lab,1,case['enemy']);lab.paint_floor(1);lab.refill(1,300)
                lab.step(lab.actions(),'v3-natural-health-settle',40)
                restored=[refine(lab,n,case['source']if n==0 else case['enemy'])for n in[0,1]]
                if min(lab.info(n)['hp']for n in[0,1])<.999:
                    lab.result['bounded_stop']='natural full-health precondition failed';break
                if first:
                    act=neutral();act['buttons'][3]=1;lab.act(0,act,'v3-RS',6)
                    lab.step(lab.actions(),'v3-native-activation',25);first=False
                source,target=[lab.info(n)['position']for n in[0,1]]
                if case['aim']=='best':
                    prediction=model.best(source,target,case['style']);yaw=prediction['yaw'];pitch=prediction['native_pitch']
                else:
                    old=json.loads((ROOT/'work/d3r/attack-parameters-v1.json').read_text())
                    yaw,pitch=blade_angles(source,target,old,style=case['style'])
                    pitch=max(-.85,min(.85,pitch+case['pitch_delta']))
                    prediction=model.evaluate(source,target,case['style'],yaw,pitch)
                aim.set_native(0,yaw,pitch);lab.step(lab.actions(),'v3-frozen-native-preaim',4)
                before=lab.env.process_infos
                prediction=model.evaluate(before['player_0']['position'],before['player_1']['position'],case['style'],yaw,pitch)
                errors=[math.dist(before[f'player_{n}']['position'],case['source']if n==0 else case['enemy'])for n in[0,1]]
                row=dict(index=index,id=case['id'],style=case['style'],goals=dict(source=case['source'],enemy=case['enemy']),aim=case['aim'],pitch_delta=case.get('pitch_delta'),native_pitch=pitch,yaw=yaw,before=before,restore_within005=restored,requested_pose_errors=errors,paired_pose_eligible=max(errors)<=.05,model_recomputed_at_actual_pose=True,prediction=prediction,contact_predictions={receiver:model.contact(np.repeat([before['player_0']['position']],4,axis=0),np.repeat([before['player_1']['position']],4,axis=0),case['style'],yaw,pitch,receiver)for receiver in ['ColBullet','Body-candidate']},history=[])
                records.append(row);lab.save()
                for phase,count,press in [('hold',21 if case['style']=='full'else 1,True),('release',65,False)]:
                    for tick in range(count):
                        act=neutral();act['buttons'][0]=int(press)
                        lab.act(0,act,'v3-'+phase,1);row['history'].append(dict(phase=phase,tick=tick,infos=lab.env.process_infos))
                        if not lab.info(1)['alive']:break
                    if not lab.info(1)['alive']:break
                row['after']=lab.env.process_infos;aim.off();lab.save()
                print('D4_ATTACK3_CASE '+json.dumps(dict(id=case['id'],pose_errors=errors,pitch=pitch,predicted=prediction['hit'],uncertain=prediction['assembly_uncertain'],minimum_hp=min(h['infos']['player_1']['hp']for h in row['history']))),flush=True)
            lab.result.update(passed=True,driver_completed=True)
    except BaseException as e:
        lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc())
    finally:lab.finish()
    print('D4_ATTACK3_CLOSED '+str(lab.out),flush=True)
    return 0 if lab.result['passed']else 1

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--group',required=True);p.add_argument('--fit',type=Path,default=ROOT/'work/d4/restart-v3/attack-fit-v1.json');p.add_argument('--host',type=Path,default=ROOT/'work/d4/meter-v1/dmhost-aim');raise SystemExit(main(p.parse_args()))
