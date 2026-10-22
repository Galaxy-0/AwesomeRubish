"""Geometry-only selection of bounded diagnostic poses, no native outcomes."""
import argparse,json,math,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d4.query_model import World
from tools.zipcaster_d4.calibration_plan_v4 import reachable
from tools.zipcaster_d4.attack_geometry import basis,contact_overlap
from tools.zipcaster_d4.contact_shape import native_shape
from tools.zipcaster_d4.contact_field import shape_field
from tools.zipcaster_d3r.analyze_direction import sha


def main(a):
    if a.out.exists():raise ValueError('fresh output required')
    began=time.monotonic();found={k:[]for k in ['high-clear','side-wall-clear','los-origin-disagreement']};examined=0;by_map={}
    for name in ['Yunohana','District00','Yagara']:
        w=World(ROOT/('work/d4/graph-v2-'+name));z=w.graph;nav=reachable(w.meta['stage'])
        supported=np.array([int(i)in nav for i in z['ground_atlas_ids']]);shape=native_shape(w.shots.parameters['vertical_contact']['ShapeParam']);count=0
        for s,source in enumerate(z['ground']):
            if not supported[s]:continue
            delta=z['ground']-source;distance=np.linalg.norm(delta,axis=1);dy=delta[:,1]
            ids=np.flatnonzero(supported&(distance>2)&(distance<5.5)&((np.abs(dy)<.25)|((dy>2.8)&(dy<3.2))))
            for e in ids:
                enemy=z['ground'][e];yaw=math.atan2(delta[e,0],delta[e,2]);origin=source+basis(yaw,0)@np.array([0,1.2,.5])
                endpoints=enemy+np.array([[0,h,0]for h in [.35,.8,1.3]])
                body_los=w.field.clear_pairs(source+[0,1.1,0],endpoints).tolist();birth_los=w.field.clear_pairs(origin,endpoints).tolist();examined+=1;count+=1
                if not any(body_los)and not any(birth_los):continue
                aim=w.shots.best_contact(source,enemy,'full')
                if not aim['hit']or aim['clearance']<.15:continue
                _,elevation=w.shots.direction(yaw,aim['native_pitch'],'full');rotation=basis(yaw,elevation)
                yaw_overlap=contact_overlap(origin,basis(yaw,0),shape,enemy)
                hits=shape_field(w.field.tri,origin,rotation,shape);wall=any(h['surface_kind']=='wall-like'for h in hits)
                kinds=[]
                if dy[e]>2.8 and all(body_los)and all(birth_los)and not wall and not yaw_overlap['hit']:kinds.append('high-clear')
                if abs(dy[e])<.25 and all(body_los)and all(birth_los)and wall:kinds.append('side-wall-clear')
                if any(body_los)!=any(birth_los):kinds.append('los-origin-disagreement')
                if not kinds:continue
                row=dict(map=name,graph=str(w.directory.relative_to(ROOT)),source_index=s,enemy_index=int(e),source=source.tolist(),enemy=enemy.tolist(),height_difference=float(dy[e]),
                    aim=aim,body_los=body_los,birth_los=birth_los,yaw_only_overlap=yaw_overlap,field=hits,
                    score=float(aim['clearance']),selection='Geometry-only, ordinary-navigation support; physical standability and actual pose still require pre-shot native gate.')
                for kind in kinds:found[kind].append(row)
        by_map[name]=count;print('D4_DISAGREEMENT_MAP '+json.dumps(dict(map=name,pairs=count,found={k:len(v)for k,v in found.items()},seconds=time.monotonic()-began)),flush=True)
    for rows in found.values():rows.sort(key=lambda r:(-r['score'],abs(r['height_difference']-3)if r['height_difference']>2.8 else 0,r['map'],r['source_index'],r['enemy_index']))
    out=dict(schema='inklab.d4.contact.pose.disagreements.v1',examined=examined,by_map=by_map,candidates=found,seconds=time.monotonic()-began,source_sha256=sha(__file__),
             scope='All declared ordinary-supported grid pairs passing stated distance/height filters. No native damage outcome used; different poses are not called single-variable pairs.')
    a.out.write_text(json.dumps(out,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args())
