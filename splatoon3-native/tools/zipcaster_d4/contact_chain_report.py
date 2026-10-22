"""Reduce read-only native contact/half fixtures without exporting memory bytes."""
import argparse,json,re,struct
from pathlib import Path
from collections import Counter,defaultdict
from tools.zipcaster_d4.report_duel import reduce
from tools.zipcaster_d4.analyze_contact import SNAP
from tools.zipcaster_d3r.analyze_direction import sha

def report(path):
 path=path.resolve();d=json.loads(path.read_text());base={k:d.get(k)for k in ['passed','errors','session','owned_pids','chain_final_pose_gate','outcome']};base.update(artifact=str(path),artifact_sha256=sha(path))
 start=next((e for e in d.get('events',[])if e['event']=='before-RS'),None)
 if start is None:return base|dict(measured_slashes=0,reason='setup void beforeRS')
 f=start['infos']['player_0']['frame'];offset=f-start['infos']['player_1']['frame'];roles=[]
 for role in [0,1]:
  log=Path(d['session'])/f'player-{role}/host.log';text=log.read_text();off=offset if role else 0
  lines=[l for l in text.splitlines()if(m:=re.search(r'frame=(\d+)',l))and int(m[1])+off>=f]
  counts=Counter(k for l in lines if(m:=re.search(r'\b(D4_[A-Z_0-9]+) ',l))for k in[m[1]])
  life=[]
  for l in lines:
   m=re.search(r'D4_LIFE_STATE frame=(\d+) slot=(\d+) hp=(-?\d+) pending=(-?\d+)',l)
   if m:life.append(dict(frame=int(m[1])+off-f,slot=int(m[2]),hp=int(m[3]),pending=int(m[4])))
  captures=defaultdict(dict)
  for l in lines:
   m=SNAP.search(l)
   if m:captures[int(m[1])+off-f][m[2]]=bytes.fromhex(m[3])
  compound=[]
  for frame,blobs in captures.items():
   if 'd4_leaf_entries'not in blobs:continue
   b=blobs['d4_leaf_entries'];count=len(b)//128
   compound.append(dict(frame=frame,leaf_count=count,leaf_names=[b[i*128+0x1c:i*128+0x34].split(b'\0')[0].decode('ascii','replace')for i in range(count)],local_transform=[list(struct.unpack_from('<12f',b,i*128+0x40))for i in range(count)]))
  halves=defaultdict(lambda:defaultdict(dict));roots={}
  for l in lines:
   m=re.search(r'D4_HALF_ROOT frame=(\d+) stage=(\w+) actor=(0x\w+) vtable=(\w+) p=([^ ]+)',l)
   if m:roots[int(m[1])+off-f,m[2],m[3]]=dict(vtable=m[4],position=list(map(float,m[5].split(','))))
   m=re.search(r'D4_HALF_QUERY frame=(\d+) stage=(\w+) actor=(0x\w+) array=(\w+) index=(\d+) query=([^ ]+) qvtable=(\w+) state=(\d+) dead=(\d+) child=([^ ]+) cvtable=(\w+) child_flag=(\d+)',l)
   if m:
    key=(int(m[1])+off-f,m[2],m[3]);halves[key][m[4]][int(m[5])]=dict(present=m[6]not in['0x0','(nil)'],state=int(m[8]),dead=int(m[9]),child_flag=int(m[12]),child_vtable=m[11])
  transitions=[]
  for (frame,stage,actor),arrays in halves.items():
   if stage!='before':continue
   after=halves.get((frame,'after',actor))
   if not after:continue
   vt=roots[(frame,stage,actor)]['vtable'];n=7 if vt=='5c76df0'else 5;core=n//2
   for key,balls in arrays.items():
    gone=[j for j in range(n)if balls.get(j,{}).get('present')and not after.get(key,{}).get(j,{}).get('present')]
    if gone:transitions.append(dict(frame=frame,style='full'if n==7 else'light',array=key,removed=gone,surviving=[j for j in range(n)if after.get(key,{}).get(j,{}).get('present')],states_before=[balls.get(j)for j in range(n)],centre=core))
  roles.append(dict(role=role,log_sha256=sha(log),counts=dict(counts),life=life,compound=compound,half_transitions=transitions,
    half_observed_frames=len({k[0]for k in halves}),physics_interface_frames=sum('d4_body_interface'in v for v in captures.values())))
 truth=reduce(path)
 return base|dict(measured_slashes=sum(e['event']in['full-release','light-input']for e in d['events']),truth={k:truth[k]for k in ['strict_budget_win','enemy_down','counter_at_enemy_down','projectile_births']},roles=roles,
  observation_scope='Zero receiver/submit probe calls in a positive control is incomplete instrumentation, never evidence of no contact. Life pending1400 is native queued140;100HP death alone is censored. Compound leaf names are not independent halves.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--results',type=Path,nargs='+',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();assert not a.out.exists();rows=[report(p)for p in a.results];a.out.write_text(json.dumps(dict(schema='inklab.d4.chain.report.v1',runs=rows,source_sha256=sha(__file__),full_d4_passed=False),indent=2)+'\n');print(json.dumps([dict(artifact=r['artifact'],measured=r['measured_slashes'],errors=r['errors'],roles=[dict(role=v['role'],counts=v['counts'],transitions=v['half_transitions'])for v in r.get('roles',[])])for r in rows]))
