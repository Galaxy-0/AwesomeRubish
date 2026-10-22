"""Bounded native scheduler: <=3 rooms, source freeze, graceful STOP_LAUNCH.

Breadth-first repeats test every state early. Prior exact-input trials are
retained regardless of combat outcome. Setup voids get at most one retry;
two setup failures for one case stop launches, current rooms finish normally.
"""
import argparse,json,subprocess,sys,time,hashlib,shutil
from collections import deque
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def atomic(path,data):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');tmp.replace(path)
def main(a):
 a.out=a.out.resolve();a.plan=a.plan.resolve()
 if a.out.exists():raise ValueError('fresh output directory')
 a.out.mkdir(parents=True);snapshot=a.out/'source';snapshot.mkdir();files=list(Path(__file__).parent.glob('*.py'))+[ROOT/'tools/zipcaster_d3r/control.py',ROOT/'tools/zipcaster_d3r/weapon_aim.py',ROOT/'tools/zipcaster_d3r/aim_solver.py',ROOT/'tools/zipcaster_d3r/setup_navigation.py',a.plan];manifest={str(p.resolve()):sha(p)for p in files}
 for i,p in enumerate(files):shutil.copy2(p,snapshot/f'{i}-{p.name}')
 atomic(a.out/'source-manifest.json',manifest);points=json.loads(a.plan.read_text())['points'];byid={p['id']:p for p in points};results=[];done=set();aux=[];began=time.monotonic();stop_reason=None
 for batch in a.reuse:
  for r in json.loads(batch.read_text())['results']:
   path=ROOT/r['artifact'];run=json.loads(path.read_text());point=run['point'];new=byid.get(point['id']);same=new is not None and all(new[k]==point[k]for k in['graph','source','enemy','heading','speed','hooks','program']);key=(point['id'],run['repeat'])
   if not same:aux.append(dict(artifact=str(path.relative_to(ROOT)),sha256=sha(path),reason='different predeclared input; retained auxiliary'));continue
   assert run['freeze_before']==run['freeze_after'];item=dict(r,artifact_sha256=sha(path),eligible=bool(run['calibration_eligible']and run['passed']),reused=True,source_plan_sha256=run['plan_sha256']);results.append(item)
   if item['eligible']:assert key not in done;done.add(key)
 tasks=deque((p['id'],r,0)for r in range(a.repeats)for p in points if(p['id'],r)not in done)
 def progress(pending):atomic(a.out/'batch.json',dict(schema='inklab.d4.native.batch.v3',results=results,auxiliary=aux,rooms=a.rooms,planned=len(points)*a.repeats,valid=len(done),pending=len(tasks)+len(pending),stop_reason=stop_reason,seconds=time.monotonic()-began,source_sha256=manifest,plan_sha256=sha(a.plan)))
 def run(item):
  point,repeat,attempt=item;log=a.out/f'{point}-r{repeat}-attempt{attempt}.log'
  with log.open('w')as f:r=subprocess.run([sys.executable,str(Path(__file__).with_name('duel_v4.py')),'--plan',str(a.plan),'--point',point,'--repeat',str(repeat)],stdout=f,stderr=subprocess.STDOUT,cwd=ROOT)
  lines=[l for l in log.read_text().splitlines()if l.startswith('D4_DUEL_CLOSED ')];path=Path(lines[-1].split(' ',1)[1])/'result.json'if lines else None;data=json.loads(path.read_text())if path else{};eligible=bool(data.get('calibration_eligible')and data.get('passed'))
  return dict(point=point,repeat=repeat,attempt=attempt,exit_code=r.returncode,artifact=str(path.relative_to(ROOT))if path else None,artifact_sha256=sha(path)if path else None,eligible=eligible,outcome=data.get('outcome'),errors=data.get('errors'),reused=False)
 with ThreadPoolExecutor(max_workers=a.rooms)as pool:
  pending={};progress(pending)
  while tasks or pending:
   if(a.out/'STOP_LAUNCH').exists()and not stop_reason:stop_reason=(a.out/'STOP_LAUNCH').read_text().strip()or'operator stop'
   while tasks and len(pending)<a.rooms and not stop_reason:
    item=tasks.popleft();pending[pool.submit(run,item)]=item
   if not pending:break
   finished,_=wait(pending,return_when=FIRST_COMPLETED)
   for future in finished:
    item=pending.pop(future);result=future.result();results.append(result);print('D4_DUEL_CASE '+json.dumps(result),flush=True)
    if result['eligible']:done.add((item[0],item[1]))
    elif item[2]<1:tasks.appendleft((item[0],item[1],item[2]+1))
    else:stop_reason='Two setup attempts failed for '+item[0]+' repeat'+str(item[1]);(a.out/'STOP_LAUNCH').write_text(stop_reason+'\n')
   progress(pending)
 for p,h in manifest.items():assert sha(p)==h,p
 progress({});print('D4_BATCH_CLOSED '+json.dumps(dict(valid=len(done),planned=len(points)*a.repeats,stop_reason=stop_reason)),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--reuse',type=Path,nargs='*',default=[]);p.add_argument('--repeats',type=int,default=8);p.add_argument('--rooms',type=int,choices=[1,2,3],default=3);main(p.parse_args())
