#!/usr/bin/env python3
"""Coarse exhaustive finite atlas sweep, then disclosed sampled fine evaluation."""
import argparse,json,math,sys,time,hashlib
from pathlib import Path
from dataclasses import asdict
from functools import lru_cache
from collections import deque
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from geometry import ROOT,CollisionMesh,IndexedMesh,reachable
from batch_geometry import BatchMesh
from model import Config,hook_path,duel_batch,wilson
from arena.lib.atlas import MapAtlas

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n')

def coarse(args):
    started=time.monotonic();source=ROOT/'work/d2/map-analysis-full.json';data=json.loads(source.read_text());result=[];count=0;cfg=Config()
    for stage,m in enumerate(data['maps'],1):
        atlas=MapAtlas.load(stage);regions=['center','central_high','west_lane','east_lane'];starts={r:atlas.points[atlas.nearest(atlas.region(r))]for r in regions}
        ids=reachable(atlas,[*starts.values(),*[v['ground']for v in atlas.spawns.values()]]);enemy=np.array(atlas.points)[ids];rows=[]
        # Every reachable node contributes equal mass; all 8 headings and both
        # forms are enumerated analytically by the heading/form invariant bound.
        for c in m['candidates']:
            if 'SuperHookCantBind'in c['material_flags']or'SplPlayerSuperHookCheck'in c['collision_disabled']:continue
            if c['landing_estimate']is None:continue
            landing=np.array(c['landing_estimate']);dist=np.linalg.norm(enemy-landing,axis=1);near=dist<=30
            viable=(dist<=cfg.light_range)&(np.abs(enemy[:,1]-landing[1])<=8);upper=float(viable.sum()/len(enemy));count+=len(enemy)*16
            for a in c['approaches']:
                if a['start']not in starts:continue
                start=starts[a['start']];length=np.linalg.norm(np.array(c['anchor'])-np.array(start)-[0,1.1,0])
                if length>35:continue
                path,events=hook_path(start,[c['anchor']],[c['attach_pose_estimate']],cfg)
                if path is None:continue
                # Triangle inequality bound permits enemy walking towards the
                # landing during the whole fixed tactic, unlike a static circle.
                radius=cfg.light_range+cfg.enemy_walk*len(path)
                upper=float((dist<=radius).sum()/len(enemy))
                exposure=float(np.mean([e['visible_sample_fraction']for e in a['potential_exposure']]))
                # Ordering heuristic only. The separate distance bound is an
                # optimistic bound for this fixed no-pursuit two-shot tactic.
                score=upper*(1-.55*exposure)*(1+float(c['landing_view_percent']or 0)/200)
                rows.append(dict(id=c['id'],map=m['id'],stage=stage,start_region=a['start'],source=list(start),anchor=c['anchor'],normal=c['normal'],attach=c['attach_pose_estimate'],landing=c['landing_estimate'],material_flags=c['material_flags'],near_nodes=int(near.sum()),finite_model_movement_range_bound=upper,heuristic_score=score,old_exposure=exposure,path_frames=len(path),native_status=c['native_status']))
        result.append(dict(id=m['id'],stage=stage,reachable_nodes=len(ids),enemy_scenarios=len(ids)*16,starts=starts,rows=rows,reachable_ids=ids.tolist()))
        print('COARSE '+m['id']+' '+str(len(rows))+' starts/hooks',flush=True)
    out=dict(schema='inklab.d3.coarse.v1',calibrated=False,search_complete=False,not_for_player_recommendation=True,config=asdict(cfg),source_sha256=sha(source),maps=result,analytically_screened_enemy_scenarios=count,seconds=time.monotonic()-started,limits=['All reachable atlas nodes x8 headings x2 forms screened by heading/form-independent distance bound.','Uniform node/heading/form prior; human/swim surface state not live ink.','Existing static hooks are a sampled surface set, not all continuous wall points.','Heuristic sorting is not a proof that rejected candidates cannot beat fine candidates.','No native bind success inferred from geometric eligibility.','Multi-hook uses a capped beam graph when supplied; native calibration is pending.'])
    write(args.out,out);print(json.dumps(dict(seconds=out['seconds'],scenarios=count)))


def select_fine(coarse_data,per_map=6):
    selection=[]
    native=json.loads((ROOT/'work/d2c/results.json').read_text())
    # New selection uses rank quantiles (2 high/mid/low), spatially distinct.
    for m in coarse_data['maps']:
        rows=sorted(m['rows'],key=lambda r:-r['heuristic_score']);byid={}
        for r in rows:byid.setdefault(r['id'],r)
        unique=list(byid.values());used=[]
        for band,center in [('high',.05),('middle',.5),('low',.9)]:
            ordered=sorted(range(len(unique)),key=lambda i:abs(i/max(1,len(unique)-1)-center))
            taken=0
            for i in ordered:
                r=unique[i]
                if any(np.linalg.norm(np.array(r['anchor'])-p)<4 for p in used):continue
                used.append(np.array(r['anchor']));selection.append(r|dict(band=band,coarse_rank=i+1,coarse_total=len(unique)));taken+=1
                if taken==2:break
    return selection

