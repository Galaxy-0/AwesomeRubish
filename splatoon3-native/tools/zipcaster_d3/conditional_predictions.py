"""Matched initial-pose predictions over completed immutable native cases."""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import ROOT,sha
from calibrated_model import Config,hook_path,duel_batch
from model_v2 import Config as PriorConfig,duel_batch as prior_duel,hook_path as prior_path
from geometry import CollisionMesh
from batch_geometry import BatchMesh

def predict(path,*,parameters=None,samples=512):
 d=json.loads(path.read_text());p=d['point'];point=p['point_model'];initial=next(e['infos']for e in d['events']if e['event']=='before-R');cfg=(Config(**parameters,reaction_min=18,reaction_max=18)if parameters is not None else PriorConfig(reaction_min=18,reaction_max=18))
 source=initial['player_0']['position'];enemy=np.asarray([initial['player_1']['position']]);heading=np.asarray([initial['player_1']['heading']]);forms=np.asarray([False]);trajectory,events=(hook_path if parameters is not None else prior_path)(source,[point['anchor']],[point['attach']],cfg,ground_landings=[point['landing']]);arrival=next(e['frame']for e in events if e['event']=='开始蓄力')
 mesh=BatchMesh(CollisionMesh.load(ROOT/f'work/arena/maps/{p["map"]}/sight.npz').triangles);clear=np.zeros((len(trajectory),1),bool)
 for t,pos in enumerate(trajectory):clear[t]=any(mesh.clear_many(pos+[0,h,0],enemy+[0,1.1,0])[0]for h in [.12,.7,1.3])
 r=(duel_batch if parameters is not None else prior_duel)(trajectory,arrival,enemy,heading,forms,clear,cfg=cfg,samples=samples,behavior='stand',seed=p['stage']*100+p['trial'],ballistic_clear=mesh.clear_pairs)
 good=(r['atk_ko']<0)|(r['atk_ko']>=arrival)
 return dict(prediction_sources={str(q.relative_to(ROOT)):sha(q)for q in [Path(__file__),Path(__file__).with_name('model.py'),Path(__file__).with_name('model_v2.py'),Path(__file__).with_name('calibrated_model.py')]},hit70_given_charge=float(r['hit70'][good].mean())if good.any()else 0.,hit35_given_charge=float(r['hit35'][good].mean())if good.any()else 0.,kill=float(r['kills'].mean()),hit70=float(r['hit70'].mean()),hit35=float(r['hit35'].mean()),attacker_down=float((r['atk_ko']>=0).mean()),first_seen_mean=float(r['first_seen'][r['first_seen']>=0].mean())if(r['first_seen']>=0).any()else None,samples=samples,parameters=parameters or {},source_sha256=sha(path),source=str(path.relative_to(ROOT)))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--batch',type=Path,default=ROOT/'work/d3/calibration-v2/final/batch.json');ap.add_argument('--out',type=Path,required=True);ap.add_argument('--parameters',type=Path);a=ap.parse_args();parameters=json.loads(a.parameters.read_text())if a.parameters else None
 rows=[]
 for r in json.loads(a.batch.read_text())['results']:
  if r['eligible']:rows.append(predict(ROOT/r['artifact'],parameters=parameters));print('PRED '+r['point']+' '+str(r['trial'])+' '+str(rows[-1]['kill']),flush=True)
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(dict(predictions=rows,model_sha256=sha(Path(__file__).with_name('calibrated_model.py')),predictor_sha256=sha(__file__)),indent=2)+'\n')
