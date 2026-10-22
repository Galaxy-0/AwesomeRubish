"""Freeze common validation enemy states with ordinary spawn-route support.

Only validation-cohort feasibility, NOT a restriction of all-start model output.
A geometry atlas can contain enclosed lower surfaces, not usable native setups.
"""
import json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from arena.lib.atlas import MapAtlas
from tools.zipcaster_d3r.analyze_direction import sha
out=ROOT/'work/d4/common-enemy-states-v2.json'
if out.exists():raise ValueError('fresh states')
rows=[]
for stage in[1,2,3]:
 a=MapAtlas.load(stage);name=a.data['name'];z=np.load(ROOT/f'work/d4/graph-v2-{name}/graph.npz');todo=[a.nearest(a.spawns[t]['ground'])for t in['alpha','bravo']];seen=set(todo)
 for i in todo:
  for j in a.edges[i]:
   if j not in seen:seen.add(j);todo.append(j)
 ids=np.flatnonzero([int(i)in seen for i in z['ground_atlas_ids']])
 for region,heading in[('center',0),('central_high',2),('west_lane',1)]:
  p=np.array(a.region(region));i=int(ids[np.argmin(np.sum((z['ground'][ids]-p)**2*[1,4,1],axis=1))]);rows.append(dict(map=name,stage=stage,region=region,enemy_index=i,enemy=z['ground'][i].tolist(),heading=heading,graph=f'work/d4/graph-v2-{name}'))
out.write_text(json.dumps(dict(states=rows,source_sha256=sha(__file__),scope='Only native common-enemy cohort feasibility uses ordinary spawn reach. Full model ground bank remains unfiltered/overcomplete; enclosed/unsupported cells must not be advertised as proven native standing cells.'),indent=2)+'\n');print(out)
