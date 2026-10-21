"""Native pitch/hit-window control. Private aim only; HP/pose never written.

Fixed grid declared before collection. Stationary target, natural heal/refill.
Both successful and unsuccessful shots retained. Not a combat-rate benchmark.
"""
import argparse,json,math,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.control import new_lab,fixture,neutral,sha
from tools.zipcaster_d3r.analyze_direction import PAT,angle

def main(a):
 lab=new_lab('blade-v2-'+a.kind+'-'+a.name,1,a.host);records=[];lab.result.update(ideal_operation_fixture=True,full_d3r_passed=False,probe_kind=a.kind,records=records)
 (lab.out/'tested-blade_probe.py').write_bytes(Path(__file__).read_bytes())
 try:
  with fixture(lab,roles=(0,1))as aim:
   lab.start();lab.navigate({0:[0,3,8],1:[-8,3,8]},'blade-setup')
   shooter=1 if a.kind=='defender'else 0;target=1-shooter
   # Same known flat layout as independently proven reactive close-range gate.
   # Native source/target actual positions are always recorded, not assumed.
   if a.kind=='defender':cases=[('gun',1,p)for p in [-.22,-.16,-.10,-.04,.02,.08]]
   else:cases=[(style,hold,p)for style,hold in [('full',21),('light',1)]for p in [-.30,-.20,-.10,0.,.10,.20,.30]]
   if a.kind=='flat'and a.style!='all':cases=[c for c in cases if c[0]==a.style]
   lab.result['predeclared_cases']=cases;lab.result['recovery']='ordinary target floor painting/refill, no HP write';lab.save()
   for index,(style,hold,pitch)in enumerate(cases):
    aim.off()
    if lab.info(0)['remaining_time']<22:lab.result['bounded_early_stop']='less22s remaining, unattempted angles retained';break
    lab.paint_floor(target);lab.refill(target,240);lab.step(lab.actions(),'blade-target-ready',40)
    if not all(lab.info(n)['alive']and lab.info(n)['hp']>.999 for n in(0,1)):
     lab.result['bounded_early_stop']='target not naturally full health/alive; do not repair measured HP';break
    if shooter==0:lab.paint_floor(shooter);lab.refill(shooter,240);lab.step(lab.actions(),'blade-ready',40)
    p=lab.info(shooter)['position'];q=lab.info(target)['position'];yaw=math.atan2(q[0]-p[0],q[2]-p[2]);command=aim.set_native(shooter,yaw,pitch);lab.step(lab.actions(),'blade-native-aim',4)
    rec=dict(index=index,style=style,hold=hold,native_pitch=pitch,command=command,before=lab.env.process_infos,history=[]);records.append(rec);lab.save()
    # Whole hold/release is sampled per present to retain exact damage windows.
    for label,n,pressed in [('hold',hold,True),('release',60,False)]:
     for tick in range(n):
      act=neutral();act['buttons'][0]=int(pressed);lab.act(shooter,act,'blade-'+style+'-'+label,1);rec['history'].append(dict(label=label,tick=tick,infos=lab.env.process_infos))
      if not lab.info(target)['alive']:break
     if not lab.info(target)['alive']:break
    rec['after']=lab.env.process_infos;aim.off();lab.save()
   if a.kind=='defender':
    hits=[r for r in records if min(h['infos']['player_0']['hp']for h in r['history'])<r['before']['player_0']['hp']-.1]
    if hits:
     best=min(hits,key=lambda r:abs(r['native_pitch']));aim.off();lab.paint_floor(0);lab.refill(0,240);lab.step(lab.actions(),'gun-control-heal',40)
     p=lab.info(1)['position'];q=lab.info(0)['position'];yaw=math.atan2(q[0]-p[0],q[2]-p[2]);aim.set_native(1,yaw,best['native_pitch']);lab.step(lab.actions(),'gun-control-aim',4)
     act=neutral();act['sticks'][1]=.85;lab.act(1,act,'gun-control-body',8);lab.step(lab.actions(),'gun-control-stop',80)
     if lab.info(0)['hp']<.999:raise AssertionError('gun control full-health precondition')
     p=lab.info(1)['position'];q=lab.info(0)['position'];aim.set_native(1,math.atan2(q[0]-p[0],q[2]-p[2]),best['native_pitch']);lab.step(lab.actions(),'gun-control-final-aim',4)
     control=dict(selected_pitch=best['native_pitch'],selection='closest-to-zero observed damaging pitch; separate adaptive control, not held-out calibration',before=lab.env.process_infos,history=[]);lab.result['close_threat_control']=control
     for tick in range(120):
      act=neutral();act['buttons'][0]=1;lab.act(1,act,'gun-control-continuous',1);control['history'].append(lab.env.process_infos)
      if not lab.info(0)['alive']:break
     control.update(after=lab.env.process_infos,target_down=not bool(lab.info(0)['alive']));aim.off();lab.save()
   lab.result.update(passed=True,driver_completed=True)
 except BaseException as e:lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc())
 finally:lab.finish()
 print('D3R_BLADE_CLOSED '+str(lab.out),flush=True);return 0 if lab.result['passed']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--kind',choices=['flat','defender'],required=True);p.add_argument('--name',required=True);p.add_argument('--style',choices=['full','light','all'],default='all');p.add_argument('--host',type=Path,default=ROOT/'work/d3r/aim-v1/dmhost-aim');raise SystemExit(main(p.parse_args()))
