"""Closed D4 duel truth: HP callbacks, actual bind witnesses and strict budget.

No button-based kill/bind inference. Source/target clocks normalized by their
fixed controlled-frame offset; same-present zero is conservatively not a win.
"""
import argparse,json,re,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import PAT,sha

def reduce(path):
 d=json.loads(path.read_text());assert d['freeze_before']==d['freeze_after'];events=d['events'];start=next((e for e in events if e['event']=='before-RS'),None)
 if start is None:return dict(artifact=str(path.relative_to(ROOT)),eligible=False,errors=d['errors'],reason='no combat start')
 f=start['infos']['player_0']['frame'];offset=f-start['infos']['player_1']['frame'];hp=[[],[]];meter=[];shots=[[],[]]
 for role in[0,1]:
  log=Path(d['session'])/f'player-{role}/host.log';seen=set()
  for line in log.open(errors='replace'):
   m=re.search(r'RL_DAMAGE frame=(\d+) slot=\d+ hp=(-?\d+)',line)
   if m and int(m[1])+(offset if role else 0)>=f:hp[role].append(dict(frame=int(m[1])+(offset if role else 0)-f,hp=int(m[2])))
   if role==0:
    m=re.search(r'D4_METER frame=(\d+) slot=\d+ remaining=(-?\d+) readonly=1',line)
    if m and int(m[1])>=f:meter.append(dict(frame=int(m[1])-f,counter=int(m[2])))
   m=PAT.search(line)
   if m and m[2]=='setter_input'and int(m[1])+(offset if role else 0)>=f and m[4]in['5c76df0','5c75510','5c79398']:
    v=list(map(float,m[5].split(',')));key=(int(m[1]),m[3],m[4])
    if math.sqrt(sum(x*x for x in v))>.75 and key not in seen:shots[role].append(dict(frame=int(m[1])+(offset if role else 0)-f,vtable=m[4],velocity=v,position=list(map(float,m[6].split(',')))));seen.add(key)
 zero=next((m['frame']for i,m in enumerate(meter)if m['counter']<=0 and any(q['counter']>0 for q in meter[:i])),None);death=[next((r['frame']for r in rows if r['hp']<=0),None)for rows in hp];atkill=next((m['counter']for m in reversed(meter)if death[1]is not None and m['frame']<=death[1]),None);first=death[1]is not None and(death[0]is None or death[1]<death[0]);deadline=death[1]is not None and(zero is None or death[1]<zero)and atkill is not None and atkill>0
 p=path.with_name('sensors.jsonl');sensors=[json.loads(l)for l in p.open()]if p.exists()else[];binds=[s for s in sensors if s['native_frame']>=f and s['bind_witness']];bound=next(iter(binds),None)
 eligible=bool(d['calibration_eligible']and d['passed']);return dict(artifact=str(path.relative_to(ROOT)),sha256=sha(path),point=d['point'],repeat=d['repeat'],eligible=eligible,errors=d['errors'],tactic_failure=d.get('tactic_failure'),native_target_down=death[1]is not None,first_kill=first,strict_budget_win=bool(first and deadline),attacker_down=death[0],enemy_down=death[1],first_zero=zero,counter_at_enemy_down=atkill,damage_callbacks=hp,projectile_births=shots,bind_witness=None if bound is None else{k:bound[k]for k in['native_frame','anchor_world','hit_normal_world']},events=[dict(event=e['event'],frame=e['infos']['player_0']['frame']-f,counter=e['counter'],source=e['infos']['player_0']['position'],enemy=e['infos']['player_1']['position'],hp=[e['infos'][f'player_{n}']['hp']for n in[0,1]])for e in events],raw_sha256=d['raw_sha256'],scope='Ideal aim fixture. Static logical180deg FOV, real native intrinsic spread/HP/knockback retained. First KO and before-zero required; driver exit0 does not imply tactic success.')
def main(a):
 if a.out.exists():raise ValueError('fresh reduction')
 paths=[]
 for b in a.batches:
  batch=json.loads(b.read_text());paths.extend(ROOT/r['artifact']for r in batch['results']if r.get('artifact'))
 paths.extend(a.artifacts);rows=[reduce(p.resolve())for p in paths];out=dict(schema='inklab.d4.duel.summary.v1',runs=rows,full_d4_passed=False,source_sha256=sha(__file__));a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps([dict(point=r.get('point',{}).get('id'),eligible=r['eligible'],win=r.get('strict_budget_win'),attacker_down=r.get('attacker_down'),enemy_down=r.get('enemy_down'),bound=r.get('bind_witness')is not None,errors=r['errors'])for r in rows],indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--batches',type=Path,nargs='*',default=[]);p.add_argument('--artifacts',type=Path,nargs='*',default=[]);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
