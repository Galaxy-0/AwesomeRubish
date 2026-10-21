"""Bounded physical-direction A/B; no combat-rate claims from camera readback."""
import argparse,json,sys,math,traceback
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'tools/zipcaster_d3'),str(ROOT)]
from native import DuelLab,owned_options,neutral,sha,NativeSession
from serve import fast_align
from validate_candidates import read_sensors
def main(a):
 lab=DuelLab('r-direct-'+a.mode+'-'+a.name,host=a.host,modules=a.host.parent/'modules');seq=[0,0];events=[];files=[lab.out/f'aim-{n}.txt'for n in (0,1)];capture=lab.out/'capture-bullets'
 def aim(n,yaw=0,pitch=0,enabled=False):
  seq[n]+=1;p=files[n];tmp=p.with_suffix('.tmp');tmp.write_text(f'D3Rv1 {seq[n]} {int(enabled)} {yaw:.9g} {pitch:.9g}\n');tmp.replace(p);events.append(dict(event='command',player=n,seq=seq[n],enabled=enabled,yaw=yaw,pitch=pitch))
 def mark(label):events.append(dict(event=label,infos=lab.env.process_infos));lab.result['events']=events;lab.save()
 lab.result.update(d3r_probe=a.mode,probe_sha256=sha(__file__),ideal_operation_fixture=not a.disabled,full_d3r_passed=False)
 (lab.out/'tested-probe.py').write_bytes(Path(__file__).read_bytes())
 try:
  with owned_options(special=a.mode=='hook',sensors=a.mode=='hook',meter='infinite',bullets=a.mode=='gun',capture=capture if a.mode=='gun'else None):
   original=NativeSession.host_options
   def options(self,n):return original(self,n) if a.disabled else original(self,n)|dict(DM_TEST_AIM='1',DM_TEST_AIM_FILE=str(files[n]))|({'DM_D3R_DUMP':'1'}if a.dump else{})
   with patch.object(NativeSession,'host_options',options):
    for n in (0,1):aim(n)
    lab.start();mark('loaded')
    if a.mode=='gun':
     lab.navigate({0:[0,3,8],1:[-8,3,8]},'r-gun-place');q=lab.info(1)['position'];target=[q[0]+10,q[1]+4,q[2]+10];fast_align(lab,1,target,'r-controller-reference');lab.step(lab.actions(),'r-reference-settle',20);mark('reference-view');view=lab.info(1)['own_view'];yaw,pitch=view['yaw'],view['pitch'];capture.touch()
     for group,y,p,enabled in [('controller',yaw,pitch,False),('direct-same',yaw,pitch,True),('direct-changed',math.atan2(math.sin(yaw+1.),math.cos(yaw+1.)),.1,True)]:
      aim(1,y,p,enabled);lab.step(lab.actions(),'r-'+group+'-settle',12);mark(group+'-before')
      for j in range(6):
       if not enabled:fast_align(lab,1,target,'r-controller-realign')
       act=neutral();act['buttons'][0]=1;mark(group+'-shot-'+str(j));lab.act(1,act,'r-'+group+'-fire',1);lab.step(lab.actions(),'r-'+group+'-release',14)
      mark(group+'-after')
     capture.unlink();aim(1);lab.step(lab.actions(),'r-disabled',12);mark('disabled')
    elif a.mode=='sword':
     lab.navigate({0:[0,3,8],1:[-8,3,8]},'r-sword-place');q=lab.info(0)['position'];target=[q[0]+10,q[1]+4,q[2]+10];fast_align(lab,0,target,'r-sword-reference');lab.step(lab.actions(),'r-reference-settle',20);mark('reference-view');view=lab.info(0)['own_view'];yaw,pitch=view['yaw'],view['pitch']
     for group,enabled,y,p in [('controller',False,yaw,pitch),('direct-same',True,yaw,pitch),('direct-changed',True,math.atan2(math.sin(yaw+1.),math.cos(yaw+1.)),.1)]:
      if enabled:
       aim(0);lab.paint_floor(0);lab.refill(0,240);lab.step(lab.actions(),'r-refill-standing-ready',60)
      aim(0,y,p,enabled);lab.step(lab.actions(),'r-'+group+'-settle',12);mark(group+'-before')
      for style,hold,release in [('light',1,35),('full',21,42)]:
       for j in range(3):
        if not enabled:fast_align(lab,0,target,'r-controller-realign')
        mark(group+'-'+style+'-shot-'+str(j));act=neutral();act['buttons'][0]=1;lab.act(0,act,'r-'+group+'-'+style,hold);lab.step(lab.actions(),'r-'+group+'-release',release)
      mark(group+'-after')
     aim(0);lab.step(lab.actions(),'r-disabled',12);mark('disabled')
    else:
     point=next(p for p in json.loads((ROOT/'work/d2c/selection.json').read_text())['points']if p['id']=='Yunohana-hook-0532');lab.navigate({0:point['source'],1:point['target']},'r-hook-place');lab.result['point']=point
     fast_align(lab,0,point['requested_anchor'],'r-hook-reference');lab.step(lab.actions(),'r-hook-reference-settle',12);view=lab.info(0)['own_view'];yaw,pitch=view['yaw'],view['pitch'];mark('hook-reference')
     for label,enabled in [('controller',False),('direct-same',True)]:
      aim(0,yaw,pitch,enabled);lab.step(lab.actions(),'r-'+label+'-aim',12)
      act=neutral();act['buttons'][3]=1;lab.act(0,act,'r-'+label+'-RS',1);lab.step(lab.actions(),'r-'+label+'-startup',30);mark(label+'-before-R')
      act=neutral();act['buttons'][2]=1;lab.act(0,act,'r-'+label+'-R',1);lab.step(lab.actions(),'r-'+label+'-release',120);mark(label+'-flight-end');aim(0);lab.step(lab.actions(),'r-'+label+'-return',650);mark(label+'-returned')
    lab.result.update(passed=True,driver_completed=True)
 except BaseException as e:lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc())
 finally:lab.result['events']=events;lab.finish()
 if a.mode=='hook'and lab.result.get('session'):
  p=lab.out/'sensors.jsonl';p.write_text(''.join(json.dumps(s)+'\n'for s in read_sensors(lab.result['session'])));lab.result['sensor_sha256']=sha(p);lab.save()
 print('D3R_CLOSED '+str(lab.out),flush=True);return 0 if lab.result['passed']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--mode',choices=['gun','hook','sword'],required=True);p.add_argument('--host',type=Path,default=ROOT/'work/d3r/aim-r1/dmhost-aim');p.add_argument('--dump',action='store_true');p.add_argument('--disabled',action='store_true');a=p.parse_args();a.host=a.host.resolve();raise SystemExit(main(a))
