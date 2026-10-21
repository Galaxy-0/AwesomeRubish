"""D3 native rank/conditional calibration report, with held-out trial2."""
import argparse,json,math,sys
from pathlib import Path
from collections import defaultdict
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import ROOT,sha
from native_calibration_data import case
from calibration_stats import spearman,kendall,beta_interval,fit_reliability,metrics
from conditional_predictions import predict

def main(a):
 batches=[json.loads(p.read_text())for p in a.batches];bycase={};invalid=[]
 for batch in batches:
  for r in batch['results']:
   if not r['eligible']:invalid.append(r);continue
   d=case(ROOT/r['artifact']);key=(d['map'],d['id'],d['trial']);bycase[key]=d
 cases=list(bycase.values());cache=a.out/'cache';cache.mkdir(parents=True,exist_ok=True)
 def prediction(c,parameters=None,tag='prior'):
  p=cache/(c['id']+'-'+str(c['trial'])+'-'+tag+'.json')
  if p.exists():
   d=json.loads(p.read_text());assert all(sha(ROOT/x)==h for x,h in d['prediction_sources'].items());assert d['source_sha256']==sha(ROOT/c['artifact'])and d['parameters']==(parameters or {});return d
  d=predict(ROOT/c['artifact'],parameters=parameters);p.write_text(json.dumps(d,indent=2)+'\n');return d
 for c in cases:c['pred_prior']=prediction(c)
 train=[c for c in cases if c['trial']!=2];held=[c for c in cases if c['trial']==2];ready=[c for c in train if c['prepared_healthy']]
 setup=[c['arrival_setup_frames']for c in ready if c['arrival_setup_frames']is not None]
 yaw=[e for c in train for e in c['fired_yaw_errors']];pitch=[e for c in train for e in c['fired_pitch_errors']]
 parameters=dict(arrival_setup=int(round(float(np.median(setup))))if setup else 117,full_reliability=fit_reliability([c['pred_prior']['hit70_given_charge']for c in ready],[c['full_window70']for c in ready]),light_reliability=fit_reliability([c['pred_prior']['hit35_given_charge']for c in ready],[c['light_window35_or_clampedKO']for c in ready]),aim_sigma_degrees=math.degrees(float(np.sqrt(np.mean(np.square(yaw)))))if yaw else 2.,defender_pitch_sigma_degrees=math.degrees(float(np.sqrt(np.mean(np.square(pitch)))))if pitch else 0.)
 groups=defaultdict(list)
 for c in cases:groups[c['map'],c['id']].append(c)
 feasibility={}
 for k,rs in groups.items():
  training=[c for c in rs if c['trial']!=2];bind=[c for c in training if c['hook_exposed']];control=[c for c in training if c['control_exposed']]
  feasibility[k]=dict(bind=(1+sum(c['bind_success']for c in bind))/(2+len(bind))if bind else 1.,control=(1+sum(c['control_complete']for c in control))/(2+len(control))if control else 1.,train_bind_n=len(bind),train_control_n=len(control))
 for c in cases:
  f=feasibility[c['map'],c['id']];c['pred_feasibility']=c['pred_prior']['kill']*f['bind']*f['control'];c['pred_hit_model']=prediction(c,parameters,'post');c['pred_corrected']=c['pred_hit_model']['kill']*f['bind']*f['control']
 points=[]
 for (m,p),rs in groups.items():
  n=len(rs);kills=sum(c['kill']for c in rs);bind=sum(c['bind_success']for c in rs)
  points.append(dict(map=m,id=p,band=rs[0]['band'],n=n,kills=kills,rate=kills/n,rate_beta95=beta_interval(kills,n),bind_success=bind,bind_beta95=beta_interval(bind,n),aim_timeouts=sum(c['tactic_failure']=='C aim budget180 exhausted'for c in rs),model_global_expected=rs[0]['model_global_expected'],matched_prior_prediction=float(np.mean([c['pred_prior']['kill']for c in rs])),matched_post_prediction=float(np.mean([c['pred_corrected']for c in rs])),feasibility_training=feasibility[m,p]))
 def ranks_for(ps,key):return dict(spearman=spearman([p[key]for p in ps],[p['rate']for p in ps]),kendall_tau_b=kendall([p[key]for p in ps],[p['rate']for p in ps]))
 match=ranks_for(points,'matched_post_prediction');stages={}
 held_points=[dict(rate=float(c['kill']),matched_prior_prediction=c['pred_prior']['kill'],matched_post_prediction=c['pred_corrected'],model_global_expected=c['model_global_expected'])for c in held]
 for label,rs in [('train',train),('held_out_trial2',held),('all',cases)]:
  stages[label]={k:metrics([c[k]if k!='pred_prior'else c['pred_prior']['kill']for c in rs],[c['kill']for c in rs])for k in ['pred_prior','pred_feasibility','pred_corrected']}
 for c in cases:c.pop('fired_yaw_errors');c.pop('fired_pitch_errors')
 out=dict(schema='inklab.d3.calibration.report.v2',date='2026-10-21',native_trials=len(cases),void_attempts=len(invalid),full_d3_passed=False,model_native_rank_proven=False,parameters=parameters,spearman=match['spearman'],kendall_tau_b=match['kendall_tau_b'],rankings=dict(matched_prior=ranks_for(points,'matched_prior_prediction'),matched_post=match,global_prior_vs_native_validation_prior=ranks_for(points,'model_global_expected'),per_map={m:dict(prior=ranks_for([p for p in points if p['map']==m],'matched_prior_prediction'),post=ranks_for([p for p in points if p['map']==m],'matched_post_prediction'))for m in ['Yunohana','District00','Yagara']}),metrics=stages,points=points,cases=cases,invalid_attempts=invalid,summary='人形、静止反应对手，三初态/点；相关与条件误差只覆盖该夹具。全图先验和双敌模型未获得原生等价认证。',scope=['Step1 threat controls separately prove actual52 hits/KO.','Native initial prior: static reachable <=30u nodes, >=10u from source; human only, three sampled poses/point, stand/react18 only.','R1 correction: Beta(1,1) binding-neighborhood and bounded-aim feasibility, fit on trials0/1 only.','R2 correction: effective controller shot reliability, preparation median, defender aim/pitch error; fit on trials0/1, hold trial2 out. These are surrogate priors, not changed native weapon damage or universal player accuracy.','Native hook contact, finite projectile collision volumes, arbitrary elevation and camera/gyro coupling remain structural uncertainties.','Global-prior rank correlation is reported separately because its prior differs from native validation.','N3/point cannot establish highest native kill probability; Beta intervals overlap. No D3 success flag manufactured.'],source_sha256={str(p.relative_to(ROOT)):sha(p)for p in [Path(__file__),Path(__file__).with_name('native_calibration_data.py'),Path(__file__).with_name('conditional_predictions.py'),Path(__file__).with_name('calibrated_model.py'),Path(__file__).with_name('calibration_stats.py'),*a.batches]})
 out['rankings']['held_out_trial2_only']=dict(matched_prior=ranks_for(held_points,'matched_prior_prediction'),matched_post=ranks_for(held_points,'matched_post_prediction'),global_prior=ranks_for(held_points,'model_global_expected'))
 out['bands']=[dict(map=m,band=b,n=sum(c['map']==m and c['band']==b for c in cases),kills=sum(c['kill']for c in cases if c['map']==m and c['band']==b))for m in ['Yunohana','District00','Yagara']for b in ['high','middle','low']]
 a.out.mkdir(parents=True,exist_ok=True);(a.out/'report.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');(a.out/'parameters.json').write_text(json.dumps(parameters,indent=2)+'\n');print(json.dumps(dict(native_trials=len(cases),rankings=out['rankings'],metrics=stages,parameters=parameters),indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--batches',type=Path,nargs='+',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.batches=[p.resolve()for p in a.batches];a.out=a.out.resolve();main(a)
