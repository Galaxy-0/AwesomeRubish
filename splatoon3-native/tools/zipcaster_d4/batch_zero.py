"""Source-frozen <=3 owned rooms; one boundary case per room."""
import argparse,json,sys,subprocess,hashlib,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(a):
 if a.out.exists():raise ValueError('fresh batch output')
 a.out.mkdir(parents=True);sources=[Path(__file__),Path(__file__).with_name('zero_probe_v4.py'),ROOT/'tools/zipcaster_d3r/control.py',ROOT/'tools/zipcaster_d3r/weapon_aim.py'];manifest={str(p.resolve()):sha(p)for p in sources};(a.out/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');results=[];began=time.monotonic()
 def run(item):
  counter,repeat=item;log=a.out/f'counter-{counter}-r{repeat}.log'
  with log.open('w')as f:r=subprocess.run([sys.executable,str(Path(__file__).with_name('zero_probe_v4.py')),'--name',f'{a.out.name}-c{counter}-r{repeat}','--counter',str(counter)],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
  lines=[l for l in log.read_text().splitlines()if l.startswith('D4_ZERO_CLOSED ')];p=Path(lines[-1].split(' ',1)[1])/'result.json'if lines else None
  return dict(counter=counter,repeat=repeat,exit_code=r.returncode,artifact=str(p.relative_to(ROOT))if p else None)
 with ThreadPoolExecutor(max_workers=a.rooms)as pool:
  for future in as_completed([pool.submit(run,(c,r))for c in a.counters for r in range(a.repeats)]):
   results.append(future.result());(a.out/'batch.json').write_text(json.dumps(dict(results=results,rooms=a.rooms,seconds=time.monotonic()-began,source_sha256=manifest),indent=2)+'\n');print('D4_ZERO_CASE '+json.dumps(results[-1]),flush=True)
 for p,h in manifest.items():assert sha(p)==h,p
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--counters',type=int,nargs='+',default=[29,30,40]);p.add_argument('--repeats',type=int,default=1);p.add_argument('--rooms',type=int,choices=[1,2,3],default=3);main(p.parse_args())
