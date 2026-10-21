"""Deterministic native validation cohort. Workers own independent processes."""
import argparse,json,math,os,sys,subprocess,hashlib,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import ROOT,sha
from geometry import reachable
from arena.lib.atlas import MapAtlas

def select(a):
    inputs=[ROOT/'work/d3/fine-v2-stage1/result.json',ROOT/'work/d3/fine-v2-stage2/result.json',ROOT/'work/d3/fine-v2-resumed-stage3/result.json']
    maps=[m for p in inputs for m in json.loads(p.read_text())['maps']];rng=np.random.default_rng(52032107);permap=[]
    for m in maps:
        atlas=MapAtlas.load(m['stage']);pts=np.asarray(atlas.points);reach=set(reachable(atlas,[atlas.spawns['bravo']['ground']]).tolist());singles=sorted([p for p in m['points']if len(p.get('sequence',[p['id']]))==1],key=lambda p:-p['expected_kill_probability']);cases=[]
        for rank,p in enumerate(singles):
            pool=[e['node']for e in p['enemy_results']if e['node']in reach and np.linalg.norm(pts[e['node']]-p['source'])>=10]
            if len(pool)<3:raise ValueError('insufficient static reachable target pool '+p['id'])
            chosen=rng.choice(pool,3,replace=False)
            for trial,node in enumerate(chosen):
                cases.append(dict(id=p['id'],map=p['map'],stage=p['stage'],trial=trial,band=['high','middle','low'][rank//2],model_single_rank=rank+1,model_global_expected=p['expected_kill_probability'],model_local_expected=p['local_expected'],source=p['source'],requested_anchor=p['anchor'],estimated_landing=p['landing'],target=pts[node].tolist(),target_node=int(node),heading=float(rng.integers(8)*math.pi/4),human_only=True,native_prior_pool_nodes=len(pool),original_near_nodes=p['enemy_nodes_sampled'],point_model=p))
        # Each map supplies two hooks per band x three human initial poses.
        permap.append(cases)
    ordered=[permap[stage][i]for i in range(18)for stage in range(3)]
    data=dict(schema='inklab.d3.calibration.selection.v2',points=ordered,seed=52032107,native_target_prior='Uniform fine <=30u enemy nodes, conditioned on static reachability from bravo spawn and >=10u from source; human only; uniform8 headings. Three deterministic draws per hook. This differs from all-map/global model prior; matched conditional predictions required.',source_sha256={str(p.relative_to(ROOT)):sha(p)for p in [Path(__file__),*inputs]})
    a.selection.parent.mkdir(parents=True,exist_ok=True)
    if a.selection.exists():raise ValueError('do not overwrite existing selection')
    a.selection.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n');print('CASES '+str(len(ordered)))

def batch(a):
    a.out=a.out.resolve()
    if a.out.exists():raise ValueError('fresh batch output required')
    a.out.mkdir(parents=True);cases=json.loads(a.selection.read_text())['points'][a.offset:][:a.limit or None];driver=Path(__file__).with_name('validate_hint.py');began=time.monotonic();results=[]
    freeze={str(p.relative_to(ROOT)):sha(p)for p in [Path(__file__),driver,driver.with_name('native.py'),driver.with_name('validate.py'),ROOT/'tools/zipcaster/serve.py',a.selection.resolve()]}
    (a.out/'source-manifest.json').write_text(json.dumps(freeze,indent=2)+'\n')
    def execute(p):
        name=p['id']+'-t'+str(p['trial']);log=a.out/(name+'.log')
        cmd=[sys.executable,str(driver),'--selection',str(a.selection.resolve()),'--point',p['id'],'--trial',str(p['trial']),'--cohort',a.cohort,'--attempt',str(a.attempt)]
        with log.open('w')as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env={k:v for k,v in os.environ.items()if not k.startswith('DM_')})
        lines=[l for l in log.read_text().splitlines()if l.startswith('HINT_DUEL_CLOSED ')]
        result=Path(lines[-1].split(' ',1)[1])/'result.json'if lines else None;d=json.loads(result.read_text())if result else{}
        return dict(point=p['id'],map=p['map'],trial=p['trial'],exit_code=r.returncode,artifact=str(result.relative_to(ROOT))if result else None,eligible=d.get('calibration_eligible',False),outcome=d.get('outcome'),tactic_failure=d.get('tactic_failure'),errors=d.get('errors'),log=str(log.relative_to(ROOT)))
    with ThreadPoolExecutor(max_workers=a.rooms)as pool:
        for future in as_completed([pool.submit(execute,p)for p in cases]):
            r=future.result();results.append(r);(a.out/'batch.json').write_text(json.dumps(dict(results=results,rooms=a.rooms,seconds=time.monotonic()-began,source_sha256=freeze),indent=2)+'\n');print('CAL_CASE '+json.dumps(r),flush=True)
    for p,h in freeze.items():assert sha(ROOT/p)==h,p
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['select','batch']);p.add_argument('--selection',type=Path,default=ROOT/'work/d3/calibration-v2/selection.json');p.add_argument('--out',type=Path);p.add_argument('--cohort',default='v2');p.add_argument('--rooms',type=int,choices=[1,2,3],default=3);p.add_argument('--attempt',type=int,choices=[1,2],default=1);p.add_argument('--offset',type=int,default=0);p.add_argument('--limit',type=int,default=0);a=p.parse_args();select(a)if a.mode=='select'else batch(a)
