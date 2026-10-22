"""Deterministic offline check of necessary terminal envelopes against real solver."""
import argparse,json,time,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d4.query_model import World
from tools.zipcaster_d4.model_v3 import PROGRAMS
from tools.zipcaster_d4.optimistic import terminal_bound,envelopes
from tools.zipcaster_d3r.analyze_direction import sha

def main(a):
 if a.out.exists():raise ValueError('fresh output required')
 rng=np.random.default_rng(a.seed);rows=[];began=time.monotonic()
 for name in ['Yunohana','District00','Yagara']:
  w=World(ROOT/('work/d4/graph-v2-'+name));bounds=envelopes(w.shots.parameters)
  for trial in range(a.poses):
   ground=bool(rng.integers(2));node=int(rng.integers(w.g if ground else w.h));position=w.graph['ground'if ground else'attach'][node];near=np.flatnonzero(np.linalg.norm(w.graph['ground']-position,axis=1)<25)
   if not len(near):continue
   enemy_id=int(rng.choice(near));enemy=w.graph['ground'][enemy_id];speed=int(rng.choice([20,40,60,129]))
   for program in PROGRAMS:
    bound=terminal_bound(w,node,enemy,speed,program,ground,bounds);actual=w.terminal(node,enemy,speed,program,ground)
    row=dict(map=name,trial=trial,node=node,ground=ground,enemy=enemy_id,speed=speed,program=program,bound=bound,actual_cost=actual['cost']if actual else None);rows.append(row)
    if actual is not None:assert bound is not None and bound<=actual['cost']+1e-9,row
 sources=[Path(__file__),*[Path(__file__).with_name(n)for n in ['optimistic.py','query_model.py','model_v3.py','attack_model_v5.py','attack_sequence_v2.py']]]
 result=dict(schema='inklab.d4.optimistic.check.v1',seed=a.seed,poses_per_map=a.poses,checked=len(rows),positive=sum(r['actual_cost']is not None for r in rows),seconds=time.monotonic()-began,rows=rows,source_sha256={str(p.relative_to(ROOT)):sha(p)for p in sources},scope='Offline sampled admissibility check, not a mathematical proof or native collision validation.')
 a.out.write_text(json.dumps(result,indent=2)+'\n');print({k:v for k,v in result.items()if k not in ['rows','source_sha256']})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--poses',type=int,default=30);p.add_argument('--seed',type=int,default=742);main(p.parse_args())
