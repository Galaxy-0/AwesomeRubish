"""Physical vectors, not own-view changes, decide the scoped direction A/B."""
import argparse,json,re,math,hashlib
from pathlib import Path
import numpy as np
PAT=re.compile(r'D3R_PROJECTILE frame=(\d+) kind=(\w+) object=(0x[0-9a-f]+) vtable=([0-9a-f]+) velocity=([^ ]+) p110=([^ ]+) readonly=1')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def angle(a,b):
 a=np.asarray(a,float);b=np.asarray(b,float)
 return math.degrees(math.acos(float(np.clip(a@b/np.linalg.norm(a)/np.linalg.norm(b),-1,1))))
def summarize(vectors):
 if not vectors:return None
 v=np.asarray(vectors);v/=np.linalg.norm(v,axis=1)[:,None];mean=v.mean(axis=0);mean/=np.linalg.norm(mean)
 return dict(n=len(v),mean_direction=mean.tolist(),yaw=math.atan2(mean[0],mean[2]),elevation=math.atan2(mean[1],math.hypot(mean[0],mean[2])),max_angle_from_mean_degrees=max(angle(q,mean)for q in v))
def projectiles(path):
 d=json.loads(path.read_text());role=1 if d['d3r_probe']=='gun'else 0;log=Path(d['session'])/f'player-{role}/host.log';events=d['events'];samples=[]
 for line in log.open(errors='replace'):
  m=PAT.search(line)
  if m:samples.append(dict(frame=int(m[1]),kind=m[2],object=m[3],vtable=m[4],velocity=list(map(float,m[5].split(','))),position110=list(map(float,m[6].split(',')))))
 shots=[];seen=set()
 for e in events:
  label=e['event']
  if '-shot-'not in label:continue
  info=e['infos'][f'player_{role}'];f=info['frame'];full='-full-'in label;vt='5c79398'if role else'5c76df0'if full else'5c75510';speed_min=2.8 if role else.75 if full else 2.7
  # A birth-speed witness after this input. De-duplicate objects/frames; keep
  # finite-delay failures explicit instead of substituting camera direction.
  possible=[s for s in samples if f<s['frame']<=f+(45 if full else 20)and s['vtable']==vt and np.linalg.norm(s['velocity'])>=speed_min and(s['object'],s['frame'])not in seen]
  witness=min(possible,key=lambda s:(s['frame'],s['kind']!='setter_input'))if possible else None
  if witness:seen.add((witness['object'],witness['frame']))
  shots.append(dict(label=label,input_frame=f,own_view=info['own_view'],body_heading=info['heading'],position=info['position'],physical_witness=witness))
 groups={}
 for label in ['controller','direct-same','direct-changed']:
  for style in (['']if role else['light','full']):
   rs=[s for s in shots if s['label'].startswith(label+('-'+style if style else'')+'-shot-')];groups[label+('-'+style if style else'')]=summarize([r['physical_witness']['velocity']for r in rs if r['physical_witness']])
 comparisons=[]
 for style in (['']if role else['-light','-full']):
  a,b=groups['controller'+style],groups['direct-same'+style]
  comparisons.append(dict(style=style or'52',mean_angle_degrees=angle(a['mean_direction'],b['mean_direction'])if a and b else None,controller_internal_max_degrees=a['max_angle_from_mean_degrees']if a else None,direct_internal_max_degrees=b['max_angle_from_mean_degrees']if b else None,n=[a['n']if a else 0,b['n']if b else 0]))
 return dict(schema='inklab.d3r.direction.v1',mode=d['d3r_probe'],driver_completed=d['passed'],errors=d['errors'],samples=len(samples),shots=shots,groups=groups,comparisons=comparisons,physical_equivalence_passed=None,limits=['Finite pose/direction check only; no camera-readback-only pass.','First native birth-speed witness can include spread, body-turn, parallax and native delay. Raw vectors retained.','No binary pass threshold is inferred from insufficient native samples.'],source=str(path),source_sha256=sha(path),log=str(log),log_sha256=sha(log),analyzer_sha256=sha(__file__))
def hooks(path):
 d=json.loads(path.read_text());sensors=[json.loads(l)for l in path.with_name('sensors.jsonl').open()];groups={}
 for label in ['controller','direct-same']:
  start=next((e['infos']['player_0']['frame']for e in d['events']if e['event']==label+'-before-R'),None);end=next((e['infos']['player_0']['frame']for e in d['events']if e['event']==label+'-flight-end'),None)
  rows=[s for s in sensors if start is not None and end is not None and start<s['native_frame']<=end and s['state_native']==1 and s['hook_tip_world']is not None];vectors=[np.asarray(b['hook_tip_world'])-a['hook_tip_world']for a,b in zip(rows,rows[1:])if b['native_frame']>a['native_frame']and np.linalg.norm(np.asarray(b['hook_tip_world'])-a['hook_tip_world'])>.01];groups[label]=dict(native_tip_samples=[dict(frame=s['native_frame'],position=s['hook_tip_world'])for s in rows],direction=summarize(vectors),binds=[dict(frame=s['native_frame'],anchor=s['anchor_world'],normal=s['hit_normal_world'])for s in sensors if start is not None and end is not None and start<s['native_frame']<=end and s['bind_witness']])
 a,b=[groups[k]['direction']for k in ['controller','direct-same']]
 return dict(mode='hook',driver_completed=d['passed'],errors=d['errors'],groups=groups,mean_angle_degrees=angle(a['mean_direction'],b['mean_direction'])if a and b else None,physical_equivalence_passed=None,source=str(path),source_sha256=sha(path),sensor_sha256=sha(path.with_name('sensors.jsonl')),analyzer_sha256=sha(__file__))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--result',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();d=json.loads(a.result.read_text());r=hooks(a.result)if d['d3r_probe']=='hook'else projectiles(a.result);a.out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items()if k not in ['shots','groups']},indent=2))
