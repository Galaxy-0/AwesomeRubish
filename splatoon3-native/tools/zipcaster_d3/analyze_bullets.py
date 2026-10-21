"""Reduce D3 read-only bullet pool snapshots. Keep semantic confidence explicit."""
import argparse,json,re,struct,sys,math
from pathlib import Path
from collections import defaultdict
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import ROOT,sha

def analyze(result):
 d=json.loads(result.read_text());session=Path(d['session']);log=session/'player-1/host.log';groups=defaultdict(list);count=0
 for line in log.open(errors='replace'):
  m=re.search(r'D3_BULLET frame=(\d+).*?index=(\d+) object=(0x[0-9a-f]+) size=(\d+) data=([0-9a-f]+)',line)
  if not m:continue
  b=bytes.fromhex(m[5]);count+=1
  if len(b)!=int(m[4]):raise AssertionError('truncated snapshot')
  if len(b)<0x1270:continue
  vec=lambda off:list(struct.unpack_from('<3f',b,off))
  groups[m[3]].append(dict(frame=int(m[1]),index=int(m[2]),position_110_candidate=vec(0x110),position_11c_candidate=vec(0x11c),velocity_1130=vec(0x1130),previous_velocity_121c_candidate=vec(0x121c),phase_1238_candidate=struct.unpack_from('<I',b,0x1238)[0]))
 image=(ROOT/'work/d2b/main.bin').read_bytes()
 # Static virtual getter returns precisely these three float components.
 assert struct.unpack_from('<Q',image,0x5c79398+0x1a0)[0]==0x1a40710
 expected=bytes.fromhex('003051bd013451bd023851bdc0035fd6')
 assert image[0x1a40710:0x1a40720]==expected
 rows=[];birth=[]
 for address,history in groups.items():
  changed=[];last=None
  for r in history:
   key=(tuple(r['position_110_candidate']),tuple(r['velocity_1130']))
   if key!=last:changed.append(r);last=key
  active=[r for r in changed if np.linalg.norm(r['velocity_1130'])>.05]
  if active:
   v=active[0]['velocity_1130'];speed=float(np.linalg.norm(v));birth.append(speed)
   rows.append(dict(object=address,index=active[0]['index'],first_sample_speed=speed,first_sample_frame=active[0]['frame'],first_sample_yaw=math.atan2(v[0],v[2]),first_sample_elevation=math.atan2(v[1],math.hypot(v[0],v[2])),history=active))
 full_initial=[v for v in birth if v>=2.8]
 return dict(schema='inklab.d3.bullet_evidence.v1',result=str(result.relative_to(ROOT)),result_sha256=sha(result),source=str(log.relative_to(ROOT)),source_sha256=sha(log),objects_discovered=len(groups),moving_objects=len(rows),snapshot_count=count,velocity_getter=dict(vtable='0x5c79398',virtual_slot='0x1a0',function='0x1a40710',offsets=['0x1130','0x1134','0x1138'],image_sha256=sha(ROOT/'work/d2b/main.bin'),verified=True),first_sample_speed=dict(all=birth,full_initial_samples=full_initial,median=float(np.median(full_initial))if full_initial else None),objects=rows,limits=['Pool object position110/11c semantics are candidate previous/current segment coordinates, not independently established impact coordinates.','Speed is a direct native vector; first 4f sample can miss an early flight phase.','Initial velocity can include player-motion addition; >=2.8 threshold selects early samples, not all bullets.','Yaw/elevation changes include native spread, camera-to-muzzle parallax and body turn. Do not label their combined range as intrinsic spread.','Snapshots alone do not identify bullet age at every first sample or recover the RNG distribution.'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--result',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=analyze(a.result.resolve());a.out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k]for k in ['objects_discovered','moving_objects','snapshot_count','first_sample_speed']},indent=2))