def graph_motion(atlas,ids,heading,mode,horizon,cfg,mesh=None,threat=None):
    """Map-only preplanned walk; aim/fire reaction remains visibility-gated.

    A strafe or backwards route is selected before the attack. This represents
    a walking opponent, not clairvoyant movement triggered by an unseen hook.
    Endpoints follow existing conservative graph edges, interpolate per frame.
    """
    pts=np.array(atlas.points);out=np.empty((horizon,len(ids),3));current=np.array(ids).copy();position=pts[current].copy();goal=position.copy();targets=current.copy()
    cover_routes={};route_indices=np.zeros(len(ids),int);travelled=np.zeros(len(ids))
    if mode=='retreat' and mesh is not None and threat is not None:
        eye=np.array(threat)+[0,1.1,0]
        cover_mask=~np.logical_or.reduce([mesh.clear_many(eye,pts+[0,h,0])for h in [.12,.7,1.3]])
        for j,node in enumerate(ids):
            key=(int(node),float(heading[j]))
            if key in cover_routes:continue
            if cover_mask[node]:cover_routes[key]=[int(node)];continue
            queue=deque([(int(node),[int(node)])]);seen={int(node)};choices=[]
            while queue and len(seen)<=80:
                q,route=queue.popleft();delta=pts[q]-pts[node];distance=np.linalg.norm(delta)
                if len(route)>1 and cover_mask[q]:
                    backward=np.array([-math.sin(heading[j]),0,-math.cos(heading[j])]);penalty=max(0,-float(delta@backward))
                    choices.append((len(route)+penalty,route))
                if len(route)>=7:continue
                for nxt in atlas.edges[q]:
                    if nxt in seen or abs(pts[nxt,1]-pts[q,1])>.3 or np.linalg.norm(pts[nxt]-pts[node])>6:continue
                    seen.add(nxt);queue.append((nxt,route+[nxt]))
            cover_routes[key]=min(choices,key=lambda x:x[0])[1]if choices else []
    direction=np.stack([np.sin(heading+(math.pi/2 if mode=='strafe'else math.pi)),np.zeros(len(ids)),np.cos(heading+(math.pi/2 if mode=='strafe'else math.pi))],axis=1)
    for t in range(horizon):
        if mode!='stand':
            for j in np.where(np.linalg.norm(position-goal,axis=1)<.001)[0]:
                node=int(targets[j])
                route=cover_routes.get((int(ids[j]),float(heading[j])),[])
                if mode=='retreat' and route:
                    index=int(route_indices[j])+1
                    if index<len(route):route_indices[j]=index;targets[j]=route[index];goal[j]=pts[route[index]]
                    continue
                neighbors=atlas.edges[node]
                eligible=[q for q in neighbors if abs(pts[q,1]-position[j,1])<.3]
                if eligible:
                    nxt=max(eligible,key=lambda q:float((pts[q]-position[j])@direction[j]))
                    if (pts[nxt]-position[j])@direction[j]>.01:current[j]=node;targets[j]=nxt;goal[j]=pts[nxt]
            delta=goal-position;d=np.linalg.norm(delta,axis=1);step=np.minimum(np.minimum(d,cfg.enemy_walk),np.maximum(0,6-travelled));position+=delta*(step/np.maximum(d,1e-9))[:,None];travelled+=step
        out[t]=position
    return out

