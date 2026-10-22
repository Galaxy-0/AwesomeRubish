"""Reduce closed zero-boundary probes. Keep setup voids, never infer from buttons."""
import argparse,json,re,sys,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import PAT,sha

def reduce(path):
 run=json.loads(path.read_text());assert'freeze_after'in run;assert run['freeze_before']==run['freeze_after'];session=Path(run['session']);logs=[session/f'player-{i}/host.log'for i in[0,1]];records=[]
 for rec in run['records']:
  events={e['event']:e for e in rec['events']};last=events.get('final-light-input')
  if last is None:continue
  f=last['infos']['player_0']['frame'];offset=f-last['infos']['player_1']['frame'];end=events['case-end']['infos']['player_0']['frame'];meter=[];births=[]
  for l in logs[0].open(errors='replace'):
   m=re.search(r'D4_METER frame=(\d+) slot=\d+ remaining=(-?\d+) readonly=1',l);kind='meter1'
   if not m:m=re.search(r'D2B_CANONICAL frame=(\d+) slot=\d+ key=\d+ remaining=(-?\d+)',l);kind='canonical4'
   if m and f-8<=int(m[1])<=end:meter.append(dict(frame=int(m[1]),remaining=int(m[2]),source=kind))
   p=PAT.search(l)
   if p and p[2]=='setter_input'and p[4]=='5c75510'and f<=int(p[1])<=f+45:
    v=list(map(float,p[5].split(',')))
    if math.sqrt(sum(x*x for x in v))>2.7:births.append(dict(frame=int(p[1]),velocity=v))
  if any(m['source']=='meter1'for m in meter):meter=[m for m in meter if m['source']=='meter1']
  zero=next((m for m in meter if m['frame']>=f and m['remaining']<=0),None);positive=next((m for m in reversed(meter)if zero and m['frame']<zero['frame']and m['remaining']>0),None);interval=[positive['frame']+1 if positive else f,zero['frame']]if zero else None
  damage=[]
  for l in logs[1].open(errors='replace'):
   m=re.search(r'RL_DAMAGE frame=(\d+) slot=\d+ hp=(-?\d+)',l)
   if m and f<=int(m[1])+offset<=end:damage.append(dict(frame=int(m[1])+offset,target_native_frame=int(m[1]),native_hp=int(m[2])))
  ko=next((d for d in damage if d['native_hp']<=0),None);birth=next(iter(births),None)
  records.append(dict(artifact=str(path.relative_to(ROOT)),index=rec['index'],eligible=bool(rec['eligible']),prime70=rec['prime70'],input_frame=f,requested_counter=run.get('requested_native_counter'),counter_at_input=last['remaining_native'],zero_interval=interval,zero_sample=zero,previous_positive=positive,first_light_birth=birth,ko=ko,target_hp_at_input=last['infos']['player_1']['hp'],native_target_down=rec['target_down'],d4_deadline_confirmed=bool(ko and interval and ko['frame']<interval[0]),scope='Native HP callback and own projectile direction, source-frame normalized target. Interval width1 only with per-present meter; coarse samples never promoted to exact same-frame order.'))
 return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),passed=run['passed'],errors=run['errors'],requested_counter=run.get('requested_native_counter'),closed=True,records=records,raw_sha256=run['raw_sha256'])
def main(a):
 if a.out.exists():raise ValueError('fresh reduction output')
 files=sorted((ROOT/'work/a6').glob('d3-r-d4-zero*/result.json'));closed=[p for p in files if'freeze_after'in json.loads(p.read_text())];rows=[reduce(p)for p in closed];out=dict(schema='inklab.d4.zero.summary.v1',runs=rows,open_runs=[str(p.relative_to(ROOT))for p in files if p not in closed],full_d4_passed=False,source_sha256=sha(__file__));a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps([dict(path=r['path'],errors=r['errors'],records=r['records'])for r in rows],indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args())
