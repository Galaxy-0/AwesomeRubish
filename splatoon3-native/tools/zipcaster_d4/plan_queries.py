"""Frozen common enemy states, independent of native outcomes."""
import json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from arena.lib.atlas import MapAtlas
from tools.zipcaster_d3r.analyze_direction import sha
out=ROOT/'work/d4/common-enemy-states-v1.json'
if out.exists():raise ValueError('fresh plan')
rows=[]
for stage in[1,2,3]:
 atlas=MapAtlas.load(stage);name=atlas.data['name'];directory=ROOT/f'work/d4/graph-v2-{name}';ground=np.load(directory/'graph.npz')['ground']
 for region,heading in [('center',0),('central_high',2),('west_lane',1)]:
  p=np.array(atlas.region(region));index=int(np.argmin(np.sum((ground-p)**2*[1,4,1],axis=1)));rows.append(dict(map=name,stage=stage,region=region,enemy_index=index,enemy=ground[index].tolist(),heading=heading,graph=str(directory.relative_to(ROOT))))
out.write_text(json.dumps(dict(states=rows,source_sha256=sha(__file__),scope='Three geometry-labelled common states/map, frozen before D4 duel outcomes. Field standing feasibility requires native setup; no score-driven enemy selection.'),indent=2)+'\n');print(out)
