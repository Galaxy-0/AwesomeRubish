"""Export bounded diagnostic results and resource closure, never map arrays."""
import argparse,collections,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha
from tools.zipcaster_d4.report_duel import reduce

def edges(rows):
 out=[];last=None
 for row in rows:
  if row['hp']!=last:out.append(row);last=row['hp']
 return out
def main(a):
 if a.out.exists():raise ValueError('fresh numerical report path required')
 first=[];second=[];bindings={}
 for path in sorted((ROOT/'work/a6').glob('d3-r-d4-attack-r1-*/result.json')):
  d=json.loads(path.read_text());assert d['freeze_before']==d['freeze_after'];bindings[str(path.relative_to(ROOT))]=sha(path);cases=[]
  for row in d['records']:
   before=row['before']['player_1']['hp'];hp=[dict(frame=h['infos']['player_1']['frame']-row['before']['player_1']['frame'],hp=round(h['infos']['player_1']['hp']*1000))for h in row['history']];ee=edges(hp)
   cases.append(dict(index=row['index'],style=row['style'],pitch_delta=row['pitch_delta'],minimum_hp=round(min(h['hp']for h in hp)),direct70_window=any(680<=x['hp']-y['hp']<=720 for x,y in zip([dict(hp=round(before*1000))]+ee,ee)),target_down=any(x['hp']<=0 for x in hp),hp_edges=ee[:8],hp_edges_total=len(ee)))
  first.append(dict(artifact=str(path.relative_to(ROOT)),point=d['point']['id'],cases=cases,errors=d['errors'],bounded_stop=d.get('bounded_stop'),calibration_eligible=False))
 for path in sorted((ROOT/'work/a6').glob('d3-r-d4-duel5-attack-r2-*/result.json')):
  r=reduce(path);d=json.loads(path.read_text());bindings[str(path.relative_to(ROOT))]=sha(path);ee=edges(r['damage_callbacks'][1]);second.append(dict(artifact=str(path.relative_to(ROOT)),point=d['point']['id'],pitch_bias=d['attack_pitch_bias'],program=d['point']['program'],enemy_down=r['enemy_down'],strict_budget_win=r['strict_budget_win'],counter_at_enemy_down=r['counter_at_enemy_down'],target_hp_edges=ee[:8],target_hp_edges_total=len(ee),calibration_eligible=False,scope='Diagnostic offsets chosen after round1. Not independent native win-rate validation.'))
 assert len(first)==3 and len(second)==3
 rooms=list((ROOT/'work/a6').glob('d3-r-d4-*/result.json'));old=ROOT/'work/a6/d3-r-ideal2-Yunohana-b4-c1-t0-20261022-124632-068623/result.json';assert old.exists();rooms.append(old);pids=set();timeline=[];freeze=[]
 for path in rooms:
  d=json.loads(path.read_text());assert d['freeze_before']==d['freeze_after'];assert 'freeze_after'in d;pids.update(d.get('owned_pids',[]));timeline.extend([(path.parent.stat().st_birthtime,1),(path.stat().st_mtime,-1)]);freeze.append(d['freeze_after'])
 active=0;peak=0
 for time,delta in sorted(timeline):active+=delta;peak=max(peak,active)
 listing=subprocess.check_output(['ps','-axo','pid=,comm='],text=True);live={int(line.strip().split(None,1)[0]):line.strip().split(None,1)[1]for line in listing.splitlines()if line.strip()};active_owned=[p for p in pids if p in live and 'dmhost'in live[p]];assert not active_owned and peak<=3
 protected=json.loads((ROOT/'work/d4/meter-v1/protected.json').read_text());assert all(sha(ROOT/p)==h for p,h in protected.items());build=json.loads((ROOT/'work/d4/meter-v1/dmhost-aim.build.json').read_text());assert sha(ROOT/'work/d4/meter-v1/dmhost-aim')==build['output_sha256'];modules=build['private_module_sha256'];assert all(sha(ROOT/'work/d4/meter-v1/modules'/p)==h for p,h in modules.items())
 out=dict(schema='inklab.d4.blocker.v1',date='2026-10-22',status='stopped after two bounded elevation/contact diagnostic rounds did not close native-model consistency',full_d4_passed=False,diagnostic_round1=first,diagnostic_round2=second,remaining_blockers=['Missing native near-contact140 volume/first-hit timing changes optimal resource objective. Do not fit an arbitrary distance threshold to win outcomes.','High ledge first-full70 possible with raised pitch, but two fresh paired high-combo controls still failed to KO; core/player side-volume/spawn-position/ordinary-placement effects not closed.','Old projectile-only all-map traversal incomplete and not a calibrated probability. Full216 plan, Yagara cohort, extreme-budget chains not completed.'],resources=dict(rooms=len(rooms),owned_hosts=len(pids),peak_rooms_conservative=peak,active_owned_hosts=active_owned,protected_hosts_sha256=protected,private_modules_sha256=modules,all_room_freeze_before_after_equal=True,stale_freeze_scope='Existing6 mismatches include prior runner/policy/RL edits; inactive baseline mismatch list unchanged, not a claim those36files match the historical tournament manifest.'),evidence_sha256=bindings,source_sha256={str(Path(__file__).relative_to(ROOT)):sha(__file__)},scope='Numerical diagnosis only. No map meshes, original game bytes, generated page, screenshots or trace arrays. Test-only direct aim, full/infinite gauge in fixtures; no policies/default-host changes, no T1/S1.')
 a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(round1_cases=sum(len(x['cases'])for x in first),round2=[dict(point=x['point'],win=x['strict_budget_win'])for x in second],resources={k:out['resources'][k]for k in ['rooms','owned_hosts','peak_rooms_conservative','active_owned_hosts']}),indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args())
