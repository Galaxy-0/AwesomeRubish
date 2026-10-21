"""Reduce completed cohort into numerical outcomes; preserve all failed tactics."""
import json,math
from pathlib import Path
from native import ROOT,sha

def case(path):
 d=json.loads(path.read_text());p=d['point'];rows=[json.loads(l)for l in path.with_name('steps.jsonl').open()];events={e['event']:e['infos']for e in d['events']};initial=events['before-R'];start=initial['player_0']['frame'];sensors=[json.loads(l)for l in path.with_name('sensors.jsonl').open()];bind=next((s for s in sensors if s['native_frame']>=start and s['bind_witness']),None)
 deltas=[];lastlight=None;fullhit=light_hit=False
 for a,b in zip(rows,rows[1:]):
  if b['label']=='hint-duel-light':lastlight=b['infos']['player_0']['frame']
  before=a['infos']['player_1']['hp'];after=b['infos']['player_1']['hp'];frame=b['infos']['player_0']['frame']
  if frame>=start and before-after>.1:
   deltas.append(dict(frame=frame,before=before,after=after,label=b['label']))
   fullhit|=abs(before-after-.7)<.001
   light_hit|=lastlight is not None and 0<=frame-lastlight<45 and (abs(before-after-.35)<.001 or before<=.351 and after==0)
 hashes={str(Path(k).relative_to(ROOT)):v for k,v in d['raw_sha256'].items()}
 for k,v in hashes.items():assert sha(ROOT/k)==v,k
 hashes[str(path.relative_to(ROOT))]=sha(path);hashes[str(path.with_name('sensors.jsonl').relative_to(ROOT))]=sha(path.with_name('sensors.jsonl'))
 history=d['reactive_history'];first=next((h['t']for h in history if h['visible']),None);fired=[h for h in history if h['fired']];assert all(h['visible']and first is not None and h['t']-first>=18 for h in fired)
 charge=events.get('charge-start');arrive=events.get('arrival');aim=events.get('aim-end');bind_near=bool(bind and math.dist(bind['anchor_world'],p['requested_anchor'])<=2.5)
 return dict(id=p['id'],map=p['map'],trial=d['trial'],band=p['band'],artifact=str(path.relative_to(ROOT)),eligible=d['calibration_eligible'],kill=d['outcome']['kill'],attacker_alive=d['outcome']['attacker_alive'],bind_any=bool(bind),bind_success=bind_near,anchor=bind['anchor_world']if bind else None,anchor_error=math.dist(bind['anchor_world'],p['requested_anchor'])if bind else None,hook_exposed=bool(bind)or str(d.get('tactic_failure','')).startswith('no native completed'),control_exposed=bool(aim)or d.get('tactic_failure')=='C aim budget180 exhausted',control_complete=bool(aim),tactic_failure=d.get('tactic_failure'),full_window70=bool(fullhit),light_window35_or_clampedKO=bool(light_hit),prepared_healthy=bool(charge and charge['player_1']['hp']>=.999),arrival_setup_frames=charge['player_0']['frame']-arrive['player_0']['frame']if charge and arrive else None,model_global_expected=p['model_global_expected'],native_target_prior_pool_nodes=p['native_prior_pool_nodes'],initial=dict(source=initial['player_0']['position'],target=initial['player_1']['position'],defender_heading=initial['player_1']['heading'],human=initial['player_1']['referee_motion']['form_squid']==0),hp_decreases=deltas,first_seen_tick=first,firing_ticks=len(fired),fired_yaw_errors=[h['yaw_error']for h in fired],fired_pitch_errors=[h['pitch_error']for h in fired],raw_sha256=hashes,owned_pids=d['owned_pids'])
