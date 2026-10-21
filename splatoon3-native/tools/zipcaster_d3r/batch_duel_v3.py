"""Fixed-cohort <=3 independently owned rooms. No automatic combat retries.

Source/parameters/plan frozen for batch; setup voids retained. Replacement
attempts require a new output directory, never overwriting failures.
"""
import argparse,json,sys,os,time,subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha

def main(a):
 if a.out.exists():raise ValueError('fresh batch directory')
 a.out.mkdir(parents=True);plan=json.loads(a.plan.read_text());cases=[(p,t)for p in plan['points']for t in([p['trial']]if'trial'in p else range(a.trials))][a.offset:][:a.limit or None];results=[];began=time.monotonic()
 sources=[Path(__file__),Path(__file__).with_name('duel_v3.py'),Path(__file__).with_name('control.py'),Path(__file__).with_name('aim_solver.py'),Path(__file__).with_name('ray_model.py'),Path(__file__).with_name('weapon_aim.py'),a.plan,a.parameters,a.ray];manifest={str(p.resolve()):sha(p)for p in sources};(a.out/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 def execute(pair):
  p,t=pair;log=a.out/f'{p["id"]}-t{t}.log';cmd=[sys.executable,str(Path(__file__).with_name('duel_v3.py')),'--plan',str(a.plan.resolve()),'--parameters',str(a.parameters.resolve()),'--ray',str(a.ray.resolve()),'--point',p['id'],'--trial',str(t),'--speed',str(a.speed)]
  if a.passive:cmd+=['--passive']
  with log.open('w')as output:r=subprocess.run(cmd,stdout=output,stderr=subprocess.STDOUT,env={k:v for k,v in os.environ.items()if not k.startswith('DM_')})
  lines=[l for l in log.read_text().splitlines()if l.startswith('D3R_IDEAL_CLOSED ')];artifact=Path(lines[-1].split(' ',1)[1])/'result.json'if lines else None;d=json.loads(artifact.read_text())if artifact else{}
  return dict(point=p['id'],trial=t,map=p['map'],exit_code=r.returncode,artifact=str(artifact.relative_to(ROOT))if artifact else None,eligible=d.get('calibration_eligible',False),control_eligible=d.get('control_eligible',False),outcome=d.get('outcome'),errors=d.get('errors'),tactic_failure=d.get('tactic_failure'),band=p.get('band'))
 with ThreadPoolExecutor(max_workers=a.rooms)as pool:
  for future in as_completed([pool.submit(execute,c)for c in cases]):
   result=future.result();results.append(result);(a.out/'batch.json').write_text(json.dumps(dict(results=results,rooms=a.rooms,seconds=time.monotonic()-began,source_sha256=manifest),indent=2)+'\n');print('D3R_CASE '+json.dumps(result),flush=True)
 for p,h in manifest.items():assert sha(p)==h,p
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--parameters',type=Path,required=True);p.add_argument('--ray',type=Path,default=ROOT/'work/d3r/ray-v2-frozen.json');p.add_argument('--out',type=Path,required=True);p.add_argument('--rooms',type=int,choices=[1,2,3],default=3);p.add_argument('--trials',type=int,default=3);p.add_argument('--speed',type=int,default=40);p.add_argument('--offset',type=int,default=0);p.add_argument('--limit',type=int,default=0);p.add_argument('--passive',action='store_true');main(p.parse_args())
