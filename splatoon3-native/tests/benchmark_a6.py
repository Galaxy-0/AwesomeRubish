#!/usr/bin/env python3
"""One native training room; any policy manifest can produce a scorecard.

Run scenarios sequentially, never concurrently. New calls to act retain the
policy's declared cadence. Fixture setup and scoring use referee data only.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import traceback
from a6_lab import Lab, ROOT, neutral, uniform_loadout
from probe_a6_combat import prepare,heal_and_refill,trial as native_trial
from arena.config import PolicySpec
from arena.proficiency_process import ProficiencyProcess
from arena.control_process import own_special,encode_control
from arena.proficiency import scorecard, write_card, table,library_hashes,evaluation_hashes
from stamper import squid_roll,emerge_charge
from a6_metrics import large_hp_drops,roll_witness
from a6_motion import calibrate_roll


def approach_setup(lab):
    q=lab.info(1)['position'];x,y,z=q
    for offset in (3.,6.,-3.,0.):
        lab.navigate({1:(x+offset,y,z)});lab.paint_floor(1)
    lab.refill(1,180)
    lab.align(1,(x+12,y+1.1,z));lab.refill(1,180,surface=False)
    plan=squid_roll(lab.obs(1))
    run_up=[lab.info(1)]
    # The measured reaction window starts on the reversal/B edge. Run-up is
    # unopposed setup so a policy cannot kill the target before the roll.
    while lab.obs(1)['frame']<plan.start+30:
        result=plan.tick(lab.obs(1))
        if result.done:raise AssertionError('roll run-up precondition: '+result.status)
        lab.act(1,result.action,'approach-run-up',result.frames)
        run_up.append(lab.info(1))
    return plan,run_up


def reset_target(lab,position,distance):
    lab.step(lab.actions(),'training-knockback-settle',30)
    lab.navigate({1:position},'training-target-reset');lab.paint_floor(1)
    heal_and_refill(lab)
    q=lab.info(1)['position'];lab.align(0,(q[0],q[1]+1.1,q[2]),precise=distance>=12)


def main(args):
    spec=PolicySpec.load(args.policy)
    libraries=library_hashes();evaluation=evaluation_hashes()
    lab=Lab('benchmark-'+args.scenario,args.timeout,loadouts=[spec.loadout,uniform_loadout()],native_runtime=getattr(args,'native_runtime',None))
    lab.result.update(policy=spec.name,policy_root=str(spec.root),policy_source_sha256=spec.source_sha256,
                      policy_step_frames=spec.step_frames,library_sha256=libraries,evaluation_sha256=evaluation)
    try:
        calibration=None
        if args.scenario=='approach' and args.roll_calibration.is_file():
            value=json.loads(args.roll_calibration.read_text())
            if value!=calibrate_roll(value['source']) or not value['passed']:
                raise AssertionError('roll calibration differs from closed native controls')
            calibration=dict(path=str(args.roll_calibration.resolve().relative_to(ROOT)),
                             sha256=hashlib.sha256(args.roll_calibration.read_bytes()).hexdigest())
        lab.result['roll_calibration']=calibration
        lab.start();trials=[]
        if args.verify_emerge:
            prepare(lab,8.,source=(8.,3.,8.))
            # Paint the approach in the intended heading, rather than relying
            # on the original spawn-facing foot patch's lateral width.
            lab.paint_floor(0);lab.refill(0)
            q=lab.info(1)['position'];lab.align(0,(q[0],q[1]+1.1,q[2]))
            lab.refill(0,60,surface=False)
            before=lab.info(0);a=neutral();a['buttons'][1]=1;a['sticks'][1]=1.
            lab.act(0,a,'swim-approach-emerge',18)
            lab.add(dict(kind='swim-approach-emerge',before=before,after=lab.info(0)))
            native_trial(lab,'moving-emerge-full-damage',lambda obs:emerge_charge(obs,args.emerge_frames))
        distances=tuple(args.distances or (6.,12.,18.)) if args.scenario=='lateral' else (6.,)
        repeats=args.repeats if args.repeats is not None else (1 if args.scenario=='approach' else 3)
        baseline=None
        for index,distance in enumerate(d for d in distances for _ in range(repeats)):
            if index%repeats==0 or args.scenario=='approach':
                prepare(lab,distance,source=(-4.,3.,8.));baseline=tuple(lab.info(1)['position'])
            else:reset_target(lab,baseline,distance)
            target_plan,run_up=approach_setup(lab) if args.scenario=='approach' else (None,[])
            before=lab.info(1);source_before=lab.info(0)
            actual_distance=math.dist(source_before['position'],before['position'])
            budget=240 if args.scenario=='stationary' else (180 if args.scenario=='approach' else 90)
            down=None;first_visible=None;reaction=None;hps=[];trace=[];damage_events=[]
            damage_samples=[]
            held=neutral();previous_attack=False;previous_executed=False;cycle_closed=False
            with ProficiencyProcess(spec.root,lab.out/f'policy-{index}.stderr.log',spec.step_timeout) as policy:
                for frame in range(budget):
                    obs=lab.obs(0)
                    wire=None
                    visible=any(e['visible'] for e in obs['enemies'])
                    if visible and first_visible is None:first_visible=frame
                    if obs['frame']%spec.step_frames==0:
                        observation=lab.api.policy_observation('player_0')
                        meter=own_special(lab.info(0),'player_0',lab.origins['player_0']['frame'])
                        wire=json.loads(encode_control(observation,meter))
                        lab.result['last_policy_input']=wire
                        held=policy.act(observation,meter)
                    a=lab.actions();a['player_0']={k:list(v) for k,v in held.items()}
                    # Training fixture fixes the shooter's location and tests
                    # main-weapon aim/fire/refill, not tactical rushing or sub
                    # and special damage. Preserve the raw policy output too.
                    a['player_0']['sticks'][:2]=[0.,0.]
                    a['player_0']['buttons'][2:]=[0,0,0,0]
                    if args.scenario=='lateral':
                        if previous_executed and not held['buttons'][0]:cycle_closed=True
                        if cycle_closed:a['player_0']['buttons'][0]=0
                        previous_executed=bool(a['player_0']['buttons'][0])
                        # Camera-relative target strafe; align target along x
                        # first so its lateral stick travels along z.
                        own=lab.obs(1)['own'];yaw=own['view_yaw']
                        sign=1. if (frame//30)%2==0 else -1.
                        dx,dz=0.,sign
                        a['player_1']['sticks'][:2]=[-.85*dx*math.cos(yaw)+.85*dz*math.sin(yaw),.85*dx*math.sin(yaw)+.85*dz*math.cos(yaw)]
                    elif target_plan is not None:
                        target_result=target_plan.tick(lab.obs(1))
                        if not target_result.done:a['player_1']=target_result.action
                        else:
                            a['player_1']['buttons'][1]=1
                            p=lab.info(0)['position'];q=lab.info(1)['position']
                            direction=[run_up[-1]['position'][j]-run_up[0]['position'][j] for j in (0,2)]
                            ahead=(q[0]-p[0])*direction[0]+(q[2]-p[2])*direction[1]>0
                            if ahead and math.hypot(q[0]-p[0],q[2]-p[2])>1.5:
                                a['player_1']['sticks'][1]=-1.
                    attack=bool(a['player_0']['buttons'][0])
                    if attack and not previous_attack and first_visible is not None and reaction is None:
                        reaction=frame-first_visible
                    previous_attack=attack
                    lab.step(a,'benchmark-'+args.scenario,1)
                    i=lab.info(1)
                    if not i['hp_valid'] or not i['alive_valid']:raise AssertionError('missing native scoring sample')
                    if i['alive'] and (not i['position_valid'] or i['position'][1]<2.5):
                        raise AssertionError('training target escaped the flat fixture; cannot score an environmental down')
                    damage_samples.append(i)
                    hps.append(i['hp'])
                    trace.append(dict(frame=frame+1,target_hp=i['hp'],target_alive=i['alive'],
                                      sample_frame=i['position_sample_frame'],visible=visible,policy_action=held,
                                      policy_observation=wire,
                                      executed_action=a['player_0'],
                                      target_action=a['player_1'],
                                      target_referee_motion=i['referee_motion'],position_valid=i['position_valid'],
                                      target_hud_status=i['hud_status'][i['self_slot']],target_hud_valid=i['hud_valid'][i['self_slot']],
                                      shooter_position=lab.info(0)['position'],
                                      position=i['position']))
                    if not i['alive']:
                        if not i['self_slot_valid'] or not i['hud_valid'][i['self_slot']] or i['hud_status'][i['self_slot']]!=1:
                            raise AssertionError('target HUD became unavailable; not a native Down')
                        if not any(e['executed_action']['buttons'][0] for e in trace):
                            raise AssertionError('target down without an executed attack cannot score')
                        down=frame+1;break
            evidence=lab.out/f'trial-{index}.json'
            evidence.write_text(json.dumps(trace,indent=2)+'\n')
            damage_events=large_hp_drops(before,damage_samples)
            witness=roll_witness(run_up,before,damage_samples) if args.scenario=='approach' else None
            trial=dict(scenario=args.scenario,status='measured',distance=actual_distance,budget_frames=budget,
                       nominal_distance=distance,repeat=index%repeats,
                       time_remaining_at_start=source_before['remaining_time'],
                       distance_min=min([actual_distance]+[math.dist(e['shooter_position'],e['position']) for e in trace if e['target_alive']]),
                       distance_max=max([actual_distance]+[math.dist(e['shooter_position'],e['position']) for e in trace if e['target_alive']]),
                       attack_cycles=sum(bool(e['executed_action']['buttons'][0]) and
                           (index==0 or not trace[index-1]['executed_action']['buttons'][0]) for index,e in enumerate(trace)),
                       attack_frames=sum(e['executed_action']['buttons'][0] for e in trace),
                       masked_movement_frames=sum(any(abs(v)>.001 for v in e['policy_action']['sticks'][:2]) for e in trace),
                       roll_verified=bool(calibration and witness and witness['verified']),
                       roll_run_up=run_up,roll_proof=witness,roll_calibration=calibration,
                       roll_reason=witness['reason'] if calibration and witness else 'matched native roll calibration unavailable',
                       down_frame=down,target_hp_loss=before['hp']-min(hps),reaction_frames=reaction,
                       native_damage_events=damage_events,
                       target_baseline={k:before[k] for k in ('frame','position_sample_frame','hp','hp_valid','position','position_valid','referee_motion','alive')},
                       source_baseline={k:source_before[k] for k in ('frame','position_sample_frame','position','position_valid')},
                       released_attack_cycle=cycle_closed if args.scenario=='lateral' else None,
                       native_evidence=str(evidence),native_evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),first_visible_frame=first_visible)
            trials.append(trial);lab.add(trial)
        if PolicySpec.load(spec.root).source_sha256!=spec.source_sha256 or library_hashes()!=libraries or evaluation_hashes()!=evaluation:
            raise AssertionError('policy/public library/evaluation changed during benchmark')
        lab.result.update(passed=True,probe_completed=True,scorecard=str(args.out),trials=trials)
    except BaseException as e:
        lab.result['errors'].append(repr(e));lab.result['traceback']=traceback.format_exc()
    finally:lab.close()
    if lab.result['passed'] and not lab.result['errors']:
        proof=lab.out/'result.json';digest=hashlib.sha256(proof.read_bytes()).hexdigest()
        complete=[dict(t,native_run_result=str(proof),native_run_sha256=digest) for t in trials]
        card=scorecard(spec.name,spec.source_sha256,spec.loadout,complete,
                       library_sha256=libraries,evaluation_sha256=evaluation,step_frames=spec.step_frames)
        write_card(args.out,card);Path(args.out).with_suffix('.md').write_text(table(card))
    print(lab.out,flush=True)
    return 0 if lab.result['passed'] and not lab.result['errors'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--policy',type=Path,default=ROOT/'arena/proficiency-reference')
    p.add_argument('--scenario',choices=('stationary','lateral','approach'),required=True)
    p.add_argument('--repeats',type=int,choices=range(1,4))
    p.add_argument('--distances',type=float,nargs='+',choices=(6.,12.,18.),help='Lateral subset for a sequential follow-up run')
    p.add_argument('--out',type=Path,required=True);p.add_argument('--timeout',type=float,default=3600)
    p.add_argument('--roll-calibration',type=Path,default=ROOT/'work/a6/roll-calibration.json')
    p.add_argument('--verify-emerge',action='store_true',help='Also verify a real swim approach immediately followed by the observed 26-frame release')
    p.add_argument('--emerge-frames',type=int,choices=range(1,61),default=26)
    raise SystemExit(main(p.parse_args()))
