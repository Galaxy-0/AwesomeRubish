"""Resumable enemy-state queries, compressed original numeric results.

No game processes. Timeout/candidate cap is reported unknown, never P=0.
Each query has its own immutable gzip original; progress manifest is resumable.
"""
import argparse,contextlib,gzip,io,json,os,signal,sys,time
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha
CACHE={}
class Deadline(Exception):pass
class MemoryFile:
 def __init__(self,bank,name):self.bank=bank;self.name=name
 def write_text(self,text):self.bank[self.name]=text
class MemoryDirectory:
 def __init__(self):self.bank={}
 def exists(self):return False
 def mkdir(self,**kw):pass
 def __truediv__(self,name):return MemoryFile(self.bank,name)
def work(task):
 import tools.zipcaster_d4.query_v4 as q
 from tools.zipcaster_d4.model_v2 import World
 mapname,enemy,heading,speed,outpath,seconds=task;start=time.monotonic();graph=ROOT/f'work/d4/graph-v2-{mapname}';memory=MemoryDirectory();log=io.StringIO();key=f'{mapname}-e{enemy}-h{heading}-s{speed}';status='error';result=None
 def alarm(*args):raise Deadline()
 signal.signal(signal.SIGALRM,alarm);signal.alarm(seconds)
 try:
  if mapname not in CACHE:CACHE[mapname]=World(graph)
  q.World=lambda directory:CACHE[mapname]
  a=argparse.Namespace(graph=graph,enemy_index=enemy,heading=heading,speed=speed,programs=['full-light','light3','light-full','full2'],out=memory,top_only=False,prune_terminal=True,min_hooks=0,max_candidates=0)
  with contextlib.redirect_stdout(log):q.query(a)
  result=json.loads(memory.bank['result.json']);status='complete'if result['search_complete']else'unresolved'
 except Deadline:status='timeout';result=json.loads(memory.bank['partial.json'])if'partial.json'in memory.bank else dict(rows=[])
 except BaseException as e:result=dict(error=repr(e),rows=[])
 finally:signal.alarm(0)
 payload=dict(schema='inklab.d4.enumeration.item.v1',key=key,map=mapname,enemy_index=enemy,heading=heading,speed=speed,status=status,seconds=time.monotonic()-start,result=result,log=log.getvalue());p=Path(outpath)/f'{key}.json.gz'
 # Never replace an earlier closed raw result.
 with p.open('xb')as raw:
  with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0)as f:f.write(json.dumps(payload,separators=(',',':')).encode())
 return dict(key=key,status=status,seconds=payload['seconds'],bytes=p.stat().st_size,sha256=sha(p),path=str(p.relative_to(ROOT)))
def main(a):
 a.out=a.out.resolve();a.states=a.states.resolve();a.out.mkdir(parents=True,exist_ok=True);inputs=[Path(__file__),Path(__file__).with_name('query_v4.py'),Path(__file__).with_name('model_v2.py'),Path(__file__).with_name('reverse_v2.py'),Path(__file__).with_name('flight_v2.py'),a.states];manifest={str(p.resolve()):sha(p)for p in inputs};m=a.out/'source-manifest.json'
 if m.exists():assert json.loads(m.read_text())==manifest,'resume requires identical source/input'
 else:m.write_text(json.dumps(manifest,indent=2)+'\n')
 states=json.loads(a.states.read_text())['states'];tasks=[];finished=[];prior={}
 if a.prior:
  previous=json.loads((a.prior/'progress.json').read_text())
  for r in previous['results']:
   if r['status']=='complete':
    path=ROOT/r['path'];assert sha(path)==r['sha256'];prior[r['key']]=r
 for row in states:
  for heading in a.headings:
   for speed in a.speeds:
    key=f"{row['map']}-e{row['enemy_index']}-h{heading}-s{speed}";p=a.out/f'{key}.json.gz'
    if key in prior:finished.append(dict(prior[key],status='prior-complete'));continue
    if p.exists():finished.append(dict(key=key,status='existing',sha256=sha(p)));continue
    tasks.append((row['map'],row['enemy_index'],heading,speed,str(a.out),a.seconds))
 for name in['OPENBLAS_NUM_THREADS','VECLIB_MAXIMUM_THREADS','OMP_NUM_THREADS']:os.environ[name]='1'
 with ProcessPoolExecutor(max_workers=a.workers)as pool:
  for future in as_completed([pool.submit(work,t)for t in tasks]):
   r=future.result();finished.append(r);(a.out/'progress.json').write_text(json.dumps(dict(results=finished,total=len(states)*len(a.headings)*len(a.speeds)),indent=2)+'\n');print('D4_ENUM '+json.dumps(r),flush=True)
 for p,h in manifest.items():assert sha(p)==h,p
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--states',type=Path,required=True);p.add_argument('--prior',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--workers',type=int,choices=range(1,9),default=4);p.add_argument('--headings',type=int,nargs='+',default=[0,1,2,3]);p.add_argument('--speeds',type=int,nargs='+',default=[20,40,60,129]);p.add_argument('--seconds',type=int,default=60);main(p.parse_args())
