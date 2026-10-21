"""Independent fixed-source casts, ordinary return/RS; no combat actions.

Eight directions per fresh native match; full/infinite meter is fixture-only.
All target predictions and input angles precede native evidence collection.
"""
import argparse,json,math,sys,traceback,subprocess,os,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.control import new_lab,fixture,Sensors,neutral,sha
from arena.lib.atlas import MapAtlas
from tools.zipcaster.validate_candidates import read_sensors

MAPS=['Yunohana','District00','Yagara'];REGIONS=['center','central_high','west_lane','east_lane','center']
def plan(a):
 data=json.loads((ROOT/'work/d2/map-analysis-full.json').read_text());jobs=[]
 for batch,region in enumerate(REGIONS):
  for stage,m in enumerate(data['maps'],1):
   atlas=MapAtlas.load(stage);source=np.asarray(atlas.points[atlas.nearest(atlas.region(region))]);pool=[]
   for c in m['candidates']:
    delta=np.asarray(c['anchor'])-source-[0,1.1,0];length=np.linalg.norm(delta)
    if not 5<length<34 or not -.7<math.atan2(delta[1],np.linalg.norm(delta[[0,2]]))<.8:continue
    if 'SuperHookCantBind'in c['material_flags']or'SplPlayerSuperHookCheck'in c['collision_disabled']:continue
    # Fixed deterministic space coverage; status does not label new native pass.
    value=(c['landing_view_percent']or 0)-.2*length+(5 if c['native_status']!='candidate'else 0)
    pool.append((value,c,delta/length))
   chosen=[];vectors=[]
   ordered=sorted(pool,key=lambda x:(-x[0],x[1]['id']))
   if batch==4:ordered=list(reversed(ordered))
   for _,c,u in ordered:
    if any(float(u@q)>math.cos(math.radians(6))for q in vectors):continue
    chosen.append(dict(id=c['id'],target=c['anchor'],normal=c['normal'],material_flags=c['material_flags'],kind='sampled-wall'));vectors.append(u)
    if len(chosen)==6:break
   if len(chosen)!=6:raise ValueError('insufficient angular coverage '+m['id']+' '+region)
   for sign in [-1,1]:
    yaw=batch*math.pi/3+sign*.4;pitch=.75 if sign==1 else-.55
    chosen.append(dict(id=f'probe-{batch}-{sign}',yaw=yaw,pitch=pitch,kind='untargeted-direction'))
   rng=np.random.default_rng(520321+stage*31+batch);held=set(map(int,rng.choice(6,2,replace=False)))|{int(rng.integers(6,8))}
   for index,p in enumerate(chosen):p['split']='held-out'if index in held else'train'
   jobs.append(dict(stage=stage,map=m['id'],batch=batch,source_region=region,source=source.tolist(),casts=chosen))
 out=dict(schema='inklab.d3r.mapping.plan.v1',jobs=jobs,planned_casts=sum(len(j['casts'])for j in jobs),source_sha256={str(p.relative_to(ROOT)):sha(p)for p in [Path(__file__),ROOT/'work/d2/map-analysis-full.json']},fixed_prior='5 source batches x3 maps x8 casts; six angularly distinct sampled walls and2 unconditioned directions. Center second batch reverses candidate ordering. No selection on this native cohort outcomes.')
 if a.plan.exists():raise ValueError('fresh plan path required')
 a.plan.parent.mkdir(parents=True,exist_ok=True);a.plan.write_text(json.dumps(out,indent=2)+'\n');print('PLANNED '+str(out['planned_casts']))

