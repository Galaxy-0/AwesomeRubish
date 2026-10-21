"""Finite joint two-.52 search over budgeted hook paths and repeated programs."""
import argparse,json,time,sys,math
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import ROOT,sha
from model_v2 import Config,hook_path
from geometry import CollisionMesh
from batch_geometry import BatchMesh
from search_v2 import graph_motion,write
from arena.lib.atlas import MapAtlas
from joint_duel import simulate

def main(a):
    if a.out.exists():raise ValueError('fresh directory required')
    a.out.mkdir(parents=True);cfg=Config();source=ROOT/'work/d3/coarse-v2.json';coarse=json.loads(source.read_text());detailpaths=[ROOT/'work/d3/fine-v2-stage1/result.json',ROOT/'work/d3/fine-v2-stage2/result.json',ROOT/'work/d3/fine-v2-resumed-stage3/result.json'];maps=[m for p in detailpaths for m in json.loads(p.read_text())['maps']];records=[];started=time.monotonic();sources=[Path(__file__),Path(__file__).with_name('joint_duel.py'),Path(__file__).with_name('model_v2.py'),Path(__file__).with_name('model.py'),Path(__file__).with_name('budget.py'),Path(__file__).with_name('search_v2.py'),Path(__file__).with_name('batch_geometry.py'),source,*detailpaths];manifest={str(p.relative_to(ROOT)):sha(p)for p in sources};write(a.out/'source-manifest.json',manifest)
    for m in maps:
        if a.stage and m['stage']!=a.stage:continue
        atlas=MapAtlas.load(m['stage']);allpts=np.asarray(atlas.points);mesh=BatchMesh(CollisionMesh.load(ROOT/f'work/arena/maps/{m["id"]}/sight.npz').triangles);rng=np.random.default_rng(520321900+m['stage']);reachable=next(x['reachable_ids']for x in coarse['maps']if x['stage']==m['stage']);ids=rng.choice(reachable,(a.samples,2));heading=rng.integers(8,size=(a.samples,2))*math.pi/4;forms=rng.integers(2,size=(a.samples,2)).astype(bool)&np.asarray(atlas.swimmable)[ids]
        for p in m['points']:
            path,events=hook_path(p['source'],p.get('sequence_anchors',[p['anchor']]),p.get('sequence_attach',[p['attach']]),cfg,ground_landings=p.get('sequence_landings',[p['landing']]))
            modes={};tic=time.monotonic()
            for b,mode in enumerate(['stand','strafe','retreat']):
                horizon=700;motion=graph_motion(atlas,ids.ravel(),heading.ravel(),mode,horizon,cfg,mesh=mesh,threat=p['source']).reshape(horizon,a.samples,2,3);human=np.empty((horizon,a.samples,2),bool);squid=np.empty_like(human);cache={}
                for t in range(horizon):
                    at=path[min(t,len(path)-1)];en=motion[t].reshape(-1,3);key=(tuple(at),en.tobytes())
                    if key not in cache:
                        result=[]
                        for eyeheight in [1.1,.25]:
                            seen=np.zeros(len(en),bool)
                            for h in [.12,.7,1.3]:
                                remaining=np.flatnonzero(~seen)
                                if len(remaining):seen[remaining]=mesh.clear_many(at+[0,h,0],en[remaining]+[0,eyeheight,0])
                            result.append(seen.reshape(a.samples,2))
                        cache[key]=result
                    human[t],squid[t]=cache[key]
                modes[mode]=(motion,human,squid)
            for style in ['full-light','triple-light']:
                behavior=[]
                for b,(mode,(motion,human,squid))in enumerate(modes.items()):
                    r=simulate(path,events,motion,heading,forms,human,squid,mesh.clear_pairs,style=style,seed=52032100+b,cfg=cfg)
                    iv=simulate(path,events,motion,heading,forms,human,squid,mesh.clear_pairs,style=style,seed=52032100+b,cfg=cfg,return_vulnerable=False)
                    behavior.append(dict(behavior=mode,n=a.samples,mean_kills=float(r['kills'].mean()),p_any=float((r['kills']>0).mean()),p_two=float((r['kills']==2).mean()),std_error=float(r['kills'].std(ddof=1)/math.sqrt(a.samples)),survive_return_bracket=[float(r['attacker_alive'].mean()),float(iv['attacker_alive'].mean())],mean_budget_spent=float(r['spent'].mean()),full_emissions=r['full_emissions'],light_emissions=r['light_emissions']))
                row=dict(map=m['id'],id=p['id'],start_region=p['start_region'],source=p['source'],sequence=p.get('sequence',[p['id']]),anchors=p.get('sequence_anchors',[p['anchor']]),style=style,expected_kills=float(np.mean([r['mean_kills']for r in behavior])),worst_kills=min(r['mean_kills']for r in behavior),behavior=behavior,seconds=time.monotonic()-tic,native_joint_validated=False)
                records.append(row);write(a.out/'partial.json',dict(records=records,source_sha256=manifest));print('JOINT '+json.dumps({k:row[k]for k in ['map','id','style','expected_kills','worst_kills','seconds']}),flush=True)
    for p,h in manifest.items():assert sha(ROOT/p)==h,p
    result=dict(schema='inklab.d3.joint.v1',records=records,samples_per_behavior=a.samples,seconds=time.monotonic()-started,source_sha256=manifest,scope='Two independent uniformly sampled all-map initial .52 defenders,8 headings,valid forms; shared attackerHP/gauge, persistent enemyHP, joint crossfire. Finite hook candidates and two repeated110f programs; native two-enemy calibration absent.',limits=['No continuous/global optimum claim or 4v4 player guarantee.','Single-defender model/ideal targeting assumptions carry over.','Return hit rule unknown; survival bracket uses vulnerable clear-LOS upper risk vs100f invulnerable bound.','No armor benefit/contact blast; static terminal floor and turn template.','Full-light repeat and target switching unverified jointly; triple-light30f individual input rhythm from A6.','MC uncertainty plus much larger structural/native model error.'])
    write(a.out/'result.json',result)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--samples',type=int,default=256);p.add_argument('--stage',type=int,choices=[1,2,3]);main(p.parse_args())
