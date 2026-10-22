"""Run a frozen D4 plan; <=3 own rooms. Never silently resample losses."""
import argparse,json,subprocess,sys,time,hashlib,shutil
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(a):
 if a.out.exists():raise ValueError('fresh output path')
 a.out.mkdir(parents=True);snapshot=a.out/'source';snapshot.mkdir();files=list(Path(__file__).parent.glob('*.py'))+[ROOT/'tools/zipcaster_d3r/control.py',ROOT/'tools/zipcaster_d3r/weapon_aim.py',ROOT/'tools/zipcaster_d3r/aim_solver.py',ROOT/'tools/zipcaster_d3r/setup_navigation.py',a.plan];manifest={str(p.resolve()):sha(p)for p in files}
 for i,p in enumerate(files):shutil.copy2(p,snapshot/f'{i}-{p.name}')
 (a.out/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');plan=json.loads(a.plan.read_text());points=a.points or[p['id']for p in plan['points']];results=[];began=time.monotonic()
 def run(item):
  point,repeat=item;log=a.out/f'{point}-r{repeat}.log'
  with log.open('w')as f:r=subprocess.run([sys.executable,str(Path(__file__).with_name('duel_v3.py')),'--plan',str(a.plan),'--point',point,'--repeat',str(repeat)],stdout=f,stderr=subprocess.STDOUT,cwd=ROOT)
  lines=[l for l in log.read_text().splitlines()if l.startswith('D4_DUEL_CLOSED ')];artifact=Path(lines[-1].split(' ',1)[1])/'result.json'if lines else None
  return dict(point=point,repeat=repeat,exit_code=r.returncode,artifact=str(artifact.relative_to(ROOT))if artifact else None)
 with ThreadPoolExecutor(max_workers=a.rooms)as pool:
  for f in as_completed([pool.submit(run,(p,r))for p in points for r in range(a.repeats)]):
   results.append(f.result());(a.out/'batch.json').write_text(json.dumps(dict(results=results,rooms=a.rooms,seconds=time.monotonic()-began,source_sha256=manifest),indent=2)+'\n');print('D4_DUEL_CASE '+json.dumps(results[-1]),flush=True)
 for p,h in manifest.items():assert sha(p)==h,p
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--points',nargs='+');p.add_argument('--repeats',type=int,default=1);p.add_argument('--rooms',type=int,choices=[1,2,3],default=3);main(p.parse_args())
