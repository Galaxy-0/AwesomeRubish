"""Freeze a cost-ordered prefix's global and ordinary-supported top2.

Only when all processed starts are resolved and the next possible lower bound
is STRICTLY above both second scores. Heatmap completeness remains false.
The live partial is copied once; no output or running query is modified.
"""
import argparse,json,math
from pathlib import Path
import numpy as np
from tools.zipcaster_d4.model_v3 import ROOT,Config
from tools.zipcaster_d4.calibration_plan_v4 import reachable
from tools.zipcaster_d3r.analyze_direction import sha
from dataclasses import asdict

def main(a):
 assert not a.out.exists();batch=json.loads(a.bank.read_text());states=json.loads(a.states.read_text())['states'];manifest=batch['source_sha256'];assert all(sha(Path(k))==v for k,v in manifest.items())
 missing=[s for s in states if not any(r['state']==s for r in batch['results'])];assert len(missing)==1,missing;s=missing[0]
 directory=a.bank.parent/(s['map']+'-'+s['region']);assert(directory/'tested-query.py').read_bytes()==(ROOT/'tools/zipcaster_d4/query_blade_only.py').read_bytes()
 partial=directory/'partial.json';snapshot=partial.read_bytes();rows=json.loads(snapshot)['rows'];assert len(rows)>2 and all(r['complete']for r in rows)
 bounds=[r['cost_lower_bound']if r['cost_lower_bound']is not None else math.inf for r in rows];assert all(x<=y+1e-10 for x,y in zip(bounds,bounds[1:]));frontier=bounds[-1];assert math.isfinite(frontier)
 z=np.load(ROOT/s['graph']/'graph.npz');nav=reachable(s['stage']);allwins=sorted([r for r in rows if r.get('probability')==1],key=lambda r:(r['cost'],r['exposure_frames'],r['start']));supported=[r for r in allwins if int(z['ground_atlas_ids'][r['start']])in nav]
 assert len(supported)>=2 and frontier>max(allwins[1]['cost'],supported[1]['cost'])+1e-9
 a.out.mkdir();(a.out/'partial-snapshot.json').write_bytes(snapshot)
 proof=dict(schema='inklab.d4.prefix.top2.proof.v1',state=s,processed=len(rows),total=len(z['ground']),frontier_lower_bound=frontier,
  global_second_cost=allwins[1]['cost'],supported_second_cost=supported[1]['cost'],
  strict_bound_gap=frontier-supported[1]['cost'],source_manifest=manifest,partial_snapshot_sha256=sha(a.out/'partial-snapshot.json'),
  query_source_sha256=sha(directory/'tested-query.py'),scope='Query visits starts in nondecreasing cost lower bound. Every unvisited score is >= last processed lower bound. Strict gap rules out cost/exposure/ID ties. Full heatmap is not complete.')
 q=dict(schema='inklab.d4.blade-only.query.v1',map=s['map'],stage=s['stage'],enemy_index=s['enemy_index'],enemy=s['enemy'],heading_quadrant=s['heading'],speed=40,
  rows=rows,top2=allwins[:2],search_complete=False,top2_certified_in_declared_model=True,ordinary_supported_top2_certified=True,prefix_proof=proof,
  source_sha256={str(Path(k).relative_to(ROOT)):v for k,v in manifest.items()if Path(k).is_relative_to(ROOT)},config=asdict(Config()),ground_nodes=len(z['ground']),full_d4_passed=False)
 (a.out/'result.json').write_text(json.dumps(q,indent=2)+'\n');(a.out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
 planbank=dict(batch,results=batch['results']+[dict(state=s,artifact=str(a.out/'result.json'),reused_prefix_certificate=True)],heatmap_complete=False,scope='Top2 plan bank; one query prefix certificate, full computation continues independently.')
 (a.out/'bank-for-plan.json').write_text(json.dumps(planbank,indent=2)+'\n');print(json.dumps({k:proof[k]for k in ['processed','total','frontier_lower_bound','supported_second_cost','strict_bound_gap']}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--bank',type=Path,required=True);p.add_argument('--states',type=Path,default=Path('work/d4/common-enemy-states-v2.json'));p.add_argument('--out',type=Path,required=True);main(p.parse_args())
