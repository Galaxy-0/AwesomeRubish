"""Complete all-start restricted fallback queries for nine fixed enemy states.

No native processes, ranked start subset or timeout-to-zero conversion. Reuse
requires exact state and model dependency hashes; work originals never deleted.
"""
import argparse,json,time,subprocess,sys,shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from tools.zipcaster_d3r.analyze_direction import sha
from tools.zipcaster_d4.model_v3 import ROOT

def main(a):
 assert not a.out.exists();a.out.mkdir(parents=True);start=time.monotonic();states=json.loads(a.states.read_text())['states'];rows=[]
 files=[p for p in Path(__file__).parent.glob('*.py')if p.name not in ['compute_blade_common.py']]+[a.states]
 manifest={str(p.resolve()):sha(p)for p in files};(a.out/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 def run(state):
  dest=a.out/(state['map']+'-'+state['region']);reuse=None
  if state['map']=='Yunohana'and state['enemy_index']==637 and state['heading']==2:
   p=ROOT/'work/d4/restart-v4/high-blade-full-query-v1/result.json'
   if p.exists():
    d=json.loads(p.read_text())
    if d['search_complete']and all(sha(ROOT/k)==v for k,v in d['source_sha256'].items()):reuse=p
  if reuse:return dict(state=state,artifact=str(reuse),reused=True,seconds=0)
  cmd=[sys.executable,'-m','tools.zipcaster_d4.query_blade_only','--graph',state['graph'],'--enemy-index',str(state['enemy_index']),'--heading',str(state['heading']),'--speed','40','--out',str(dest)]
  then=time.monotonic()
  with(dest.with_suffix('.log')).open('w')as f:code=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=ROOT).returncode
  return dict(state=state,artifact=str(dest/'result.json')if(dest/'result.json').exists()else None,code=code,seconds=time.monotonic()-then,reused=False)
 with ThreadPoolExecutor(max_workers=a.workers)as pool:
  for f in as_completed([pool.submit(run,s)for s in states]):
   r=f.result();rows.append(r);(a.out/'batch.json').write_text(json.dumps(dict(results=rows,source_sha256=manifest,seconds=time.monotonic()-start,scope='Restricted whole-wave-clear/contact-disjoint; no native/full-D4 calibration'),indent=2)+'\n');print('D4_BLADE_COMMON '+json.dumps(r),flush=True)
 assert all(sha(Path(k))==v for k,v in manifest.items()),'source changed during batch'
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--states',type=Path,default=Path('work/d4/common-enemy-states-v2.json'));p.add_argument('--out',type=Path,required=True);p.add_argument('--workers',type=int,choices=[1,2,3,4],default=3);main(p.parse_args())
