"""Read-only bullet coordinate discovery fixture; bounded one room, no specials."""
import argparse,json,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import DuelLab,owned_options,neutral,ROOT,MODULES
from serve import fast_align
p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--host',type=Path,required=True);p.add_argument('--capture',type=Path);a=p.parse_args()
lab=DuelLab(a.name,host=a.host,modules=ROOT/'work/a7/patched-seeds-v16')
try:
 with owned_options(bullets=True,capture=a.capture):
  lab.start();lab.navigate({0:[0,3,8],1:[-4,3,5.5]},'bullet-setup')
  q=lab.info(0)['position'];fast_align(lab,1,[q[0],q[1]+1.1,q[2]],'bullet-align')
  if a.capture:a.capture.resolve().touch(exist_ok=False)
  lab.result['before_shoot']=lab.env.process_infos;lab.save();print('D3_BULLET_READY '+str(lab.out),flush=True)
  for trial,(pitch,yaw)in enumerate([(0,0),(0,.15),(-.15,0),(.15,0)]):
   a=neutral();a['sticks'][2]=yaw;a['gyro'][0]=pitch
   lab.act(1,a,'bullet-turn-'+str(trial),8);a=neutral();a['buttons'][0]=1
   for f in range(28):lab.act(1,a,'bullet-shot-'+str(trial),1)
   for f in range(35):lab.step(lab.actions(),'bullet-flight-'+str(trial),1)
  lab.result.update(passed=True,driver_completed=True)
except BaseException as e:lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc())
finally:lab.finish()
print('D3_BULLET_CLOSED '+str(lab.out),flush=True)
raise SystemExit(0 if lab.result['passed']else 1)
