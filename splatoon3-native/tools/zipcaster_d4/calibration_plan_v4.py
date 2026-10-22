"""Prospective216 cohort using an analytic global cost lower bound.

Enumerates every declared ground start; no native outcome is read. A ground
full-contact KO attaining the universal named-program lower bound is globally
optimal even against every0..3-hook route (hook/flight costs are positive).
Ordinary-navigation support and same-height preference select only exact
primary-cost/exposure ties. The complete all-start heatmap is a separate job.
"""
import argparse
import json
import math
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from arena.lib.atlas import MapAtlas
from tools.zipcaster_d4.model_v3 import World,Config,PROGRAMS,schedule
from tools.zipcaster_d3r.analyze_direction import sha


def lower_bound(speed,cfg=Config()):
    activation=(cfg.activation_frames-cfg.activation_drain_grace)*cfg.drain
    # Full-contact first hit140; light20 then35 (max55 per input) needs
    # the second light projectile. Its earliest birth+receipt is+15f,
    # following the measured30f light input spacing. Other full-prefixed
    # programs may stop after their first contact and share full1's bound.
    light2=(speed+30+11+cfg.receive_delay)*cfg.drain+2*cfg.light_cost
    full=(speed+4+cfg.receive_delay)*cfg.drain+cfg.full_cost if speed>=cfg.charge else math.inf
    light_full=(speed+30+cfg.charge+4+cfg.receive_delay)*cfg.drain+cfg.light_cost+cfg.full_cost
    programs=dict(light2=light2,light3=light2,full1=full,**{'full-light':full},full2=full,**{'light-full':light_full})
    programs={k:activation+v for k,v in programs.items()if schedule(speed,k,cfg)}
    best=min(programs.values())
    return dict(program_cost_lower_bounds=programs,global_cost_lower_bound=best,
                one_or_more_hooks_lower_bound=best+cfg.hook_cost,
                scope='Declared finite programs,100HP, no attacks/precharge before arrival; every hook/flight/B cost nonnegative. Contact140 and separate20+35 already included. Not an unrestricted game action proof.')


def reachable(stage):
    atlas=MapAtlas.load(stage)
    todo=[atlas.nearest(atlas.spawns[t]['ground'])for t in ['alpha','bravo']];seen=set(todo)
    for i in todo:
        for j in atlas.edges[i]:
            if j not in seen:seen.add(j);todo.append(j)
    return seen


