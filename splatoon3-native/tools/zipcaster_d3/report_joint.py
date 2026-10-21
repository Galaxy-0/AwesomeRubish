"""Archive finite two-enemy simulations, retaining structural uncertainty."""
import json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import ROOT,sha
paths=[ROOT/f'work/d3/joint-v1-stage{i}/result.json'for i in [1,2,3]];inputs=[json.loads(p.read_text())for p in paths];rows=[r for d in inputs for r in d['records']];eps=2*math.sqrt(math.log(2*len(rows)*3/.05)/(2*inputs[0]['samples_per_behavior']))
for d in inputs:
 for path,h in d['source_sha256'].items():assert sha(ROOT/path)==h,path
for r in rows:
 assert 0<=r['worst_kills']<=r['expected_kills']<=2
 r['mc_uniform_family_interval']=[max(0,r['expected_kills']-eps),min(2,r['expected_kills']+eps)]
maps=[]
for name in ['Yunohana','District00','Yagara']:
 points=[r for r in rows if r['map']==name];best=max(points,key=lambda r:r['expected_kills']);worst=max(points,key=lambda r:r['worst_kills']);maps.append(dict(id=name,best_expected=best,best_maxmin=worst,records=points,highest_native_proven=False,mc_champion_separated=False))
out=dict(schema='inklab.d3.joint.report.v1',date='2026-10-21',full_d3_passed=False,native_joint_validated=False,maps=maps,scale=dict(tactics_programs=len(rows),programs=['full-light repeat110f','triple-light30f repeat110f'],defenders=2,mc_episodes=sum(len(d['records'])*3*d['samples_per_behavior']for d in inputs),simulated_frame_updates=sum(len(d['records'])*3*d['samples_per_behavior']*700 for d in inputs),stage_wall_seconds=[d['seconds']for d in inputs]),scope=inputs[0]['scope'],mc_family_delta=.05,mc_uniform_halfwidth=eps,limits=inputs[0]['limits']+['Ranks are estimates over54 finite path/program combinations; simultaneous MC intervals overlap, no highest-kill proof.','Action feasibility/reliability is the pre-calibration model; native cohort applies to single-defender full-light C only.','Expected kills can exceed1 per realization; global all-map expectation is diluted by distant enemies.'],source_sha256={str(p.relative_to(ROOT)):sha(p)for p in [Path(__file__),*paths]})
p=ROOT/'notes/d3-joint-20261021.json';p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out['scale'],indent=2));print('MC_HALF '+str(eps))
