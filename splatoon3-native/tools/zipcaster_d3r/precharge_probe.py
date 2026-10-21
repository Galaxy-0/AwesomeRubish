"""D3-R native ideal-operation upper bound, isolated test-only aim host.

Attacker may aim at known fixture target. Defender uses filtered observations,
18f reaction and measured finite yaw speed. No current hidden-target reads for
its aim. Bind failures count as tactic failures; setup failures are void.
"""
import argparse,json,math,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.control import new_lab,fixture,Sensors,neutral,sha
from tools.zipcaster_d3r.ray_model import inverse_pitch
from tools.zipcaster_d3r.aim_solver import hook_angles
from tools.zipcaster_d3r.weapon_aim import blade_angles
from tools.zipcaster.validate_candidates import read_sensors

def wrap(x):return math.atan2(math.sin(x),math.cos(x))
class Down(Exception):pass
class Defender:
 def __init__(self,aim,parameters,reaction=18):self.aim=aim;self.parameters=parameters;self.reaction=reaction;self.t=0;self.first=None;self.history=[];self.yaw=None
 def act(self,obs):
  self.t+=1;a=neutral();e=next((e for e in obs['enemies']if e['visible']and e['position']is not None),None)
  if e and self.first is None:self.first=self.t
  if not e or self.first is None or self.t-self.first<self.reaction:self.history.append(dict(t=self.t,visible=bool(e),fired=False));return a
  own=obs['own'];p=own['position'];q=e['position'];dx,dz=q[0]-p[0],q[2]-p[2];distance=math.hypot(dx,dz);bearing=math.atan2(dx,dz);old=own['view_yaw']if self.yaw is None else self.yaw;delta=wrap(bearing-old)
  # Finite mechanical operating speed retained; direct yaw isn't instantaneous
  # omnidirectional perception. No defender oracle/hp exposure.
  speed=math.radians(220.785)/60*min(1.,(self.t-self.first-self.reaction+1)/10);yaw=wrap(old+max(-speed,min(speed,delta)));elev=math.atan2(q[1]-p[1],max(distance,.01))
  pitch=max(-.85,min(.85,(elev-self.parameters['gun_elevation_bias'])/self.parameters['gun_elevation_scale']))
  self.yaw=yaw;self.aim.set_native(1,yaw,pitch);a['buttons'][0]=int(abs(wrap(bearing-yaw))<.14)
  self.history.append(dict(t=self.t,visible=True,target_sample=e['sample_frame'],fired=bool(a['buttons'][0]),yaw_error=delta,native_pitch=pitch,distance=distance));return a

