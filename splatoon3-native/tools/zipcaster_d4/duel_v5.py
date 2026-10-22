"""D4 trusted ideal-aim fixture; stationary .52 and fixed logical180deg cone.

No policy protocol changes. Full-special prefill and direct aim are test-only;
pose/HP/collision/damage remain native. Setup voids are distinct from losses.
"""
import argparse,json,math,sys,traceback
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.control import new_lab,fixture,neutral,sha
from tools.zipcaster_d3r.weapon_aim import blade_angles
from tools.zipcaster_d3r.aim_solver import hook_angles
from tools.zipcaster_d3r.setup_navigation import place
from tools.zipcaster_d4.zero_probe_v4 import Meter
from tools.zipcaster_d4.model_v2 import World,schedule
from tools.zipcaster.validate_candidates import read_sensors
class Down(Exception):pass
class FixedDefender:
 def __init__(self,lab,aim,world,parameters,heading):self.lab=lab;self.aim=aim;self.world=world;self.parameters=parameters;self.heading=heading;self.history=[]
 def act(self):
  p=np.array(self.lab.info(0)['position']);q=np.array(self.lab.info(1)['position']);v,d=self.world.visibility(p[None,:],q,self.heading);a=neutral();fire=bool(d[0])
  if fire:
   delta=p-q;pitch=(math.atan2(delta[1],math.hypot(delta[0],delta[2]))-self.parameters['gun_elevation_bias'])/self.parameters['gun_elevation_scale'];self.aim.set_native(1,math.atan2(delta[0],delta[2]),max(-.85,min(.85,pitch)));a['buttons'][0]=1
  self.history.append(dict(frame=self.lab.info(0)['frame'],visible=bool(v[0]),in_range=bool(d[0]),fired=fire,source=p.tolist(),enemy=q.tolist()));return a

