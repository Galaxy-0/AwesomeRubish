#!/usr/bin/env python3
"""A6 gate: components + independently audited native evidence, no host build.

Use --components-only during T1. The complete gate reads a manifest of completed,
hashed, one-room native experiments and regression (arena/results/a6-acceptance.json).
See arena/lib/stamper.md; missing evidence never becomes a passing milestone.
"""
import argparse
import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

from a6_lab import ROOT, MANIFEST, frozen_check, t1_running
from analyze_a6_timing import analyze as analyze_timing
from arena.proficiency import library_hashes,evaluation_hashes,scorecard as make_card,approach_summary
from arena.config import PolicySpec
from a6_metrics import large_hp_drops,roll_witness
from a6_motion import calibrate_roll
from a6_code_proof import operation_digest
from a6_special_gate import audit_test_special


def read_evidence(item,allow_errors=False):
    path=Path(item['path'])
    if not path.is_absolute():path=ROOT/path
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=item['sha256']:raise AssertionError('evidence changed: '+str(path))
    for name,expected in item.get('attachments_sha256',{}).items():
        attachment=Path(name);attachment=attachment if attachment.is_absolute() else ROOT/attachment
        if hashlib.sha256(attachment.read_bytes()).hexdigest()!=expected:
            raise AssertionError('native evidence attachment changed: '+str(attachment))
    result=json.loads(path.read_text())
    if result.get('errors') and not allow_errors:raise AssertionError('native errors: '+str(path))
    return result


def controller_proof(result,roots):
    dependency=ROOT/'arena/lib/skills.py'
    digest=hashlib.sha256(dependency.read_bytes()).hexdigest()
    recorded=[h for p,h in result.get('code_sha256',{}).items() if p.endswith('/skills.py')]
    base_proof='direct_base_sha256'
    if recorded and digest not in recorded:raise AssertionError('native controller imported a different base skills module')
    if not recorded:
        # The earliest combat driver predates per-module base snapshots. It
        # did enforce this exact T1 manifest before/after the owned room.
        frozen=json.loads(MANIFEST.read_text())
        checked=all(result.get(key)==dict(files=len(frozen),mismatches=[],active=True)
                    for key in ('freeze_before','freeze_after'))
        if digest!=frozen.get(str(dependency)) or not checked:
            raise AssertionError('legacy native proof lacks protected base-module evidence')
        base_proof='protected_T1_manifest_and_native_freeze_checks'
    module=ROOT/'arena/lib/stamper.py'
    if not module.is_file():module=ROOT/'arena/lib_a6/stamper.py'
    hashes=[h for path,h in result.get('code_sha256',{}).items() if path.endswith('/stamper.py')]
    if hashlib.sha256(module.read_bytes()).hexdigest() in hashes:return 'whole_module_sha256+'+base_proof
    tested=Path(result['artifacts'])/'tested-stamper.py'
    if not tested.is_file() or hashlib.sha256(tested.read_bytes()).hexdigest() not in hashes:
        raise AssertionError('tested controller snapshot missing/changed')
    if operation_digest(module.read_text(),roots)!=operation_digest(tested.read_text(),roots):
        raise AssertionError('operation/helper/constants differ from native controller: '+repr(roots))
    return 'unchanged_operation_dependency_ast+'+base_proof


