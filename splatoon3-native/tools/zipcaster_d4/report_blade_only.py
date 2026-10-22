"""Honest closed native totals for the contact-excluded D4 fallback.

No inferred wins from driver exit0, no old12 reuse, no censored setup as loss.
Native KO must precede gauge zero. Probability tests are exploratory iid-model
summaries, not player win rates or an unrestricted optimality certificate.
"""
import argparse,json,math
from pathlib import Path
from collections import defaultdict
import statistics
from tools.zipcaster_d4.report_duel import reduce
from tools.zipcaster_d3r.analyze_direction import sha
from tools.zipcaster_d4.model_v3 import ROOT


def fisher_greater(a,n,b,m):
 total=a+b;den=math.comb(n+m,n)
 return sum(math.comb(total,x)*math.comb(n+m-total,n-x)for x in range(a,min(n,total)+1)if 0<=n-x<=n+m-total)/den


def numeric_summary(values):
 return None if not values else dict(n=len(values),minimum=min(values),median=statistics.median(values),maximum=max(values),mean=statistics.mean(values))


def report(batch_path):
 batch=json.loads(batch_path.read_text());plan_candidates=[Path(k)for k,v in batch['source_sha256'].items()if v==batch['plan_sha256']];assert len(plan_candidates)==1;plan_path=plan_candidates[0]
 plan=json.loads(plan_path.read_text());assert sha(plan_path)==batch['plan_sha256'];byid={p['id']:p for p in plan['points']};valid=[];voids=[];unresolved=[];groups=defaultdict(lambda:defaultdict(list))
 for row in batch['results']:
  if not row.get('artifact'):
   unresolved.append(row);continue
  p=Path(row['artifact']);p=p if p.is_absolute()else ROOT/p
  d=json.loads(p.read_text());assert sha(p)==row['artifact_sha256'];point=byid[row['point']]
  if row['eligible']:
   truth=reduce(p.resolve());assert truth['strict_budget_win']==row['strict_budget_win'];counter=truth['counter_at_enemy_down'];actual=d.get('actual_pose_model')or{}
   r=dict(point=row['point'],band=point['band'],repeat=row['repeat'],artifact=str(p),artifact_sha256=sha(p),win=truth['strict_budget_win'],enemy_down=truth['enemy_down'],attacker_down=truth['attacker_down'],nominal_model=point['model'],
    counter_at_enemy_down=counter,native_remaining=None if counter is None else counter/540,
    actual_pose_model=actual,setup_errors=d.get('setup_errors'),raw_sha256=d['raw_sha256'],
    attack_exclusion=d.get('initial_contact_exclusion'),full_d4_passed=False)
   valid.append(r);groups[(point['graph'],point['region'])][point['band']].append(r)
  elif row['combat_started']:unresolved.append(row)
  else:voids.append(dict(point=row['point'],attempt=row['attempt'],artifact=str(p),sha256=sha(p),errors=row['errors']))
 summaries=[]
 for(graph,region),bands in groups.items():
  counts={b:dict(n=len(rs),wins=sum(r['win']for r in rs),kill_frames=numeric_summary([r['enemy_down']for r in rs if r['win']]),native_remaining=numeric_summary([r['native_remaining']for r in rs if r['win']]))for b,rs in bands.items()};tests={}
  if 'control'in counts:
   c=counts['control']
   for b in ['top1','top2']:
    if b in counts:
     q=counts[b];p=fisher_greater(q['wins'],q['n'],c['wins'],c['n']);tests[b]=dict(p_one_sided=p,p_bonferroni18=min(1,p*18),scope='Exploratory independent-Bernoulli assumption; same fixture repeats are not random player opponents.')
  summaries.append(dict(map=graph.split('-')[-1],region=region,bands=counts,tests=tests))
 assert len({(r['point'],r['repeat'])for r in valid})==len(valid),'duplicate eligible outcomes'
 complete=len(valid)==216 and batch['stop_reason']is None
 if complete:assert all(sum(r['point']==p['id']for r in valid)==8 for p in plan['points'])
 actual_eligible=[r for r in valid if r['actual_pose_model'].get('probability')in [0,1]]
 mismatches=[dict(point=r['point'],repeat=r['repeat'],predicted=r['actual_pose_model']['probability'],win=r['win'])for r in actual_eligible if bool(r['actual_pose_model']['probability'])!=r['win']]
 timing=[r['enemy_down']-r['actual_pose_model']['enemy_down']for r in actual_eligible if r['win']and r['actual_pose_model'].get('enemy_down')is not None]
 remaining=[r['native_remaining']-r['actual_pose_model']['remaining']for r in actual_eligible if r['win']and r['actual_pose_model'].get('remaining')is not None]
 return dict(schema='inklab.d4.blade-only.native.report.v1',full_d4_passed=False,complete_new216=complete,old12_reused=False,planned=216,valid=len(valid),setup_void_attempts=len(voids),unresolved_combats=len(unresolved),stop_reason=batch['stop_reason'],
  actual_pose_concordance=dict(eligible=len(actual_eligible),mismatches=mismatches,kill_frame_error=numeric_summary(timing),remaining_error=numeric_summary(remaining)),
  counter_capacity=540,by_state=summaries,runs=valid,voids=voids,unresolved=unresolved,
  source_sha256=sha(__file__),batch_sha256=sha(batch_path),plan_sha256=sha(plan_path),
  limits=['Only ordinary-navigation-supported setup domain; all-grid top2 remain separate in plan proofs.',
   'Whole-wave-clear and contact-disjoint declared model. Contact/native global optimum remain unclosed.',
   'One-sided Fisher values are descriptive until all216 complete; no acceptance from early stopped data.',
   'Same native fixture repeats; direct aim and full-special only for local measurement. No policies/T1/S1.'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,required=True);p.add_argument('--out',type=Path);a=p.parse_args();d=report(a.batch)
 if a.out:
  assert not a.out.exists();a.out.write_text(json.dumps(d,indent=2)+'\n')
 print(json.dumps({k:d[k]for k in ['planned','valid','complete_new216','setup_void_attempts','unresolved_combats','stop_reason','by_state']},indent=2))
