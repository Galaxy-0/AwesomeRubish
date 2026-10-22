"""Native final-light/zero-gauge order probe, ordinary attacks only.

One owned two-player room, no HP/gauge/pose writes. Full meter test option only
refills outside activation. Full70 primes the target shortly before final35;
all target HP and actual remaining gauge are retained, never repaired by memory.
"""
import argparse,json,sys,traceback,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.control import new_lab,fixture,Sensors,neutral,sha
from tools.zipcaster_d3r.weapon_aim import blade_angles
from tools.zipcaster_d3r.setup_navigation import place
from tools.zipcaster.validate_candidates import read_sensors

def main(a):
 a.thresholds=[a.counter/600];lab=new_lab('d4-zero2-'+a.name,1,a.host);parameters=json.loads(a.parameters.read_text());records=[];sensor=None
 lab.result.update(schema='inklab.d4.zero.v1',ideal_operation_fixture=True,full_d4_passed=False,records=records,requested_native_counter=a.counter,thresholds=a.thresholds,parameter_sha256=sha(a.parameters),method='Natural drain; full70 then final light. No HP/pose/gauge writes. Actual camera direction only.',events=[])
 (lab.out/'tested-zero_probe.py').write_bytes(Path(__file__).read_bytes())
 def step(label,button=0,style='light',count=1):
  for _ in range(count):
   p=lab.info(0)['position'];q=lab.info(1)['position'];yaw,pitch=blade_angles(p,q,parameters,style=style);aim.set_native(0,yaw,pitch);act=neutral();act['buttons'][0]=button;lab.act(0,act,label,1)
   if sensor:sensor.poll()
 def mark(event,rec=None):
  row=dict(event=event,infos=lab.env.process_infos,remaining_native=sensor.remaining if sensor else None,superhook_phase=sensor.phase if sensor else None);lab.result['events'].append(row)
  if rec is not None:rec['events'].append(row)
  lab.save();print('D4_ZERO_EVENT '+json.dumps(dict(event=event,frame=lab.info(0)['frame'],special=lab.info(0).get('special'),target_hp=lab.info(1)['hp'])),flush=True)
 try:
  with fixture(lab,roles=(0,),meter='full')as aim:
   lab.start();place(lab,{0:[0,3,8],1:[-8,3,8]});sensor=Sensors(lab)
   for index,threshold in enumerate(a.thresholds):
    aim.off()
    if lab.info(0)['remaining_time']<30:raise AssertionError('insufficient normal match time, unattempted cases retained')
    lab.paint_floor(1);lab.refill(1,180);lab.paint_floor(0);lab.refill(0,150);lab.step(lab.actions(),'d4-zero-heal',70)
    if not all(lab.info(n)['alive']and lab.info(n)['hp']>.999 for n in(0,1)):raise AssertionError('natural full-health precondition')
    record=dict(index=index,requested_light_gauge=threshold,events=[],eligible=False);records.append(record);mark('before-RS',record);act=neutral();act['buttons'][3]=1;lab.act(0,act,'d4-zero-RS',1);mark('after-RS',record)
    for _ in range(650):
     step('d4-zero-natural',style='full')
     value=lab.info(0).get('special')
     if lab.info(0).get('special_valid')and 0<value<=threshold+.19:break
    else:raise AssertionError('did not reach prime gauge')
    mark('prime-charge-start',record);step('d4-zero-prime-charge',1,'full',21);mark('prime-release',record);step('d4-zero-prime-flight',0,'full',36);mark('prime-end',record)
    # Keep failed primes as failures; no reselecting a damaging target/angle.
    record['prime70']=.27<=lab.info(1)['hp']<=.31
    for _ in range(90):
     if sensor.remaining is not None and sensor.remaining<=a.counter:break
     step('d4-zero-final-wait')
    mark('final-light-input',record);record['eligible']=record['prime70']and lab.info(0)['special']>0 and lab.info(1)['alive'];step('d4-zero-final-light',1);mark('final-light-release',record)
    step('d4-zero-pending-return',0,'light',145);mark('case-end',record);record['target_down']=not lab.info(1)['alive'];record['end']=lab.env.process_infos;lab.save()
    if index+1<len(a.thresholds)and not lab.info(1)['alive']:
     aim.off();place(lab,{0:[0,3,8],1:[-8,3,8]})
   lab.result.update(passed=True,driver_completed=True)
 except BaseException as e:lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc())
 finally:lab.finish()
 if lab.result.get('session'):
  p=lab.out/'sensors.jsonl';p.write_text(''.join(json.dumps(s)+'\n'for s in read_sensors(lab.result['session'])));lab.result['sensor_sha256']=sha(p);lab.save()
 print('D4_ZERO_CLOSED '+str(lab.out),flush=True);return 0 if lab.result['passed']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--counter',type=int,required=True);p.add_argument('--thresholds',type=float,nargs='+',default=[.07,.045,.025,.01]);p.add_argument('--host',type=Path,default=ROOT/'work/d4/sensor-v1/dmhost-aim');p.add_argument('--parameters',type=Path,default=ROOT/'work/d3r/attack-parameters-v1.json');raise SystemExit(main(p.parse_args()))