def audit_cards(manifest,cards):
    for item,card in zip(manifest['scorecards'],cards):
        if any(card.get(k)!=v for k,v in approach_summary(card['trials']).items()):
            raise AssertionError('approach rates differ from measured trials')
        if card.get('library_sha256')!=library_hashes():raise AssertionError('scorecard public library changed')
        if card.get('evaluation_sha256')!=evaluation_hashes():raise AssertionError('scorecard evaluator changed')
        spec=PolicySpec.load(ROOT/item['policy_root'])
        if card['source_sha256']!=spec.source_sha256 or card['loadout']!=spec.loadout:raise AssertionError('scorecard policy changed')
        if card['policy_step_frames']!=spec.step_frames:raise AssertionError('scorecard cadence changed')
        if not any(r['scenario']=='approach' for r in card['trials']):raise AssertionError('roll-approach disposition missing')
        for row in card['trials']:
            trace=Path(row['native_evidence'])
            if not trace.is_absolute():trace=ROOT/trace
            if hashlib.sha256(trace.read_bytes()).hexdigest()!=row['native_evidence_sha256']:
                raise AssertionError('scorecard native trace changed')
            run=read_evidence(dict(path=row['native_run_result'],sha256=row['native_run_sha256']))
            if not run.get('passed') or run.get('policy_source_sha256')!=card['source_sha256'] or run.get('policy')!=card['policy']:
                raise AssertionError('scorecard lacks completed native policy run')
            if run.get('library_sha256')!=card['library_sha256'] or run.get('evaluation_sha256')!=card['evaluation_sha256']:
                raise AssertionError('native benchmark source snapshot differs from scorecard')
            if run['policy_step_frames']!=spec.step_frames:raise AssertionError('native policy cadence differs')
            raw=next((r for r in run['trials'] if Path(r['native_evidence']).resolve()==trace.resolve()),None)
            if raw is None:raise AssertionError('trial is absent from closed native run')
            expected=make_card(card['policy'],card['source_sha256'],card['loadout'],
                [dict(raw,native_run_result=row['native_run_result'],native_run_sha256=row['native_run_sha256'])],
                library_sha256=card['library_sha256'],evaluation_sha256=card['evaluation_sha256'])['trials'][0]
            for key in ('native_evidence','native_run_result'):
                path=Path(expected[key]);path=path if path.is_absolute() else ROOT/path
                expected[key]=str(path.resolve().relative_to(ROOT))
            if row!=expected:raise AssertionError('scorecard differs from its native trial/scoring definition')
            events=json.loads(trace.read_text())
            first=None;reaction=None;previous=False
            for event in events:
                frame=event['frame']-1
                if event['visible'] and first is None:first=frame
                attack=bool(event['executed_action']['buttons'][0])
                if attack and not previous and first is not None and reaction is None:reaction=frame-first
                previous=attack
                wire=event['policy_observation']
                if wire is not None and (wire['frame']%spec.step_frames or any(e['visible'] for e in wire['enemies'])!=event['visible']):
                    raise AssertionError('visible input/cadence differs from policy wire')
            if reaction!=raw['reaction_frames'] or first!=raw['first_visible_frame']:
                raise AssertionError('reaction differs from per-present input/visibility')
            if any(e['target_alive'] and (not e['position_valid'] or e['position'][1]<2.5) for e in events):
                raise AssertionError('environmental escape cannot become a proficiency down')
            if any(not e['target_alive'] and (not e['target_hud_valid'] or e['target_hud_status']!=1) for e in events):
                raise AssertionError('unavailable HUD cannot become a proficiency Down')
            if row['scenario']=='approach':
                samples=[dict(frame=e['frame']+raw['target_baseline']['frame'],
                    position_sample_frame=e['sample_frame'],position=e['position'],position_valid=e['position_valid'],
                    hp=e['target_hp'],hp_valid=True,alive=e['target_alive'],referee_motion=e['target_referee_motion']) for e in events]
                proof=roll_witness(raw['roll_run_up'],raw['target_baseline'],samples)
                calibration=raw.get('roll_calibration')
                calibrated=False
                if calibration:
                    value=read_evidence(calibration)
                    if value!=calibrate_roll(value['source']):raise AssertionError('roll calibration source changed')
                    calibrated=value['passed']
                if proof!=raw['roll_proof'] or bool(calibrated and proof['verified'])!=raw['roll_verified']:
                    raise AssertionError('approach roll witness differs from undamaged native trajectory')
            if row['status']!='measured':continue
            if abs(math.dist(row['source_baseline']['position'],row['target_baseline']['position'])-row['distance'])>1e-5:
                raise AssertionError('initial native benchmark distance differs')
            distances=[row['distance']]+[math.dist(e['shooter_position'],e['position']) for e in events if e['target_alive']]
            if min(distances)!=row['distance_min'] or max(distances)!=row['distance_max']:
                raise AssertionError('native distance interval differs')
            cycles=sum(bool(e['executed_action']['buttons'][0]) and
                (index==0 or not events[index-1]['executed_action']['buttons'][0]) for index,e in enumerate(events))
            if cycles!=row['attack_cycles'] or sum(e['executed_action']['buttons'][0] for e in events)!=row['attack_frames']:
                raise AssertionError('reported attack inputs differ from executed native trace')
            if row['scenario']=='lateral' and abs(row['distance']-row['nominal_distance'])>2.:
                raise AssertionError('moving fixture outside distance band')
            down=next((e['frame'] for e in events if not e['target_alive']),None)
            samples=[dict(frame=e['frame'],position_sample_frame=e['sample_frame'],hp=e['target_hp'],hp_valid=True) for e in events]
            hit=bool(large_hp_drops(row['target_baseline'],samples))
            if down!=row['time_to_down_frames'] or hit!=row['hit_window']:
                raise AssertionError('scorecard metrics differ from native trace')