def room(a):
 job=next(j for j in json.loads(a.plan.read_text())['jobs']if j['stage']==a.stage and j['batch']==a.batch);lab=new_lab(f'map-b{a.batch}-{job["map"]}-a{a.attempt}',a.stage,a.host);records=[];lab.result.update(mapping_job=job,mapping_plan_sha256=sha(a.plan),measurement_only=True,ideal_operation_fixture=True,full_d3r_passed=False,records=records)
 (lab.out/'tested-hook_mapping.py').write_bytes(Path(__file__).read_bytes());(lab.out/'tested-control.py').write_bytes(Path(__file__).with_name('control.py').read_bytes())
 try:
  with fixture(lab)as aim:
   lab.start()
   if a.attempt>1:
    hub=list(lab.atlas.points[lab.atlas.nearest(lab.atlas.region('center'))]);lab.navigate({0:hub},'map-setup-hub')
   lab.navigate({0:job['source']},'map-fixed-source');sensor=Sensors(lab);sensor.poll()
   for index,p in enumerate(job['casts']):
    if lab.info(0)['remaining_time']<22:lab.result['bounded_early_stop']='remaining native time<22s; unattempted casts not binding failures';break
    before=lab.info(0);origin=np.asarray(before['position']);rec=dict(index=index,proposal=p,eligible=False,before=lab.env.process_infos);records.append(rec);lab.save()
    if not before['alive']or before['special']<.99:raise AssertionError('healthy ready-meter setup missing')
    if p['kind']=='sampled-wall':
     delta=np.asarray(p['target'])-origin-[0,1.1,0];yaw=math.atan2(delta[0],delta[2]);pitch=max(-.85,min(.85,math.atan2(delta[1],np.linalg.norm(delta[[0,2]]))-.04))
    else:yaw,pitch=p['yaw'],p['pitch']
    command=aim.set_native(0,yaw,pitch);lab.step(lab.actions(),'map-direct-aim',4)
    act=neutral();act['buttons'][3]=1;lab.act(0,act,'map-RS',1);lab.step(lab.actions(),'map-special-startup',30);rec.update(command=command,before_R=lab.env.process_infos)
    sensor.poll();start=lab.info(0)['frame'];act=neutral();act['buttons'][2]=1;lab.act(0,act,'map-R',1);phases=[];saw_flight=False;arrival=None
    for _ in range(120):
     lab.step(lab.actions(),'map-release',1);new=[(f,s)for f,s in sensor.poll()if f>=start];phases.extend(new);saw_flight|=any(s==3 for _,s in new)
     if saw_flight and sensor.phase==0 and arrival is None:arrival=lab.info(0)['frame'];rec['arrival_first_ack']=lab.env.process_infos
     if arrival is not None and lab.info(0)['frame']==arrival+8:rec['arrival_settled_ack']=lab.env.process_infos
    rec.update(eligible=True,flight_end=lab.env.process_infos,phases=phases);lab.save();aim.off();lab.step(lab.actions(),'map-natural-return',650);rec['returned']=lab.env.process_infos;lab.save()
   lab.result.update(passed=True,driver_completed=True)
 except BaseException as e:lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc())
 finally:lab.finish()
 if lab.result.get('session'):
  path=lab.out/'sensors.jsonl';path.write_text(''.join(json.dumps(s)+'\n'for s in read_sensors(lab.result['session'])));lab.result['sensor_sha256']=sha(path);lab.save()
 print('D3R_MAP_CLOSED '+str(lab.out),flush=True);return 0 if lab.result['passed']else 1

def batch(a):
 if a.out.exists():raise ValueError('fresh batch output required')
 a.out.mkdir(parents=True);jobs=json.loads(a.plan.read_text())['jobs'];results=[];began=time.monotonic()
 def run(j):
  log=a.out/f'{j["map"]}-b{j["batch"]}.log';cmd=[sys.executable,__file__,'room','--plan',str(a.plan),'--stage',str(j['stage']),'--batch',str(j['batch']),'--host',str(a.host)]
  with log.open('w')as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env={k:v for k,v in os.environ.items()if not k.startswith('DM_')})
  lines=[l for l in log.read_text().splitlines()if l.startswith('D3R_MAP_CLOSED ')];path=Path(lines[-1].split(' ',1)[1])/'result.json'if lines else None;d=json.loads(path.read_text())if path else{}
  return dict(map=j['map'],batch=j['batch'],exit_code=r.returncode,artifact=str(path.relative_to(ROOT))if path else None,passed=d.get('passed',False),eligible_casts=sum(c['eligible']for c in d.get('records',[])),errors=d.get('errors',[]))
 with ThreadPoolExecutor(max_workers=3)as pool:
  for f in as_completed([pool.submit(run,j)for j in jobs]):
   r=f.result();results.append(r);(a.out/'batch.json').write_text(json.dumps(dict(results=results,rooms=3,seconds=time.monotonic()-began),indent=2)+'\n');print('MAP_ROOM '+json.dumps(r),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['plan','room','batch']);p.add_argument('--plan',type=Path,default=ROOT/'work/d3r/map-plan-v1.json');p.add_argument('--out',type=Path);p.add_argument('--stage',type=int);p.add_argument('--batch',type=int);p.add_argument('--attempt',type=int,choices=[1,2],default=1);p.add_argument('--host',type=Path,default=ROOT/'work/d3r/aim-v1/dmhost-aim');a=p.parse_args();a.plan=a.plan.resolve();a.host=a.host.resolve();a.out=a.out.resolve()if a.out else None;raise SystemExit(room(a)if a.mode=='room'else plan(a)if a.mode=='plan'else batch(a))
