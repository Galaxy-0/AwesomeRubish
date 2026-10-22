"""Freeze browser-vs-Python numeric parity cases from closed query originals."""
import json,gzip,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d4.model_v2 import World
from tools.zipcaster_d3r.analyze_direction import sha
out=ROOT/'work/d4/browser/parity-cases-v1.json'
if out.exists():raise ValueError('fresh cases')
rows=[];geometry=[];rng=np.random.default_rng(402210)
for name in['Yunohana','District00','Yagara']:
 w=World(ROOT/f'work/d4/graph-v2-{name}');low=w.field.tri.min(axis=(0,1));high=w.field.tri.max(axis=(0,1));starts=rng.uniform(low,high,(300,3));ends=starts+rng.uniform(-35,35,(300,3));v=w.vision.clear_pairs(starts,ends);directions=rng.normal(size=(300,3));radii=rng.choice([.3,.4,.5],300);idx,points,dist=w.field.sphere(starts,directions,radii,35.)
 geometry.append(dict(map=name,starts=starts.tolist(),ends=ends.tolist(),visible=v.tolist(),directions=directions.tolist(),radii=radii.tolist(),indices=idx.tolist(),points=points.tolist(),distance=dist.tolist()))
 for p in sorted((ROOT/'work/d4/common-full-v3').glob(name+'-*-s40.json.gz')):
  q=json.loads(gzip.decompress(p.read_bytes()))['result'];selected=[]
  for status in['predicted-kill','dies-before-any-declared-route-can-move-or-kill','unreachable-in-declared-graph','occupied']:
   pool=[r for r in q['rows']if r['status']==status]
   if pool:selected.append(pool[len(pool)//2])
  if q['top2']:selected.append(q['top2'][0])
  for r in selected:rows.append(dict(map=name,enemy=q['enemy_index'],heading=q['heading_quadrant'],speed=q['speed'],start=r['start'],expected={k:r.get(k)for k in['probability','status','remaining','exposure_frames','stealth','cost']}))
out.write_text(json.dumps(dict(schema='inklab.d4.browser.parity.v1',queries=rows,geometry=geometry,source_sha256=sha(__file__)),separators=(',',':'))+'\n');print('BROWSER_CASES',len(rows),'GEOMETRY',1800)
