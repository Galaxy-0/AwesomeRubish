"""Read-only missed launch sweep diagnosis against actual native stops."""
import json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d4.model_v2 import World
from tools.zipcaster_d3r.analyze_direction import PAT,sha
out=ROOT/'work/d4/launch-corner-v2.json'
if out.exists():raise ValueError('fresh diagnosis')
w=World(ROOT/'work/d4/graph-v2-Yunohana');results=[]
for path in sorted((ROOT/'work/a6').glob('d3-r-d4-duel2-*/result.json')):
 d=json.loads(path.read_text());f=next(e['infos']['player_0']['frame']for e in d['events']if e['event']=='light-input');samples=[]
 for l in(Path(d['session'])/'player-0/host.log').open():
  m=PAT.search(l)
  if m and m[4]=='5c75510'and f<=int(m[1])<=f+30:samples.append(dict(frame=int(m[1]),object=m[3],velocity=list(map(float,m[5].split(','))),position=list(map(float,m[6].split(',')))))
 birth=next(s for s in samples if math.dist(s['velocity'],[0,0,0])>2.7);stop=next(s for s in samples if s['object']==birth['object']and s['frame']>=birth['frame']and math.dist(s['velocity'],[0,0,0])<1e-8);steps=[json.loads(l)for l in path.with_name('steps.jsonl').open()];pose=next(r['infos']['player_0']['position']for r in steps if r['infos']['player_0']['frame']==birth['frame']);v=np.array(birth['velocity']);v/=np.linalg.norm(v);origin=np.array(pose)+[0,1,0];predictions=[]
 for offset in[0.,.8,1.4]:
  idx,p,dist=w.field.sphere(origin+v*offset,v,.3,10.);predictions.append(dict(offset=offset,hit=int(idx[0]),contact=p[0].tolist(),distance=float(dist[0]),native_stop_error=float(np.linalg.norm(p[0]-stop['position']))))
 results.append(dict(artifact=str(path.relative_to(ROOT)),sha256=sha(path),light_input=f,light_birth=birth,native_stop=stop,actual_own_foot_at_birth=pose,predictions=predictions,raw_sha256=d['raw_sha256']))
out.write_text(json.dumps(dict(schema='inklab.d4.launch.diagnosis.v1',cases=results,source_sha256=sha(__file__),scope='Both native cases used for debugging; not held-out accuracy. Same0.3u core proxy, no radius/aim fit. The model had skipped first1.4u launch sweep; preserve all offsets and missed native outcomes.'),indent=2)+'\n');print(json.dumps([dict(artifact=r['artifact'],errors=[p['native_stop_error']for p in r['predictions']])for r in results],indent=2))