def main(a):
    if a.out.exists():raise ValueError('fresh prospective plan required')
    states=json.loads(a.states.read_text())['states'];worlds={};nav={};points=[];proofs=[]
    bound=lower_bound(40)
    for state in states:
        name=state['map']
        if name not in worlds:worlds[name]=World(ROOT/state['graph']);nav[name]=reachable(state['stage'])
        original_state=dict(state);w=worlds[name];z=w.graph
        original_enemy=np.array(original_state['enemy'])
        candidates=[int(original_state['enemy_index'])]+sorted([i for i,p in enumerate(z['ground'])
            if i!=original_state['enemy_index'] and np.linalg.norm((p-original_enemy)[[0,2]])<=6.0001
            and abs(p[1]-original_enemy[1])<.25 and int(z['ground_atlas_ids'][i])in nav[name]],
            key=lambda i:(float(np.linalg.norm(z['ground'][i]-original_enemy)),i))
        neighborhood=[];chosen=None
        for enemy_index in candidates:
            state=dict(original_state,enemy_index=enemy_index,enemy=z['ground'][enemy_index].tolist())
            w=worlds[name];z=w.graph;enemy=np.array(state['enemy']);allterms=[]
            # This is the whole declared ground set, including unsupported layers.
            # Navigation is used only after all globally minimal ties are known.
            for start in range(w.g):
                source=z['ground'][start]
                if np.linalg.norm((source-enemy)[[0,2]])<.7 and abs(source[1]-enemy[1])<1.7:continue
                term=w.terminal(start,enemy,40,'full1',True)
                if term is not None and abs(term['cost']-bound['global_cost_lower_bound'])<1e-9:allterms.append(term)
            attempts=[];chosen=None
            for heading in [state['heading'],*[h for h in range(4)if h!=state['heading']]]:
                wins=[]
                for term in allterms:
                    path,arrival,events=w.route_path(dict(edges=[]),term)
                    out=w.simulate(path,arrival,term,enemy,heading*math.pi/2)
                    if not out['kill']or out['exposure_frames']!=0 or term['uncertainties']:continue
                    start=term['node'];source=z['ground'][start]
                    wins.append(dict(start=start,position=source.tolist(),probability=1,probability_interval=[1,1],
                        cost=term['cost'],remaining=1-term['cost'],exposure_frames=0,danger_frames=0,stealth=True,
                        hooks=[],edges=[],program='full1',kill_frame=out['enemy_down'],arrival_frame=arrival,
                        terminal_inputs=term['inputs'],attack_uncertainties=term['uncertainties'],
                        ordinary_support=int(z['ground_atlas_ids'][start])in nav[name]))
                supported=[r for r in wins if r['ordinary_support']]
                supported.sort(key=lambda r:(abs(r['position'][1]-enemy[1]),np.linalg.norm(np.array(r['position'])-enemy),r['start']))
                if len(supported)<2:attempts.append(dict(heading=heading,reason='fewer than2 ordinary-supported global-cost/exposure ties'));continue
                axis=np.array([math.sin(heading*math.pi/2),0,math.cos(heading*math.pi/2)]);pool=[]
                for start,source in enumerate(z['ground']):
                    if int(z['ground_atlas_ids'][start])not in nav[name]:continue
                    delta=source-enemy;distance=float(np.linalg.norm(delta));forward=float(delta@axis)
                    if not 2<distance<11 or forward<=2 or forward/distance<=.5:continue
                    path=np.repeat(source[None,:],32,axis=0)
                    outcome=w.simulate(path,0,dict(damage_events=[],kill_frame=31),enemy,heading*math.pi/2)
                    if outcome['attacker_down']is not None and outcome['attacker_down']<31:
                        pool.append(dict(start=start,position=source.tolist(),probability=0,probability_interval=[0,0],
                            status='modeled death during mandatory activation, before any declared action',
                            attacker_down=outcome['attacker_down'],hooks=[],program='full1',forward_margin=forward))
                pool.sort(key=lambda r:(abs(r['position'][1]-enemy[1]),np.linalg.norm(np.array(r['position'])-enemy),r['start']))
                if not pool:attempts.append(dict(heading=heading,reason='no interior-cone pre-action death control'));continue
                chosen=(heading,supported[:2],pool[0]);attempts.append(dict(heading=heading,reason='selected before cohort native outcomes'));break
            neighborhood.append(dict(enemy_index=enemy_index,enemy=state['enemy'],heading_attempts=attempts))
            if chosen is not None:break
        if chosen is None:
            a.out.with_suffix('.partial.json').write_text(json.dumps(dict(points=points,proofs=proofs,failed_neighborhood=neighborhood),indent=2)+'\n')
            raise AssertionError((name,original_state['region'],neighborhood))
        heading,top,control=chosen
        proofs.append(dict(map=name,region=state['region'],original_enemy=original_state['enemy'],selected_enemy=state['enemy'],enemy_neighborhood_attempts=neighborhood,ground_examined=w.g,bound=bound,
            global_full_contact_ties=len(allterms),heading_attempts=attempts,
            selected_top2_attain_global_bound=True,selection='Exact cost and exposure ties only; ordinary support, same height, then distance/ID. No native outcome read.'))
        for label,row in [('top1',top[0]),('top2',top[1]),('control',control)]:
            points.append(dict(id=f'{name}-{state["region"]}-{label}',graph=state['graph'],enemy=state['enemy'],
                enemy_index=state['enemy_index'],heading=heading,region=state['region'],source=row['position'],
                speed=40,hooks=[],program='full1',band=label,minimum_actual_control_margin=1.,model=row,
                selection_scope='Analytic global finite-program bound attained; geometry-only exact-score/exposure/navigation/height ties.'))
        print('D4_PROSPECTIVE_STATE '+json.dumps(dict(map=name,region=state['region'],heading=heading,
            top=[r['start']for r in top],control=control['start'],enemy=state['enemy'],original_enemy=original_state['enemy'],ground_examined=w.g)),flush=True)
    out=dict(schema='inklab.d4.native.plan.v4',points=points,repeats=8,planned=len(points)*8,
        proofs=proofs,states_sha256=sha(a.states),source_sha256=sha(__file__),enemy_selection='Original common state first; if no valid prospective comparison, same-height ordinary-supported neighbors within6u, distance/ID order, no native outcomes. Full enemy-state bank unchanged.',full_d4_passed=False,
        scope='Prospective9enemy states/27points/8repeats216. Analytic global-top2 certificate is not a completed all-start heatmap. Initial0/1 are finite-model predictions; native repetition is separate. No earlier changed-input trial reused.')
    a.out.write_text(json.dumps(out,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--states',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