def audit(manifest):
    if manifest.get('schema')!='arena.a6.acceptance.v1':raise AssertionError('A6 manifest schema')
    read_evidence(manifest['t1_runtime'])
    protected=Path(manifest['t1_runtime']['path'])
    if not protected.is_absolute():protected=ROOT/protected
    if protected.resolve()!=MANIFEST.resolve():raise AssertionError('unexpected protected T1 manifest')
    release=read_evidence(manifest['t1_release'])
    if not release['process_exited'] or release['freeze']!=dict(files=36,mismatches=[],active=False) or \
            release['runtime_manifest_sha256']!=manifest['t1_runtime']['sha256'] or \
            release['source_result_sha256']!=manifest['t1_source']['sha256']:
        raise AssertionError('public merge lacks a clean completed T1 release audit')
    native={}
    partial=[]
    for name,item in manifest['native'].items():
        value=read_evidence(item,allow_errors=item.get('allow_partial_normal_end',False))
        if value.get('errors'):
            if value['errors']!=["RuntimeError('A6 normal match duration exhausted')"] or not value.get('cases'):
                raise AssertionError('partial proof is only permitted for normal match expiry after completed cases')
            partial.append(name)
        native[name]=value
    timing=native['timing']
    if not timing.get('passed') or set(timing['thresholds'])!={'standing-charge','surface-charge'}:
        raise AssertionError('minimum charge threshold missing')
    timing_path=Path(manifest['native']['timing']['path'])
    if not timing_path.is_absolute():timing_path=ROOT/timing_path
    retained=analyze_timing(timing_path)
    if retained['minimum_observed_full_release']!=timing['thresholds']:
        raise AssertionError('charge reservation was refunded; not a full release')
    for kind,threshold in timing['thresholds'].items():
        rows=[c for c in timing['cases'] if c['kind']==kind]
        if not any(c['hold_frames']==threshold and c['full_cost'] for c in rows) or not any(c['hold_frames']==threshold-1 and not c['full_cost'] for c in rows):
            raise AssertionError('charge threshold lacks adjacent release control')
    combat={r['kind']:r for r in native['combat']['cases']}
    controller_proofs=dict(charge=controller_proof(native['combat'],['charge_slash']),
                           emerge_charge=controller_proof(native['combat'],['emerge_charge']))
    for name in ('minimum-full-damage','emerge-full-damage'):
        if not .699 <= combat[name]['target_hp_loss'] <= .701:raise AssertionError(name+' did not produce full70')
    moving=native['moving_emerge'];moving_rows={r['kind']:r for r in moving['cases'] if 'kind' in r}
    approach=moving_rows['swim-approach-emerge'];emerge=moving_rows['moving-emerge-full-damage']
    if math.dist(approach['before']['position'],approach['after']['position'])<.5 or any(
            approach[key]['referee_motion']['form_squid']!=1 for key in ('before','after')):
        raise AssertionError('moving emergence lacks a real native swim approach')
    held=sum(h.get('frames',0) for h in emerge['history'] if h['phase']=='charge')
    if emerge['before']['0']['frame']!=approach['after']['frame'] or not 26<=held<=30 or not .699<=emerge['target_hp_loss']<=.701:
        raise AssertionError('swim approach did not immediately produce a measured full release')
    controller_proofs['moving_emerge']=controller_proof(moving,['emerge_charge'])
    range_rows=[row for name,value in native.items() if name.startswith('range') for row in value['cases']]
    ranges={}
    for kind in ('light','full'):
        rows=[row for row in range_rows if row['kind'].startswith(kind+'-')]
        for row in rows:
            before=row['before'];actual=math.dist(before['0']['position'],before['1']['position'])
            if abs(actual-row['distance'])>1e-5 or before['1']['hp']<.999 or not before['1']['alive']:
                raise AssertionError('invalid range baseline')
        def direct(row):return bool(large_hp_drops(row['before']['1'],[h['infos']['player_1'] for h in row['history']]))
        hits=[r['distance'] for r in rows if direct(r)];misses=[r['distance'] for r in rows if not direct(r)]
        if not hits or not misses or not 0<max(hits)<min(misses):raise AssertionError('invalid range bracket')
        ranges[kind]=dict(farthest_hit=max(hits),nearest_miss=min(misses))
    unsupported=manifest.get('unsupported',{})
    required={'charge_keep','dash','combo_move','squid_roll','squid_surge','burst_bomb','zipcaster','predictive_aim','fast_turn'}
    supported=manifest.get('supported',{})
    if required != (set(unsupported)|set(supported)) or set(unsupported)&set(supported):
        raise AssertionError('every operation needs exactly one disposition')
    if 'charge_keep' not in unsupported:raise AssertionError('native charge keep must stay unsupported')
    for name,item in unsupported.items():
        if not item.get('reason') or not item.get('evidence'):raise AssertionError('unsupported lacks reason/evidence: '+name)
        if type(item['evidence']) is not list:raise AssertionError('unsupported needs hashed evidence list')
        for proof in item['evidence']:read_evidence(proof,allow_errors=True)
    # Hook traversal may be unsupported while the narrower, naturally full
    # RS activation claim still needs an independently checked native effect.
    activation=native['zip_activation']
    zip_row=next(c for c in activation['cases'] if c['kind']=='zipcaster')
    activation_samples=[h['infos']['player_0'] for h in zip_row['history']
                        if h['phase'] in ('special_press','special_activate')]
    zip_path=Path(manifest['native']['zip_activation']['path'])
    if not zip_path.is_absolute():zip_path=ROOT/zip_path
    activation_steps=[json.loads(line) for line in (zip_path.parent/'steps.jsonl').read_text().splitlines()]
    presses=[x for x in activation_steps if x['label']=='zipcaster-special_press']
    if zip_row['before']['special']!=1. or not zip_row['before']['special_valid'] or not activation_samples or \
            not all(h['alive'] and h['special_valid'] for h in activation_samples) or \
            min(h['special'] for h in activation_samples)>=.99 or len(presses)!=1 or \
            presses[0]['frames']!=1 or presses[0]['actions']['player_0']['buttons']!=[0,0,0,1,0,0]:
        raise AssertionError('full-meter one-present RS activation/consumption proof absent')
    # Operation-specific effect validators; labels or completed inputs cannot
    # certify the skill. Experimental action identities remain unsupported.
    for name,reference in supported.items():
        result=native[reference['run']]
        roots={'dash':'charge_slash','combo_move':'light_combo','burst_bomb':'burst_bomb',
               'zipcaster':'zipcaster','fast_turn':'fast_turn','predictive_aim':'PredictiveAim',
               'squid_roll':'squid_roll','squid_surge':'squid_surge'}
        root=reference.get('controller',roots[name])
        if root not in ({'fast_turn','FastTurn'} if name=='fast_turn' else {roots[name]}):
            raise AssertionError('unexpected operation controller')
        controller_proofs[name]=controller_proof(result,[root])
        row=next(c for c in result['cases'] if c['kind']==reference['case'])
        if name=='dash':
            release=next(h['infos']['player_0'] for h in row['history'] if h['phase']=='charge' and h['infos']['player_0']['frame']==max(x['infos']['player_0']['frame'] for x in row['history'] if x['phase']=='charge'))
            if math.dist(release['position'],row['after']['0']['position'])<2. or row['target_hp_loss']<.69:raise AssertionError('dash effect missing')
        elif name=='combo_move':
            if math.dist(row['before']['0']['position'],row['after']['0']['position'])<.3:raise AssertionError('post-swing movement absent')
            costs=[row['before']['0']['ink']-h['infos']['player_0']['ink'] for h in row['history']]
            if not costs or max(costs)<.155:raise AssertionError('three native light costs missing')
        elif name=='burst_bomb':
            events=large_hp_drops(row['before']['1'],[h['infos']['player_1'] for h in row['history']],minimum=.20)
            if row['before']['0']['ink']-min(h['infos']['player_0']['ink'] for h in row['history'])<.449 or not events:raise AssertionError('native bomb cost/direct damage missing')
        elif name=='zipcaster':
            activated=[h['infos']['player_0'] for h in row['history'] if h['phase']=='special_activate']
            hooks=[h['infos']['player_0'] for h in row['history'] if h['phase']=='hook_press']
            travel=max((math.hypot(h['position'][0]-activated[-1]['position'][0],h['position'][2]-activated[-1]['position'][2]) for h in hooks),default=0.) if activated else 0.
            if row['before']['special']<1. or row['after']['special']>=1. or travel<1. or \
                    not row['after']['alive'] or not all(h['alive'] for h in activated+hooks):
                raise AssertionError('full-meter live post-activation hook travel absent')
        elif name=='fast_turn':
            delta=row['after']['own_view']['yaw']-row['before']['own_view']['yaw']
            if not row['converged'] or abs(math.atan2(math.sin(delta),math.cos(delta)))<2.8:
                raise AssertionError('native 180-degree turn not confirmed')
            if root=='FastTurn':
                control=next(c for c in result['cases'] if c['kind']=='ordinary-turn-gyro-control')
                frames=row['after']['frame']-row['before']['frame']
                baseline=control['after']['frame']-control['before']['frame']
                if row['gyro_fallback'] or row['gyro_sign'] not in (-1.,1.) or not row['gyro_gain'] or frames>=baseline:
                    raise AssertionError('calibrated gyro did not beat the matched native stick control')
        elif name=='predictive_aim':
            aligned=[]
            for h in row['history']:
                if h['target'] is None or math.hypot(h['velocity'][0],h['velocity'][2])<=.01:continue
                p=h['own']['position'];target=h['target'];yaw=h['own']['view_yaw']
                error=math.atan2(target[0]-p[0],target[2]-p[2])-yaw
                aligned.append(abs(math.atan2(math.sin(error),math.cos(error)))<=.08)
            if not any(aligned):raise AssertionError('native camera never aligned with a moving-target lead')
        elif name=='squid_roll':
            source=Path(manifest['native'][reference['run']]['path'])
            if not source.is_absolute():source=ROOT/source
            if not calibrate_roll(source)['passed']:
                raise AssertionError('matched native roll controls do not establish a boosted reversal arc')
        elif name=='squid_surge':
            held=[h['infos']['player_0'] for h in row['history'] if h['phase']=='wall_charge']
            release=[h['infos']['player_0'] for h in row['history'] if h['phase']=='surge_release']
            control=next(c for c in result['cases'] if c['kind']=='surge-stopped-control')
            control_gain=max(h['infos']['player_0']['position'][1] for h in control['history'])-control['before']['position'][1]
            tail=[h['position'][1] for h in held[2:]]
            gain=max(h['position'][1] for h in release)-held[-1]['position'][1]
            healthy=all(h['hp_valid'] and h['hp']>=.999 and h['alive'] for h in held+release)
            if len(held)<8 or max(tail)-min(tail)>.35 or gain<4. or gain<control_gain+1. or not healthy or \
                    row['before']['position'][1]<4.5 or math.dist(row['before']['position'],control['before']['position'])>.7:
                raise AssertionError('stopped-wall charge/release boost lacks matched native control')
        else:
            raise AssertionError('operation has no accepted native identity validator: '+name)
    cards=[read_evidence(item) for item in manifest['scorecards']]
    if {c['policy'] for c in cards}!={'alpha','bravo','proficiency-reference'}:
        raise AssertionError('both frozen T1 policies and public reference need scorecards')
    source=read_evidence(manifest['t1_source'],allow_errors=True)
    t1_hashes=dict(zip(source['policies'],source['source_hashes']))
    if not {'alpha','bravo'}<=set(t1_hashes):raise AssertionError('T1 source revisions missing')
    if any(c['source_sha256']!=t1_hashes[c['policy']] for c in cards if c['policy'] in t1_hashes):
        raise AssertionError('proficiency is not for the frozen T1 source revisions')
    if not cards or not all(c.get('measured',0)>0 and any(r['scenario']=='stationary' and r['status']=='measured' for r in c['trials']) and {r.get('nominal_distance') for r in c['trials'] if r['scenario']=='lateral' and r['status']=='measured'}>={6.,12.,18.} for c in cards):
        raise AssertionError('native stationary/three-distance scorecard missing')
    audit_cards(manifest,cards)
    regression=read_evidence(manifest['regression'])
    if not regression.get('passed') or set(regression.get('milestones',{}))!={'a1','a2','a3a','a4','a5'}:
        raise AssertionError('A1–A5 regression incomplete')
    for name in ('a1','a2','a3a','a4'):
        item=regression['milestones'][name]
        value=read_evidence(dict(path=item['evidence'],sha256=item['sha256']))
        if not item['passed'] or not value['passed']:raise AssertionError('fresh regression failed: '+name)
    a5=regression['milestones']['a5']
    old=read_evidence(dict(path=a5['archive_audit'],sha256=a5['archive_audit_sha256']))
    fresh=read_evidence(dict(path=a5['evidence'],sha256=a5['evidence_sha256']))
    roles={tuple(m['role_to_policy']) for m in fresh['matches'] if m.get('passed')}
    if not a5['passed'] or not old['accepted'] or old['valid_rounds']<70 or not fresh['phase_passed'] or \
            fresh['statistics']['valid_games']!=2 or roles!={(0,1),(1,0)} or a5['fresh_rooms_parallel']!=1:
        raise AssertionError('A5 needs strict accepted70 audit and two fresh swapped single-room games')
    if t1_running():raise AssertionError('T1 still running; public merge/regression gate not released')
    if not (ROOT/'arena/lib/stamper.py').is_file():raise AssertionError('public library not merged')
    staged=ROOT/'arena/lib_a6/stamper.py'
    if staged.is_file() and (ROOT/'arena/lib/stamper.py').read_bytes()!=staged.read_bytes():raise AssertionError('public/staged library differs')
    return dict(native=list(native),range_brackets=ranges,controller_proofs=controller_proofs,zipcaster_activation_verified=True,partial_normal_end=partial,supported=sorted(supported),unsupported=unsupported,scorecards=len(cards))


