"""Own native flight identification, independent of combat outcome/target HP."""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.fit_mapping import collect
from tools.zipcaster_d3r.ideal_search_v2 import flight
from tools.zipcaster_d3r.analyze_direction import sha

def features(delta):
 d=np.asarray(delta);return np.stack([np.ones(d.shape[:-1]),np.linalg.norm(d,axis=-1),np.maximum(0,d[...,1]),np.maximum(0,-d[...,1])],axis=-1)
def frames(delta,model):return np.maximum(18,np.ceil(features(delta)@model['coefficients'])).astype(int)
def path(source,attach,model):
 source=np.array(source,float);attach=np.array(attach,float);n=int(frames(attach-source,model));p=np.interp(np.linspace(0,1,n+1),np.linspace(0,1,len(model['progress'])),model['progress']);return source+p[:,None]*(attach-source)
def fit(a):
 if a.out.exists():raise ValueError('fresh parameter output')
 raw,_,opened=collect();assert not opened;rows=[];began=time.monotonic()
 for r in raw:
  if not r['native_bind']or r['arrival']is None or r['normal']is None or abs(r['normal'][1])>=.5:continue
  p=flight(r)
  if p is None or len(p)<3:continue
  delta=p[-1]-p[0];length2=np.dot(delta,delta)
  if length2<.01:continue
  progress=np.clip((p-p[0])@delta/length2,0,1);curve=np.interp(np.linspace(0,1,65),np.linspace(0,1,len(p)),progress);rows.append(dict(key=[r['map'],r['batch'],r['index']],train=r['batch']<3 and r['split']=='train',delta=delta,frames=len(p)-1,curve=curve,path=p))
 train=[r for r in rows if r['train']];assert len(train)>=12;x=features(np.array([r['delta']for r in train]));y=np.array([r['frames']for r in train]);coef=np.linalg.lstsq(x,y,rcond=None)[0];progress=np.maximum.accumulate(np.median(np.array([r['curve']for r in train]),axis=0));progress[0]=0;progress[-1]=1;model=dict(coefficients=coef.tolist(),progress=progress.tolist());metrics={}
 for label,rr in [('train',train),('final-batches3-4',[r for r in rows if r['key'][1]>=3]),('all',rows)]:
  actual=np.array([r['frames']for r in rr]);prediction=frames(np.array([r['delta']for r in rr]),model);errors=[]
  for r in rr:
   estimate=path(r['path'][0],r['path'][-1],model);n=min(len(estimate),len(r['path']));errors.extend(np.linalg.norm(estimate[:n]-r['path'][:n],axis=1).tolist())
  metrics[label]=dict(n=len(rr),duration_rmse=float(np.sqrt(np.mean((prediction-actual)**2))),duration_max_error=int(np.abs(prediction-actual).max()),position_rmse=float(np.sqrt(np.mean(np.array(errors)**2))))
 out=dict(schema='inklab.d4.flight.v1',**model,metrics=metrics,training_keys=[r['key']for r in train],seconds=time.monotonic()-began,source_sha256=sha(__file__),scope='Free own flights from existing mapping, batches0..2 train rows only. Final3/4 time/path checks; native start/end poses used for identification only. D4 graph supplies predicted anchors/attach, not future native poses. Linear centerline projection, not complete native collision/animation physics.');a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(metrics,indent=2))
def retime(a):
 if a.out.exists():raise ValueError('fresh retimed graph directory')
 a.out.mkdir(parents=True);base=json.loads((a.graph/'graph.json').read_text());assert sha(a.graph/'graph.npz')==base['graph_sha256'];model=json.loads(a.model.read_text());z=dict(np.load(a.graph/'graph.npz'));sources=np.concatenate([z['ground'],z['attach']+[0,float(np.interp(6,[0,4,8],[0,.4535,1.2975])),0]]);delta=z['attach'][z['edge_destination']]-sources[z['edge_source']];z['edge_frames']=frames(delta,model).astype(np.uint16);np.savez_compressed(a.out/'graph.npz',**z);base.update(schema='inklab.d4.graph.v2',parent_graph_sha256=base['graph_sha256'],graph_sha256=sha(a.out/'graph.npz'),flight_model_sha256=sha(a.model),flight_model=model,retime_source_sha256=sha(__file__));base['scope']=[s for s in base['scope']if not s.startswith('Flight frame rule')]+['Native own-flight train-only duration/progress model; B6/terminal fall still separate extrapolation.'];(a.out/'graph.json').write_text(json.dumps(base,indent=2)+'\n');print('D4_RETIMED '+str(a.out),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['fit','retime']);p.add_argument('--out',type=Path,required=True);p.add_argument('--graph',type=Path);p.add_argument('--model',type=Path);a=p.parse_args();(fit if a.mode=='fit'else retime)(a)
