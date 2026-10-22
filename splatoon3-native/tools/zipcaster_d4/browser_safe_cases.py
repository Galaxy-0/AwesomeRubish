"""Read-only Python golden cases for the limited D4 browser model."""
import argparse,json,math
from pathlib import Path
import numpy as np
from tools.zipcaster_d4.model_blade_only import World
from tools.zipcaster_d4.query_blade_only import clean
from tools.zipcaster_d4.optimistic_blade_only import terminal_bound
from tools.zipcaster_d3r.analyze_direction import sha

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();assert not a.out.exists();maps=[]
 batch=json.loads(Path('work/d4/restart-v4/blade-common-full-v1/batch.json').read_text())
 for name in ['Yunohana','District00','Yagara']:
  w=World(Path('work/d4/graph-v2-'+name));shots=[];terms=[];queries=[];rng=np.random.default_rng(42210)
  for item in [x for x in batch['results']if x['state']['map']==name]:
   q=json.loads(Path(item['artifact']).read_text());enemy=np.array(q['enemy']);heading=q['heading_radians'];pool=q['top2'][:1]
   for status in ['occupied','dies-before-any-declared-route-can-move-or-kill','no-contact-excluded-route; unrestricted-kill-unknown']:
    rs=[r for r in q['rows']if r['status']==status]
    if rs:pool.append(rs[len(rs)//2])
   wins=[r for r in q['rows']if r.get('probability')==1 and r.get('edges')]
   if wins:pool.append(wins[len(wins)//2])
   for row in pool:queries.append(dict(enemy=q['enemy_index'],heading=q['heading_quadrant'],speed=q['speed'],start=row['start'],expected={k:row.get(k)for k in ['probability','status','remaining','exposure_frames','stealth','cost','kill_frame']}))
   nodes=[(r['start'],True)for r in q['top2'][:1]]+[(int(rng.integers(w.h)),False)]
   for node,ground in nodes:
    source=w.graph['ground'if ground else'attach'][node]
    for style in ['full','light']:
     for delta in [np.zeros(3),np.array([0,3,0])]:
      target=enemy+delta;r=w.shots.best(source,target,style);shots.append(dict(source=source,target=target,style=style,expected={k:r[k]for k in ['hit','native_pitch','clearance','player_contact_age','radius_bound_uncertain','field_margin']}))
    for speed in [20,40,60,129]:
     for program in ['full-light','light3','light-full','full2']:
      term=w.terminal(node,enemy,speed,program,ground);expected=None
      if term:
       path,arrival,events=w.route_path(dict(edges=()),term)if ground else(term['post'],0,[])
       expected=dict(cost=term['cost'],kill_frame=term['kill_frame'],damage_events=term['damage_events'],enemy_path=term['enemy_path'],simulation=w.simulate(path,arrival,term,enemy,heading))
      terms.append(dict(node=node,ground=ground,enemy=enemy,speed=speed,program=program,bound=terminal_bound(w,node,enemy,speed,program,ground),expected=expected,heading=heading))
  maps.append(dict(map=name,shots=shots,terminals=terms,queries=queries));print(name,len(shots),len(terms),len(queries),flush=True)
 a.out.write_text(json.dumps(clean(dict(maps=maps,source_sha256=sha(__file__))),separators=(',',':'))+'\n')
if __name__=='__main__':main()