def main(a):
 plan=json.loads(a.plan.read_text());p=next(x for x in plan['points']if x['id']==a.point and x.get('trial',a.trial)==a.trial);parameters=json.loads(a.parameters.read_text());ray=json.loads(a.ray.read_text())['parameters'];lab=new_lab('precharge-'+a.point+'-t'+str(a.trial),p['stage'],a.host);events=[];active=False;eligible=False;defender=None;original=lab.step
 lab.result.update(point=p,trial=a.trial,ideal_operation_fixture=True,rate_scope='ideal-operation upper bound',defender_mode='passive control'if a.passive else'filtered reactive52 R18 finite yaw',full_d3r_passed=False,calibration_eligible=False,parameter_sha256=sha(a.parameters),plan_sha256=sha(a.plan),ray_sha256=sha(a.ray),speed_frames=a.speed,events=events)
 for file in[Path(__file__),Path(__file__).with_name('control.py'),Path(__file__).with_name('ray_model.py'),Path(__file__).with_name('weapon_aim.py')]: (lab.out/('tested-'+file.name)).write_bytes(file.read_bytes())
 def mark(event):events.append(dict(event=event,infos=lab.env.process_infos));lab.save()
 def step(actions,label,frames=6):
  if not active:return original(actions,label,frames)
  out=None
  for _ in range(frames):
   if not all(lab.info(n)['alive']for n in(0,1)):raise Down()
   acts={k:{key:list(v)for key,v in val.items()}for k,val in actions.items()};acts['player_1']=neutral()if a.passive else defender.act(lab.obs(1));out=original(acts,label,1)
  return out
 lab.step=step
 try:
  with fixture(lab,roles=(0,1),meter='full')as aim:
   defender=Defender(aim,parameters);lab.start();hub=list(lab.atlas.points[lab.atlas.nearest(lab.atlas.region('center'))]);lab.navigate({0:hub,1:hub},'ideal-setup-hub');lab.navigate({0:p['source'],1:p['target']},'ideal-setup')
   if min(lab.info(n)['hp']for n in(0,1))<.999:raise AssertionError('full health precondition')
   h=p.get('headings',[0,math.pi/2,math.pi])[a.trial%3];aim.set_native(1,h,0);lab.step(lab.actions(),'ideal-defender-aim',4);act=neutral();act['sticks'][1]=.85;lab.act(1,act,'ideal-defender-body',8);aim.set_native(1,0,0,False);lab.step(lab.actions(),'ideal-defender-stop',12)
   source=lab.info(0)['position'];anchor=p['anchor'];yaw,pitch=hook_angles(source,lab.info(0)['heading'],anchor,ray);aim.set_native(0,yaw,pitch);lab.step(lab.actions(),'ideal-hook-aim',4)
   act=neutral();act['buttons'][3]=1;lab.act(0,act,'ideal-RS',1);lab.step(lab.actions(),'ideal-special-start',30)
   if min(lab.info(n)['hp']for n in(0,1))<.999:raise AssertionError('activation damaged target; setup void')
   sensor=Sensors(lab);sensor.poll();mark('before-R');active=True;eligible=True;act=neutral();act['buttons'][2]=1;lab.act(0,act,'ideal-R',1);saw=False;arrival=None
   for _ in range(120):
    acts=lab.actions();acts['player_0']['buttons'][0]=int(saw and sensor.phase==3);lab.step(acts,'ideal-flight-precharge',1);states=sensor.poll();saw|=any(s==3 for _,s in states)
    if saw and sensor.phase==0:arrival=lab.info(0)['frame'];mark('arrival');break
   if arrival is None:lab.result['tactic_failure']='native hook did not complete within120f'
   else:
    # B is ordinary detachment. User speed is arrival->full release; B and ZR
    # may overlap, but20f still needs a witnessed in-flight precharge frame.
    lab.result['precharge_probe']=True
    if a.speed!=20:raise ValueError('this bounded probe requires20f sensor-arrival release')
    def attack_step(label,n,button,jump=False,style='full'):
     for _ in range(n):
      own=lab.info(0)['position'];q=lab.info(1)['position'];yaw,pitch=blade_angles(own,q,parameters,style=style);aim.set_native(0,yaw,pitch);act=neutral();act['buttons'][0]=button;act['buttons'][4]=int(jump);lab.act(0,act,label,1)
    for t in range(a.speed):
     if t==a.speed-21:mark('charge-start')
     attack_step('ideal-charge'if t>=a.speed-21 else'ideal-prepare',1,int(t>=a.speed-21),t<6)
     if t==5:mark('B-end')
    mark('full-release');attack_step('ideal-full-flight',36,0);mark('light-input');attack_step('ideal-light',1,1,style='light');attack_step('ideal-light-flight',42,0,style='light');mark('combo-end')
   lab.result.update(passed=True,driver_completed=True)
 except Down:
  lab.result.update(passed=True,driver_completed=True);mark('first-down')
  # Pending emitted blades remain native after the owner falls.
  for _ in range(60):original(lab.actions(),'ideal-pending-settle',1)
  mark('duel-end')
 except BaseException as e:eligible=False;lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc())
 finally:
  lab.result.update(calibration_eligible=eligible and not a.passive,control_eligible=eligible and a.passive,reactive_history=defender.history if defender else[],outcome={key:(not bool(lab.info(n)['alive']))if lab.env.process_infos else None for key,n in [('kill',1),('attacker_down',0)]});lab.finish()
 if lab.result.get('session'):
  path=lab.out/'sensors.jsonl';path.write_text(''.join(json.dumps(s)+'\n'for s in read_sensors(lab.result['session'])));lab.result['sensor_sha256']=sha(path);lab.save()
 print('D3R_IDEAL_CLOSED '+str(lab.out),flush=True);return 0 if lab.result['passed']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--parameters',type=Path,required=True);p.add_argument('--ray',type=Path,default=ROOT/'work/d3r/ray-v2-frozen.json');p.add_argument('--point',required=True);p.add_argument('--trial',type=int,default=0);p.add_argument('--speed',type=int,default=20);p.add_argument('--passive',action='store_true');p.add_argument('--host',type=Path,default=ROOT/'work/d3r/aim-v1/dmhost-aim');raise SystemExit(main(p.parse_args()))