def fine(args):
    started=time.monotonic();data=json.loads(args.coarse.read_text());selection=select_fine(data);cfg=Config();
    if args.beam:
        beam_data=json.loads(args.beam.read_text())
        selection.extend(r|dict(band='beam')for m in beam_data['maps']for r in m['fine_sequences'])
    maps=[];rng=np.random.default_rng(cfg.seed)
    for m in data['maps']:
        if args.stage and m['stage']!=args.stage:continue
        atlas=MapAtlas.load(m['stage']);mesh=BatchMesh(CollisionMesh.load(ROOT/f'work/arena/maps/{m["id"]}/sight.npz').triangles);points=[]
        for selected in [r for r in selection if r['map']==m['id']]:
            tic=time.monotonic();path,events=hook_path(selected['source'],selected.get('sequence_anchors',[selected['anchor']]),selected.get('sequence_attach',[selected['attach']]),cfg);arrival=next(e['frame']for e in events if e['event']=='开始蓄力')
            # Attack posture drops from wall to ground under native-like gravity;
            # this is a calibration hypothesis, not a native landing guarantee.
            for t in range(arrival,len(path)):
                drop=.5*.016*(t-arrival)**2;path[t,1]=max(selected['landing'][1],selected['attach'][1]-drop)
            allids=np.array(m['reachable_ids']);pts=np.array(atlas.points);near=allids[np.linalg.norm(pts[allids]-selected['landing'],axis=1)<=30]
            sampled=near if args.enemy_nodes==0 else np.sort(rng.choice(near,min(args.enemy_nodes,len(near)),replace=False))
            ids=np.repeat(sampled,16);heading=np.tile(np.repeat(np.arange(8)*math.pi/4,2),len(sampled));forms=np.tile([False,True],len(sampled)*8);enemy=pts[ids]
            weights=np.where(forms & ~np.array(atlas.swimmable)[ids],0.,np.where(~forms & ~np.array(atlas.swimmable)[ids],2.,1.));probabilities=[];details=[];query_start=mesh.queries
            for b,mode in enumerate(['stand','strafe','retreat']):
                motion=graph_motion(atlas,ids,heading,mode,len(path),cfg,mesh=mesh,threat=selected['source']);clear=np.empty((len(path),len(ids)),bool)
                cache={}
                for t,p in enumerate(path):
                    eyes=motion[t]+np.c_[np.zeros(len(ids)),np.where(forms,.25,1.1),np.zeros(len(ids))]
                    key=(tuple(p),hashlib.sha256(eyes.tobytes()).digest())
                    if key not in cache:
                        unique,inverse=np.unique(eyes,axis=0,return_inverse=True);seen=np.zeros(len(unique),bool)
                        for h in [.12,.7,1.3]:
                            remaining=np.flatnonzero(~seen)
                            if len(remaining):seen[remaining]=mesh.clear_many(p+[0,h,0],unique[remaining])
                        cache[key]=seen[inverse]
                    clear[t]=cache[key]
                def projectile_clear(origins,targets):
                    return mesh.clear_pairs(origins,targets)
                r=duel_batch(path,arrival,enemy,heading,forms,clear,cfg=cfg,samples=args.samples,behavior=mode,seed=b,move_clear=dict(positions=motion,clear=clear),ballistic_clear=projectile_clear)
                p=r['kills'].mean(axis=1);probabilities.append(p);details.append(dict(behavior=mode,p_local=float(np.average(p,weights=weights)),kills=int(r['kills'].sum()),n=int(r['kills'].size),wilson95_conditional_iid_only=wilson(int(r['kills'].sum()),int(r['kills'].size)),trades=int(r['ties'].sum())))
            pp=np.stack(probabilities);local=float(np.average(pp.mean(axis=0),weights=weights));worst=float(min(np.average(v,weights=weights)for v in pp));mass=len(near)/m['reachable_nodes']
            # A behavior is chosen adversarially for this tactic, not after
            # drawing each individual enemy state; retain stricter statewise too.
            row=selected|dict(expected_kill_probability=local*mass,worst_behavior_kill_probability=worst*mass,statewise_worst_kill_probability=float(np.average(pp.min(axis=0),weights=weights))*mass,local_expected=local,local_worst=worst,near_prior_mass=mass,enemy_nodes_sampled=len(sampled),mc_per_scenario=args.samples,behavior_results=details,enemy_results=[dict(node=int(n),position=pts[n].tolist(),expected=float(np.average(pp[:,j*16:(j+1)*16].mean(axis=0),weights=weights[j*16:(j+1)*16])),worst=float(min(np.average(v,weights=weights[j*16:(j+1)*16])for v in pp[:,j*16:(j+1)*16])))for j,n in enumerate(sampled)],events=events,seconds=time.monotonic()-tic,geometry_queries=mesh.queries-query_start)
            points.append(row);write(args.out.with_name('fine-partial.json'),dict(maps=maps,current_map=m['id'],points=points));print('FINE '+json.dumps({k:row[k]for k in ['id','band','expected_kill_probability','worst_behavior_kill_probability','seconds']}),flush=True)
        maps.append(dict(id=m['id'],stage=m['stage'],points=points))
    result=dict(schema='inklab.d3.fine.v1',calibrated=False,search_complete=False,not_for_player_recommendation=True,config=asdict(cfg),coarse_sha256=sha(args.coarse),maps=maps,seconds=time.monotonic()-started,limits=['Fine set is six heuristic-quantile hooks per map; no claim of global optimum.','Multi-hook uses a capped beam graph when supplied; native calibration is pending.','Enemy nodes: all <=30u when enemy_nodes=0; otherwise explicit uniform sample. Uniform heading and valid form prior. Outside30u assumed zero for final-target combo and bounded6u opponent movement.','Movement is a map-only preplanned walk capped6u; reaction gates aiming/fire. Non-swimmable nodes put all form weight on human.','Retreat preplans a <=6u/6-edge static cover route against source position; if none, walks backwards. Current flight LOS is still evaluated each frame.','Light/full damage and timing model require D3 native validation.','Armor unknown: default no damage benefit.','Uniform spread plus Gaussian aim error are explicit priors, not measured native angular distribution.','Reported Wilson interval ignores shared geometry/MC correlations; not a total uncertainty interval.'])
    write(args.out,result)
if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('coarse');c.add_argument('--out',type=Path,default=ROOT/'work/d3/coarse.json')
    f=sub.add_parser('fine');f.add_argument('--coarse',type=Path,default=ROOT/'work/d3/coarse.json');f.add_argument('--out',type=Path,default=ROOT/'work/d3/fine.json');f.add_argument('--beam',type=Path);f.add_argument('--stage',type=int,choices=[1,2,3]);f.add_argument('--enemy-nodes',type=int,default=12);f.add_argument('--samples',type=int,default=8)
    a=p.parse_args();coarse(a)if a.cmd=='coarse'else fine(a)
