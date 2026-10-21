"""Native fixed-grid attack control reduction; no camera-only hit claims."""
import argparse,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import PAT,sha

def reduce(path):
 d=json.loads(path.read_text());assert'freeze_after'in d;role=1 if d['probe_kind']=='defender'else 0;target=1-role;log=Path(d['session'])/f'player-{role}/host.log';shots=[];physical=[]
 for line in log.open(errors='replace'):
  m=PAT.search(line)
  if m:physical.append(dict(frame=int(m[1]),kind=m[2],object=m[3],vtable=m[4],velocity=list(map(float,m[5].split(','))),position110=list(map(float,m[6].split(',')))))
 for r in d['records']:
  initial=r['before'][f'player_{role}'];victim=r['before'][f'player_{target}'];source=initial['position'];dest=victim['position'];f=initial['frame'];vt='5c79398'if role else'5c76df0'if r['style']=='full'else'5c75510';speed=2.8 if role else .75 if r['style']=='full'else 2.7
  candidates=[s for s in physical if f<s['frame']<=f+r['hold']+20 and s['vtable']==vt and np.linalg.norm(s['velocity'])>=speed];witness=min(candidates,key=lambda s:(s['frame'],s['kind']!='setter_input'))if candidates else None
  hp=[(h['infos'][f'player_{role}']['frame'],h['infos'][f'player_{target}']['hp'],h['infos'][f'player_{target}']['frame'])for h in r['history']];drop=(victim['hp']-min(q[1]for q in hp))*100 if hp else None;hit=next((q for q in hp if victim['hp']-q[1]>.1),None);vertical=None
  if witness:
   v=witness['velocity'];vertical=math.atan2(v[1],math.hypot(v[0],v[2]))
  shots.append(dict(index=r['index'],style=r['style'],native_pitch=r['native_pitch'],source=source,target=dest,horizontal_distance=math.hypot(dest[0]-source[0],dest[2]-source[2]),height_difference=dest[1]-source[1],hold_frames=r['hold'],damage=round(drop,4)if drop is not None else None,release_frame=f+r['hold'],first_damage=hit,physical_witness=witness,emitted_elevation=vertical,full_health_start=victim['hp']>.999,alive_after=r['after'][f'player_{target}']['alive']))
 for shot in shots:
  shot['damage_edges']=[]
  record=next(r for r in d['records']if r['index']==shot['index']);last=record['before'][f'player_{target}']['hp']
  for h in record['history']:
   info=h['infos'][f'player_{target}'];delta=last-info['hp']
   if delta>1e-6:shot['damage_edges'].append(dict(attacker_frame=h['infos'][f'player_{role}']['frame'],target_frame=info['frame'],drop_hp=round(delta*100,5)))
   last=info['hp']
  shot['direct_damage_hp']=sum(e['drop_hp']for e in shot['damage_edges']if e['drop_hp']>=20)
  shot['small_damage_hp']=sum(e['drop_hp']for e in shot['damage_edges']if e['drop_hp']<20)
 fits={}
 for style in{r['style']for r in shots}:
  ss=[r for r in shots if r['style']==style and r['emitted_elevation']is not None]
  if len(ss)>=2:
   coef=np.linalg.lstsq(np.array([[r['native_pitch'],1.]for r in ss]),np.array([r['emitted_elevation']for r in ss]),rcond=None)[0];fits[style]=dict(linear_elevation_scale=float(coef[0]),linear_elevation_bias=float(coef[1]),native_pitch_hit_window=[r['native_pitch']for r in ss if r['direct_damage_hp']>20],n=len(ss))
 return dict(schema='inklab.d3r.blade.pitch.control.v1',rate_scope='static native pitch scan, ideal-operation fixture',driver_completed=d['passed'],errors=d['errors'],kind=d['probe_kind'],shots=shots,fits=fits,full_d3r_passed=False,source=str(path),source_sha256=sha(path),host_log_sha256=sha(log),limits=['Single flat layout only; high/low pose windows need separate live controls.','Damage readback is quantized/lagged own state; retain both native acknowledgement clocks.','Birth velocity direction is physical evidence. Magnitude alone is not certified u/present speed.','Coarse pitch grid; hit entries are observed windows, gaps do not prove a continuous boundary.'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--result',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();d=reduce(a.result);a.out.write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:d[k]for k in['driver_completed','kind','fits','errors']},indent=2));print([(r['style'],r['native_pitch'],r['damage'])for r in d['shots']])
