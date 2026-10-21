"""Freeze ideal-operation native cohort before observing any combat outcomes.

Six singles/map,2 each model rank band;3 distinct seeded human target poses.
Trial0/1 training,trial2 held out. Threat control is separate, never selected
from calibration wins. Conditional target prior differs from global map prior.
"""
import argparse,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'tools/zipcaster_d3'),str(ROOT)]
from tools.zipcaster_d3r.analyze_direction import sha
from arena.lib.atlas import MapAtlas
from geometry import reachable

def main(a):
 if a.out.exists():raise ValueError('fresh cohort path')
 source=json.loads(a.plan.read_text());fine=[ROOT/f'work/d3r/ideal-fine-v2-stage{s}/result.json'for s in[1,2,3]];rows=[r for p in fine for r in json.loads(p.read_text())['results']if r['speed']==40 and r['style']=='full-light'];rng=np.random.default_rng(52032240);cases=[]
 for stage in[1,2,3]:
  atlas=MapAtlas.load(stage);pts=np.array(atlas.points);reach=set(reachable(atlas,[atlas.spawns['bravo']['ground']]).tolist());ranked=sorted([r for r in rows if r['stage']==stage],key=lambda r:-r['expected']);assert len(ranked)==6
  for rank,r in enumerate(ranked):
   point=next(p for p in source['points']if p['id']==r['id']);pool=sorted(n for n in reach if 5<=np.linalg.norm(pts[n]-point['attach'])<=20 and np.linalg.norm(pts[n]-point['source'])>=9)
   if len(pool)<3:raise ValueError('3 seeded independent near target nodes needed '+r['id']+' pool='+str(len(pool)))
   chosen=rng.choice(pool,3,replace=False)
   for trial,n in enumerate(chosen):
    heading=float(rng.integers(8)*math.pi/4);cases.append(point|dict(trial=trial,split='held-out'if trial==2 else'train',target=pts[n].tolist(),target_node=int(n),headings=[heading]*3,band=['high','middle','low'][rank//2],model_rank=rank+1,global_expected=r['expected'],global_worst=r['worst'],native_prior_pool_nodes=len(pool)))
 out=dict(schema='inklab.d3r.calibration.plan.v2',ranking_program='full-light',ranking_speed_frames=40,points=cases,seed=52032240,source_sha256={str(p.relative_to(ROOT)):sha(p)for p in[Path(__file__),a.plan,*fine]},native_prior='Uniform sample without replacement among all reachable atlas nodes5..20u from arrival, >=9u from source, reachable from bravo. Human only, uniform8 heading. Deliberately includes foes both inside/outside .52 range; separate close control must prove native gun threat. Global uniform all-map scores and conditional pose predictions reported separately.',held_out='trial2 per point, fixed before outcomes; no fitting on held-out',full_d3r_passed=False)
 a.out.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':'))+'\n');print('CASES '+str(len(cases)))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,default=ROOT/'work/d3r/ideal-plan-v1.json');p.add_argument('--out',type=Path,required=True);main(p.parse_args())