def main(a):
 plan=json.loads(a.plan.read_text());point=next(p for p in plan['points']if p['id']==a.point);graph=ROOT/point['graph'];world=World(graph);z=world.graph;params=json.loads(a.parameters.read_text());ray=json.loads(a.ray.read_text())['parameters'];lab=new_lab('d4-duel5-'+a.point+'-h'+str(a.hold_r)+'-r'+str(a.repeat),world.meta['stage'],a.host);active=False;eligible=False;sensor=None;defender=None;events=[];original=lab.step
 lab.result.update(schema='inklab.d4.native.duel.v1',point=point,repeat=a.repeat,events=events,ideal_operation_fixture=True,calibration_eligible=False,full_d4_passed=False,attack_pitch_bias=dict(full=a.full_pitch_bias,light=a.light_pitch_bias),diagnostic_only=True,plan_sha256=sha(a.plan),graph_sha256=sha(graph/'graph.npz'),parameter_sha256=sha(a.parameters),ray_sha256=sha(a.ray),scope='Stationary fixed logical FOV; ideal gun aim inside cone, no intrinsic spread edits. All native damage retained; D4 kill additionally requires native HP receipt before gauge zero.')
 for p in[Path(__file__),Path(__file__).with_name('model_v2.py'),Path(__file__).with_name('zero_probe_v4.py')]: (lab.out/('tested-'+p.name)).write_bytes(p.read_bytes())
 def mark(event):
  sensor.poll();events.append(dict(event=event,infos=lab.env.process_infos,counter=sensor.remaining,meter_frame=getattr(sensor,'meter_frame',None),hook_phase=sensor.phase));lab.save();print('D4_DUEL_EVENT '+json.dumps(dict(event=event,frame=lab.info(0)['frame'],hp=[lab.info(n)['hp']for n in[0,1]],counter=sensor.remaining)),flush=True)
 def step(actions,label,frames=6):
  if not active:return original(actions,label,frames)
  out=None
  for _ in range(frames):
   if not all(lab.info(n)['alive']for n in[0,1]):raise Down()
   acts={k:{key:list(v)for key,v in val.items()}for k,val in actions.items()};acts['player_1']=neutral()if a.passive else defender.act();out=original(acts,label,1);sensor.poll()
  return out
 lab.step=step
 try:
  with fixture(lab,roles=(0,1),meter='full')as aim:
   lab.start();place(lab,{0:point['source'],1:point['enemy']});aim.off();lab.step(lab.actions(),'d4-natural-settle',60)
   errors=[math.dist(lab.info(n)['position'],point['source']if n==0 else point['enemy'])for n in[0,1]];lab.result['setup_errors']=errors
   if max(errors)>1.5 or min(lab.info(n)['hp']for n in[0,1])<.999:raise AssertionError('ordinary setup position/full-health precondition')
   sensor=Meter(lab)
   if point.get('band')=='control':
    source=np.array(lab.info(0)['position']);enemy=np.array(lab.info(1)['position']);heading=point['heading']*math.pi/2;visible,danger=world.visibility(source[None,:],enemy,heading);delta=source-enemy;margin=delta[0]*math.sin(heading)+delta[2]*math.cos(heading);lab.result['initial_control_precondition']=dict(visible=bool(visible[0]),danger=bool(danger[0]),forward_margin=float(margin),required=point['minimum_actual_control_margin'])
    if not danger[0]or margin<point['minimum_actual_control_margin']:raise AssertionError('pre-RS control actual pose outside predeclared interior threat margin (setup void)')
   defender=FixedDefender(lab,aim,world,params,point['heading']*math.pi/2);aim.set_native(1,point['heading']*math.pi/2,0);
   if point['hooks']:
    hook=point['hooks'][0];center=z['anchors'][hook]+z['normals'][hook]*.4;yaw,pitch=hook_angles(lab.info(0)['position'],lab.info(0)['heading'],center,ray);aim.set_native(0,yaw,pitch);lab.step(lab.actions(),'d4-first-hook-preaim',4)
   mark('before-RS');active=True;eligible=True
   act=neutral();act['buttons'][3]=1;lab.act(0,act,'d4-RS',6);lab.step(lab.actions(),'d4-activation',25);mark('activation-ready')
   if sensor.remaining is None or sensor.remaining<400:eligible=False;raise AssertionError('activation not acknowledged (setup void)')
   for hook in point['hooks']:
    if events[-1]['event']=='arrival':
     act=neutral();act['buttons'][4]=1;lab.act(0,act,'d4-B-rehook',6);mark('B-rehook-end')
    center=z['anchors'][hook]+z['normals'][hook]*.4;yaw,pitch=hook_angles(lab.info(0)['position'],lab.info(0)['heading'],center,ray);aim.set_native(0,yaw,pitch);mark('hook-input');act=neutral();act['buttons'][2]=1;lab.act(0,act,'d4-hook-press',a.hold_r);saw=sensor.phase==3
    for _ in range(140):
     lab.step(lab.actions(),'d4-hook-flight',1);saw|=sensor.phase==3
     if saw and sensor.phase==0:break
    else:lab.result['tactic_failure']='no native flight completion in140f';raise Down()
    mark('arrival')
   inputs=schedule(point['speed'],point['program']);last=inputs[-1][0]+85
   for t in range(last):
    full_charge=any(k=='full'and event-21<=t<event for event,k in inputs);light=any(k=='light'and t==event for event,k in inputs);next_kind=next((k for event,k in inputs if event+(6 if k=='full'else 11)+5>=t),'light');yaw,pitch=blade_angles(lab.info(0)['position'],lab.info(1)['position'],params,style=next_kind);pitch=max(-.85,min(.85,pitch+(a.full_pitch_bias if next_kind=='full' else a.light_pitch_bias)));aim.set_native(0,yaw,pitch);act=neutral();act['buttons'][0]=int(full_charge or light);act['buttons'][4]=int(bool(point['hooks'])and t<6)
    for event,kind in inputs:
     if t==event-(21 if kind=='full'else 0):mark('charge-start'if kind=='full'else'light-input')
     if t==event and kind=='full':mark('full-release')
    lab.act(0,act,'d4-combo-'+next_kind,1)
   mark('combo-end');lab.result.update(passed=True,driver_completed=True)
 except Down:
  lab.result.update(passed=True,driver_completed=True)
  if sensor:mark('first-down-or-tactic-failure')
  for _ in range(60):original(lab.actions(),'d4-native-pending-settle',1)
  if sensor:mark('duel-end')
 except BaseException as e:lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc())
 finally:
  lab.result.update(calibration_eligible=eligible and not a.passive,defender_history=defender.history if defender else[],outcome={key:(not bool(lab.info(n)['alive']))if lab.env.process_infos else None for key,n in [('native_kill',1),('attacker_down',0)]});lab.finish()
 if lab.result.get('session'):
  p=lab.out/'sensors.jsonl';p.write_text(''.join(json.dumps(s)+'\n'for s in read_sensors(lab.result['session'])));lab.result['sensor_sha256']=sha(p);lab.save()
 print('D4_DUEL_CLOSED '+str(lab.out),flush=True);return 0 if lab.result['passed']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--point',required=True);p.add_argument('--repeat',type=int,default=0);p.add_argument('--hold-r',type=int,choices=[1,4],default=1);p.add_argument('--passive',action='store_true');p.add_argument('--full-pitch-bias',type=float,default=0.);p.add_argument('--light-pitch-bias',type=float,default=0.);p.add_argument('--parameters',type=Path,default=ROOT/'work/d3r/attack-parameters-v1.json');p.add_argument('--ray',type=Path,default=ROOT/'work/d3r/ray-v2-frozen.json');p.add_argument('--host',type=Path,default=ROOT/'work/d4/meter-v1/dmhost-aim');raise SystemExit(main(p.parse_args()))