def main(args):
    out=ROOT/'work/a6'/datetime.datetime.now().strftime('gate-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(passed=False,full_a6_passed=False,components_passed=False,errors=[],artifacts=str(out),freeze_before=frozen_check())
    try:
        for test in ('test_a6_components.py','test_a6_process.py','test_a6_scores.py','test_a6_research_analysis.py','test_a6_timing_analysis.py','test_a6_metrics.py','test_a6_code_proof.py'):
            subprocess.run([sys.executable,str(ROOT/'tests'/test)],check=True)
        result['components_passed']=True
        if not args.components_only:
            if not args.evidence.is_file():raise AssertionError('full A6 requires native acceptance manifest '+str(args.evidence)+'; see README')
            manifest=json.loads(args.evidence.read_text())
            result['audit']=audit(manifest)
            result['core_a6_passed']=True
            # GOAL's test-only full/infinite host switch is a separate required
            # delivery. Natural charge/RS evidence cannot satisfy this gate.
            result['test_special']=audit_test_special(manifest.get('test_special',{}),read_evidence)
            result['passed']=result['full_a6_passed']=True
    except BaseException as e:result['errors'].append(repr(e))
    result['freeze_after']=frozen_check();(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    return 0 if result['components_passed'] and args.components_only and not result['errors'] or result['full_a6_passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--components-only',action='store_true')
    parser.add_argument('--evidence',type=Path,default=ROOT/'arena/results/a6-acceptance.json');raise SystemExit(main(parser.parse_args()))
