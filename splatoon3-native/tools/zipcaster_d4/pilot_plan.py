"""Freeze source-conditioned pilot points before their native outcomes."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import numpy as np
from tools.zipcaster_d3r.analyze_direction import sha
out=ROOT/'work/d4/pilot-plan-v1.json'
if out.exists():raise ValueError('fresh plan')
base=ROOT/'work/d4/query-v2-full-Yunohana-e772-h0-s40/result.json';fly=ROOT/'work/d4/query-v2-fly-Yunohana-e772-h0-s40/result.json';d=json.loads(base.read_text());f=json.loads(fly.read_text());z=np.load(ROOT/'work/d4/graph-v2-Yunohana/graph.npz');points=[]
for name,row in [('ground',d['top2'][0]),('fly',f['top2'][0])]:points.append(dict(id='Yunohana-pilot-'+name,graph='work/d4/graph-v2-Yunohana',source=row['position'],enemy=d['enemy'],heading=0,speed=40,program=row['program'],hooks=row['hooks'],model=row))
poor=min((r for r in d['rows'] if r['probability']==0 and r['status']=='dies-before-any-declared-route-can-move-or-kill'),key=lambda r:np.linalg.norm(np.array(r['position'])-d['enemy']));points.append(dict(id='Yunohana-pilot-control',graph='work/d4/graph-v2-Yunohana',source=poor['position'],enemy=d['enemy'],heading=0,speed=40,program='full-light',hooks=[],model=poor))
out.write_text(json.dumps(dict(schema='inklab.d4.native.plan.v1',points=points,query_sha256={str(p.relative_to(ROOT)):sha(p)for p in[base,fly]},scope='Three pilot checks, not formal repeated cohort. Selected before native outcomes; includes0-hook baseline and1+ hook conditional ranking.'),indent=2)+'\n');print(out)
