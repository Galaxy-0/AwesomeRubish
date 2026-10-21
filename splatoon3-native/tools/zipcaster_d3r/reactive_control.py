"""Exact D3-R defender threat gate: filtered observations, static native target.

Private direct aim + R18/finite yaw; output includes actual damage edges and
birth vectors. No target-control input/HP write during the measured window.
"""
import argparse,json,math,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.control import new_lab,fixture,neutral,sha
from tools.zipcaster_d3r.duel_v3 import Defender
from tools.zipcaster_d3r.analyze_direction import PAT

def main(a):
 lab=new_lab('reactive-'+a.name,1,a.host);history=[];defender=None;parameters=json.loads(a.parameters.read_text());lab.result.update(ideal_operation_fixture=True,full_d3r_passed=False,rate_scope='exact defender threat control; not native ranking cohort',parameter_sha256=sha(a.parameters))
 for f in[Path(__file__),Path(__file__).with_name('duel_v3.py')]: (lab.out/('tested-'+f.name)).write_bytes(f.read_bytes())
 try:
  with fixture(lab,roles=(1,),meter='full')as aim:
   lab.start();lab.navigate({0:[0,3,8],1:[-a.distance,3,8]},'reactive-setup');p=lab.info(1)['position'];q=lab.info(0)['position'];bearing=math.atan2(q[0]-p[0],q[2]-p[2]);aim.set_native(1,bearing+a.angle,0);lab.step(lab.actions(),'reactive-setup-aim',4);act=neutral();act['sticks'][1]=.85;lab.act(1,act,'reactive-body-face',8);aim.off();lab.step(lab.actions(),'reactive-stop',80)
   if min(lab.info(n)['hp']for n in(0,1))<.999:raise AssertionError('full-health static control required')
   lab.result['initial']=lab.env.process_infos;defender=Defender(aim,parameters)
   for t in range(180):
    acts=lab.actions();acts['player_1']=defender.act(lab.obs(1));lab.step(acts,'reactive-measured',1);history.append(lab.env.process_infos)
    if not lab.info(0)['alive']:break
   lab.result.update(driver_completed=True,final=lab.env.process_infos)
 except BaseException as e:lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc())
 finally:
  lab.result.update(history=history,reactive_history=defender.history if defender else[]);lab.finish()
 if lab.result.get('initial'):
  last=lab.result['initial']['player_0']['hp'];edges=[];start=lab.result['initial']['player_1']['frame']
  for h in history:
   hp=h['player_0']['hp'];delta=(last-hp)*100
   if delta>.001:edges.append(dict(control_frame=h['player_1']['frame']-start,target_native_frame=h['player_0']['frame'],damage_hp=delta))
   last=hp
  large=[e for e in edges if e['damage_hp']>=30];lab.result['damage_edges']=edges;lab.result['large_damage_edges']=large;lab.result['threat_passed']=bool(len(large)>=2 and not lab.info(0)['alive']and any(h['fired']for h in defender.history));lab.result['passed']=bool(lab.result['threat_passed']and not lab.result['errors']);lab.save()
 print('D3R_THREAT_CLOSED '+str(lab.out),flush=True);return 0 if lab.result['passed']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--distance',type=float,default=6);p.add_argument('--angle',type=float,default=0);p.add_argument('--parameters',type=Path,default=ROOT/'work/d3r/attack-parameters-v1.json');p.add_argument('--host',type=Path,default=ROOT/'work/d3r/aim-v1/dmhost-aim');raise SystemExit(main(p.parse_args()))
