"""Export numerical foundation evidence only, never grids/assets/generatedHTML."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha
zero=ROOT/'work/d4/zero-summary-v3.json';geometry=ROOT/'work/d4/geometry-check-v1.json';flight=ROOT/'work/d4/flight-model-v2-final.json';z=json.loads(zero.read_text());graphs=[]
for name in['Yunohana','District00','Yagara']:
 p=ROOT/f'work/d4/graph-v2-{name}/graph.json';d=json.loads(p.read_text());graphs.append({k:d[k]for k in['map','ground_nodes','candidate_wall_faces','wall_nodes','links','graph_sha256','scope']})
queries=[]
for p in sorted((ROOT/'work/d4').glob('common-query-v2-*/result.json')):
 d=json.loads(p.read_text());queries.append(dict(artifact=str(p.relative_to(ROOT)),sha256=sha(p),map=d['map'],enemy=d['enemy'],heading=d['heading_quadrant'],seconds=d['seconds'],top2_certified=d['top2_certified_in_declared_model'],top2=[{k:r[k]for k in['start','position','program','hooks','remaining','stealth']}for r in d['top2']]))
full=ROOT/'work/d4/query-v2-full-Yunohana-e772-h0-s40/result.json';d=json.loads(full.read_text());out=dict(schema='inklab.d4.foundation.v1',date='2026-10-22',full_d4_passed=False,status='foundation checkpoint; native pilot/cohort and page pending',zero_boundary=z,geometry_check=json.loads(geometry.read_text()),flight_metrics=json.loads(flight.read_text())['metrics'],graphs=graphs,common_queries=queries,complete_query={k:d[k]for k in['map','enemy','heading_quadrant','speed','search_complete','ground_nodes','wall_nodes','terminals','candidates','seconds']},tests=dict(component_cases=18,passed=True),source_sha256={str(p.relative_to(ROOT)):sha(p)for p in[Path(__file__),zero,geometry,flight,full]},scope=['No grid arrays/triangles/raw assets included. Per-case original logs retained underignoredwork.','0..3hooks; zero-hook ground baseline separated from fly-only. Four operation bands finite programs, not arbitrary input synthesis.','Deterministic ideal aim/fixed stationary FOV model, not a calibrated native probability. Native cohorts pending.','Exact emitted-at-zero present not witnessed; input30 no light birth vs31/32 birth beforezero andKOafterzero brackets observed behavior, not a universal native integer cutoff.'])
p=ROOT/'notes/d4-foundation-20261022.json'
if p.exists():raise ValueError('checkpoint exists')
p.write_text(json.dumps(out,indent=2)+'\n');print(p)
