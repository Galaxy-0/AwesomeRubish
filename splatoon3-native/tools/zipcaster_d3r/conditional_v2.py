"""Predict fixed native initial poses without reading combat outcome/history.

Closed eligible raw cases only. Initial state is matched; current source/target
positions after R, visibility history, damage and native result are NOT inputs.
"""
import argparse,json,sys,time
from pathlib import Path
from functools import lru_cache
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'tools/zipcaster_d3'),str(ROOT)]
from tools.zipcaster_d3r.motion_calibration import trajectory
from tools.zipcaster_d3r.ideal_duel import Config,duel_batch
from tools.zipcaster_d3r.blade_field import BladeField
from tools.zipcaster_d3r.analyze_direction import sha
from batch_geometry import BatchMesh
from geometry import CollisionMesh
from paired_rays import clear_pairs
@lru_cache(None)
def geometry(name):return BatchMesh(CollisionMesh.load(ROOT/f'work/arena/maps/{name}/sight.npz').triangles),BladeField(ROOT/f'work/arena/maps/{name}')

def predict(path,samples=256,profiles=None):
 d=json.loads(path.read_text());assert'freeze_after'in d and d['calibration_eligible'];p=d['point'];initial=next(e['infos']for e in d['events']if e['event']=='before-R');path_model,charge,budget=trajectory(p,d['speed_frames'],d['combo'],profiles or {});assert path_model is not None
 # Align only the source end of the old measured flight to the actual pre-R
 # source; terminal pose is still predicted, never taken from this duel.
 arrival=charge-(d['speed_frames']-21);shift=np.array(initial['player_0']['position'])-p['source'];path_model[:arrival+1]+=np.linspace(1.,0.,arrival+1)[:,None]*shift
 enemy=np.array([initial['player_1']['position']]);heading=np.array([initial['player_1']['heading']]);clear=np.zeros((len(path_model),1),bool);mesh,field=geometry(p['map']);cache={}
 for t,pos in enumerate(path_model):
  key=tuple(pos)
  if key not in cache:cache[key]=any(mesh.clear_many(pos+[0,h,0],enemy+[0,1.1,0])[0]for h in[.12,.7,1.3])
  clear[t]=cache[key]
 cfg=Config(reaction_min=18,reaction_max=18,style=d['combo']);r=duel_batch(path_model,charge,enemy,heading,np.array([False]),clear,cfg=cfg,samples=samples,seed=p['stage']*31+d['trial'],ballistic_clear=lambda x,y:clear_pairs(mesh,x,y),blade_clear=field.clear_pairs)
 return dict(point=p['id'],map=p['map'],trial=d['trial'],split=p['split'],source=str(path.relative_to(ROOT)),source_sha256=sha(path),probability=float(r['kills'].mean()),hit70=float(r['hit70'].mean()),hit35=float(r['hit35'].mean()),attacker_down=float((r['atk_ko']>=0).mean()),first_seen_mean=float(r['first_seen'][r['first_seen']>=0].mean())if(r['first_seen']>=0).any()else None,source_initial=initial['player_0']['position'],enemy_initial=initial['player_1']['position'],enemy_heading=float(heading[0]),samples=samples,scope='matched initial pose, R18/human/stand. Omega/aim priors and field/B approximations unchanged; no combat state/outcome replay.')

def main(a):
 if a.out.exists():raise ValueError('fresh prediction output')
 batch=json.loads(a.batch.read_text());rows=[];began=time.monotonic();profiles=json.loads(a.motion.read_text())['points']
 for row in batch['results']:
  if row['eligible']:
   rows.append(predict(ROOT/row['artifact'],a.samples,profiles));print('CONDITIONAL '+json.dumps({k:rows[-1][k]for k in['point','trial','probability','hit70','hit35']}),flush=True)
 sources=[Path(__file__),ROOT/'tools/zipcaster_d3r/ideal_duel.py',ROOT/'tools/zipcaster_d3r/ideal_search_v2.py',ROOT/'tools/zipcaster_d3r/motion_calibration.py',ROOT/'tools/zipcaster_d3r/blade_field.py',ROOT/'tools/zipcaster_d3r/native_kinematics.py'];a.out.write_text(json.dumps(dict(schema='inklab.d3r.conditional.v2',motion_fit_sha256=sha(a.motion),predictions=rows,seconds=time.monotonic()-began,source_sha256={str(p.relative_to(ROOT)):sha(p)for p in sources}),indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,default=ROOT/'work/d3r/calibration-v2/batch.json');p.add_argument('--motion',type=Path,required=True);p.add_argument('--samples',type=int,default=256);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
