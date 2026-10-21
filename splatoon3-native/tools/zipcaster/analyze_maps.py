#!/usr/bin/env python3
"""D2 static hook candidates and sight witnesses, never a native reachability claim.

Derived point data remains ignored. This does not change D1's map computation.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster.surfaces import load_surfaces,first_hit
from arena.geometry import CollisionMesh,GeometricVision,VisionConfig
from arena.referee import PlayerTruth,RefereeSnapshot


def scalar(v,digits=3):return round(float(v),digits)
def xyz(p):return [scalar(v)for v in p]
def person(name,team,position):return PlayerTruth(name,team,8000,True,tuple(position),0.,1.,1.,False,0,False)
def witnesses(vision,observer,targets):return vision.witnesses(RefereeSnapshot('d2-static',0,(observer,*targets)),observer.player_id)


def wall_samples(tri,normals,areas,attributes,spacing=6.):
    points={}
    for i in np.flatnonzero((abs(normals[:,1])<.35)&(areas>.05)):
        attr=attributes[i]
        if 'SuperHookCantBind'in attr['mat_flags'] or 'SplPlayerSuperHookCheck'in attr['col_disable_flags']:continue
        face=tri[i];steps=max(1,math.ceil(max(np.linalg.norm(face[(j+1)%3]-face[j])for j in range(3))/spacing))
        for u in range(steps):
            for v in range(steps-u):
                a,b=(u+1/3)/steps,(v+1/3)/steps;p=face[0]+a*(face[1]-face[0])+b*(face[2]-face[0])
                key=tuple(np.round(p*4).astype(int))+tuple(np.round(normals[i]*10).astype(int))
                points.setdefault(key,(p,normals[i],i))
    return list(points.values())


def analyze_map(root,data,spacing,max_range):
    name=data['id'];directory=root/f'work/arena/maps/{name}'
    tri,normals,areas,attrs=load_surfaces(directory)
    # HookCheck-disabled surfaces are not assumed to block the native hook query.
    query_ids=np.array([i for i,a in enumerate(attrs)if 'SplPlayerSuperHookCheck'not in a['col_disable_flags']],dtype=int)
    hook_tri=tri[query_ids]
    sight=CollisionMesh.load(directory/'sight.npz');vision=GeometricVision(sight,VisionConfig(half_fov_degrees=180))
    walk_targets=tuple(person('walk-'+str(i),1,p[:3])for i,p in enumerate(data['visibility']))
    opponents=[dict(id=p['id'],kind='named_region_proxy',position=p['position'])for p in data['points']]
    opponents += [dict(id='ambush-'+str(i),kind='D1_static_ambush_proxy',position=p['position'])for i,p in enumerate(data['ambush'])]
    starts=[dict(id=p['id'],position=p['position'])for p in data['points']]
    starts += [dict(id='spawn-'+str(i),position=p)for i,p in enumerate(data['spawns'])]
    candidates=[];sampled=wall_samples(tri,normals,areas,attrs,spacing)
    for position,normal,index in sampled:
        if position[1]<data['heights'][0]-2 or position[1]>data['heights'][1]+16:continue
        approach_sides={}
        for start in starts:
            source=np.array(start['position']);eye=source+[0,1.1,0];direction=position-eye;distance=float(np.linalg.norm(direction))
            if not 3<=distance<=max_range:continue
            h=first_hit(hook_tri,eye,position)
            if h is None or np.linalg.norm(h[1]-position)>.12:continue
            facing=normal if np.dot(normal,eye-position)>=0 else -normal
            incidence=abs(float(np.dot(normal,direction/distance)))
            if incidence<.15:continue # sampling heuristic only, not a native angle rule
            attach=position+facing*.75-[0,.75,0]
            approach_sides.setdefault(int(np.dot(normal,facing)>=0),[facing,[]])[1].append(dict(start=start['id'],source=xyz(source),eye_to_anchor=scalar(distance),incidence_cosine=scalar(incidence),
                attach_pose_estimate=xyz(attach),native_reachable=None))
        if not approach_sides:continue
        for oriented,approaches in approach_sides.values():
            attach=position+oriented*.75-[0,.75,0]
            ground=sight.floor(attach[0],attach[2],top=attach[1]-.05,bottom=-30.)
            landing=None if ground is None else np.array([attach[0],ground,attach[2]])
            hanging_view=witnesses(vision,person('hanging',0,attach),walk_targets)
            landing_view=None if landing is None else witnesses(vision,person('landing',0,landing),walk_targets)
            targets=[]
            for target in opponents:
                enemy=person('enemy',0,target['position']);body=person('arrival',1,attach)
                point_seen=witnesses(vision,enemy,(body,))[0].line_clear
                separation=float(np.linalg.norm(np.array(target['position'])-attach))
                land_distance=None if landing is None else float(np.linalg.norm(np.array(target['position'])-landing))
                shot_clear=None if landing is None else sight.clear(landing+[0,1.1,0],np.array(target['position'])+[0,.7,0])
                targets.append(dict(target=target['id'],kind=target['kind'],position=target['position'],
                    attach_distance=scalar(separation),landing_distance=None if land_distance is None else scalar(land_distance),
                    enemy_can_see_attachment_if_looking=bool(point_seen),landing_center_ray_clear=shot_clear,
                    full_plus_light_geometry_candidate=bool(land_distance is not None and land_distance<=19 and shot_clear),
                    full_plus_light_nominal_damage=105,native_combo_verified=False,
                    caveat='105 assumes both isolated projectile hits before healing; no hit/angle/airborne guarantee'))
            # Potential exposure to named-region defenders along a straight hook trajectory.
            # Geometry only: acceleration timing and body-volume collision remain unverified.
            for approach in approaches:
                source=np.array(approach['source']);end=np.array(approach['attach_pose_estimate']);path=[source+(end-source)*t for t in np.linspace(0,1,9)]
                exposures=[]
                for target in opponents[:len(data['points'])]:
                    observer=person('defender',0,target['position']);bodies=tuple(person('path-'+str(i),1,p)for i,p in enumerate(path));seen=[bool(w.line_clear)for w in witnesses(vision,observer,bodies)]
                    exposures.append(dict(target=target['id'],first_visible_progress=next((i/8 for i,v in enumerate(seen)if v),None),visible_sample_fraction=scalar(sum(seen)/len(seen))))
                approach['potential_exposure']=exposures
            candidates.append(dict(id=name+'-hook-'+str(len(candidates)).zfill(4),anchor=xyz(position),normal=xyz(normal),
                material_flags=attrs[index]['mat_flags'],collision_disabled=attrs[index]['col_disable_flags'],
                paintability=('forced_unpaintable'if 'ForceColPaintNotPaintable'in attrs[index]['mat_flags'] else 'forced_paintable'if 'ForceColPaintPaintable'in attrs[index]['mat_flags']else 'unspecified'),
                native_status='unverified_static_candidate',approaches=approaches,attach_pose_estimate=xyz(attach),
                landing_estimate=None if landing is None else xyz(landing),
                hanging_view_percent=scalar(100*sum(bool(w.line_clear)for w in hanging_view)/len(walk_targets),1),
                landing_view_percent=None if landing_view is None else scalar(100*sum(bool(w.line_clear)for w in landing_view)/len(walk_targets),1),
                targets=targets))
            if len(candidates)%50==0:print(name,'processed',len(candidates),'candidates',flush=True)
    ranked=sorted(candidates,key=lambda c:(-sum(t['full_plus_light_geometry_candidate']for t in c['targets'][:len(data['points'])]),-(c['landing_view_percent']or 0),min(a['eye_to_anchor']for a in c['approaches'])))
    return dict(id=name,wall_samples=len(sampled),candidates=candidates,shortlist=[c['id']for c in ranked[:5]],
        selection='named-region coverage count, then potential landing sight, then shorter eye-to-anchor distance; heuristic, not a combat success rank',
        sources={str((directory/f).relative_to(root)):hashlib.sha256((directory/f).read_bytes()).hexdigest()for f in ('manifest.json','sight.npz','navigation.json')})


def main(args):
    derived=json.loads(args.input.read_text());result=dict(schema='inklab.d2.hook-layer.v1',maps=[],
        max_eye_to_anchor=args.max_range,sampling_spacing=args.spacing,generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
        limits=['Static Cmn/Pnt collision only, no moving objects or native hook-specific volume sweep.',
                'World triangle winding is not treated as an outward-facing normal guarantee; normals orient toward each source.',
                'Only near-vertical faces are sampled (abs(normal.y)<.35), with incidence>.15 as a selection heuristic, not a measured native validity cutoff.',
                'Potential vision uses GeometricVision 360 degree turning, native visibility/sandbox unchanged.',
                'Named regions and D1 ambush candidates are opponent proxies, not measured enemy camping density.',
                'Attach offset .75 normal and -.75 vertical and release landing below are geometry estimates, not a native pose solver.',
                '105 damage is conditional arithmetic; future native tests must validate timing, aim, healing and target response.'])
    args.out.parent.mkdir(parents=True,exist_ok=True)
    for m in derived['maps']:
        if args.stage and m['id']not in args.stage:continue
        result['maps'].append(analyze_map(ROOT,m,args.spacing,args.max_range));args.out.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps(dict(output=str(args.out),maps=[dict(id=m['id'],samples=m['wall_samples'],candidates=len(m['candidates']))for m in result['maps']],bytes=args.out.stat().st_size),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'showcase/data/derived.json');p.add_argument('--out',type=Path,default=ROOT/'work/d2/map-analysis-full.json')
    p.add_argument('--spacing',type=float,default=6.);p.add_argument('--max-range',type=float,default=35.);p.add_argument('--stage',nargs='+',choices=('Yunohana','District00','Yagara'));raise SystemExit(main(p.parse_args()))
