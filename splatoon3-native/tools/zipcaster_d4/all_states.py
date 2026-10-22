"""Enumerate every declared3u floor layer and four headings, no ranked subset.

Atlas floor candidates include unsupported enclosed/isolated layers. Preserve
those in the compute bank, but carry ordinary-route support for UI disclosure;
never equate this support proxy with complete native standing certification.
"""
import argparse,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from arena.lib.atlas import MapAtlas
from tools.zipcaster_d3r.analyze_direction import sha

def main(a):
 if a.out.exists():raise ValueError('fresh all-state manifest')
 rows=[];maps=[]
 for stage in[1,2,3]:
  atlas=MapAtlas.load(stage);name=atlas.data['name'];graph=ROOT/f'work/d4/graph-v2-{name}';z=np.load(graph/'graph.npz');todo=[atlas.nearest(atlas.spawns[t]['ground'])for t in['alpha','bravo']];seen=set(todo)
  for i in todo:
   for j in atlas.edges[i]:
    if j not in seen:seen.add(j);todo.append(j)
  support=[int(i)in seen for i in z['ground_atlas_ids']];maps.append(dict(map=name,ground_count=len(support),ordinary_route_supported=sum(support),unsupported_layers=len(support)-sum(support),graph_sha256=sha(graph/'graph.npz')))
  for i,p in enumerate(z['ground']):rows.append(dict(map=name,stage=stage,enemy_index=i,enemy=p.tolist(),ordinary_route_supported=support[i],graph=str(graph.relative_to(ROOT))))
 out=dict(schema='inklab.d4.all.states.v1',states=rows,maps=maps,headings=[0,1,2,3],speeds=[20,40,60,129],queries=len(rows)*16,source_sha256=sha(__file__),scope='All declared3u atlas floor layers, not a strategy-ranked subset. Unsupported isolated/enclosed layers kept for transparency, not certified native valid standing cells. Ordinary-route support is only a geometry proxy; no pose writes/native teleport.');a.out.write_text(json.dumps(out,separators=(',',':'))+'\n');print(json.dumps(dict(queries=out['queries'],maps=maps),indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args())
