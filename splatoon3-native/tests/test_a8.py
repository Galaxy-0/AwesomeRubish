#!/usr/bin/env python3
"""Audit A8 after the complete native comparison and final A1-A6 regression.

This entry never builds the default host. Run the raw experiments separately;
the audit independently recomputes the comparison and checks native evidence.
"""
import argparse
import json
from pathlib import Path
import sys
from analyze_a8 import analyze
from audit_a7 import sha,require,read,reference,current
from arena.runner import write_json_atomic
from arena.proficiency import matching_card
from arena.config import PolicySpec
from test_a6 import audit_cards


def acceptance_basis(comparison,host,build,user_decision=None):
    """Keep the automatic 20% result distinct from an explicit user decision."""
    if user_decision is None:
        require(comparison['passed'],'score/trajectory equivalence or significant speedup failed')
        return dict(kind='automatic_20_percent_gate',automatic_performance_passed=True,accepted_by_user=False)
    decision=read(user_decision)
    require(decision.get('schema')=='arena.a8.user-decision.v1' and decision.get('decision')=='user_acceptance_below_20_percent','explicit user decision required')
    require(decision.get('decision_date')=='2026-10-20' and decision.get('automatic_fps_ratio_threshold')==1.2,'user decision cannot change automatic threshold')
    require(decision.get('host_sha256')==sha(host) and decision.get('host_build_sha256')==sha(host.with_suffix('.build.json')),'user decision host mismatch')
    require(comparison['equivalence_passed'] and comparison['performance']['fps_ratio']>1,'user decision cannot waive semantic equivalence or accept a slowdown')
    require(build['render_mode']=='camera' and build.get('copy_mode','none')=='none' and not build.get('experimental_hdr') and not build.get('test_only'),'user decision applies only to the camera production host')
    return dict(kind=decision['decision'],automatic_performance_passed=comparison['significant_speedup'],accepted_by_user=True,decision=reference(user_decision))


def continuous_fallback_basis(path,host):
    """Audit the explicit known-issue exception; require actual fresh BO3."""
    root=Path(__file__).resolve().parents[1]
    decision=read(path)
    require(decision.get('schema')=='arena.a8.continuous-fallback.v1' and decision.get('decision')=='user_acceptance_with_fresh_processes' and decision.get('decision_date')=='2026-10-21','explicit continuous fallback decision required')
    require(decision.get('host_sha256')==sha(host) and decision.get('session_lifecycle')=='fresh_per_match','fallback host/lifecycle mismatch')
    require(read(root/'arena/default-runtime.json').get('session_lifecycle')=='fresh_per_match','fallback lifecycle is not active in configuration')
    records={}
    for key in ('diagnostics','bo3'):
        row=decision[key];proof=root/row['path']
        require(sha(proof)==row['sha256'],'fallback evidence changed '+key);records[key]=read(proof)
    diagnostic=records['diagnostics']
    require(diagnostic['completed'] and not diagnostic['fix_validated'],'diagnostic stop/known-issue status missing')
    require(set(diagnostic['cases'])=={'immediate','delay120','calendar','cold','warm'},'three diagnostic experiments incomplete')
    for name,case in diagnostic['cases'].items():
        proof=root/case['path'];require(sha(proof)==case['sha256'],'diagnostic case changed '+name)
        raw=read(proof);require(raw['completed'] and not raw['errors'] and set(raw['branches'])=={'0','1'} and all(n in (33,34) for n in raw['branches'].values()),'diagnostic branch unavailable '+name)
    bo3=records['bo3'];valid=[m for m in bo3['matches'] if m['passed']]
    require(bo3['passed'] and not bo3['errors'] and len(valid)==3 and {m['stage'] for m in valid}=={1,2,3},'fresh three-map BO3 required')
    require(Path(bo3['native_runtime']['host']).resolve()==host.resolve(),'fallback BO3 host mismatch')
    require(len({pid for m in valid for pid in m['host_pids']})==6,'BO3 must use three independent native process pairs')
    current(read(Path(bo3['artifacts'])/'runtime-sha256.json'))
    for m in valid:
        require(m['native_winners'] and not m['void'] and not m['errors'],'fallback BO3 invalid Winners')
        for player in (0,1):
            options=read(Path(m['session'])/f'player-{player}/input.json')
            require(not options.get('DM_TEST_SPECIAL') and options['DM_RL_CLOCK_MODE']=='fixed60','fallback BO3 changed native semantics')
    return dict(accepted_known_issue=True,session_lifecycle='fresh_per_match',decision=reference(path),diagnostics=decision['diagnostics'],bo3=decision['bo3'],known_issue='same-PID return can enter NetRoot 33 without LobbyLocal Progress; native process reuse is disabled in arena runtime selection')


def audit(before,after,regression,components,capacity,user_decision=None,continuous_fallback=None):
    comparison=analyze(before.resolve(),after.resolve())
    candidate=read(after/'plan.json');host=Path(candidate['host']);build=read(host.with_suffix('.build.json'))
    basis=acceptance_basis(comparison,host,build,user_decision)
    r=read(regression);plan=read(regression.parent/'plan.json')
    current(read(after/'trial-0/result.json')['runtime_sha256'])
    require(r['passed'] and not r['errors'],'complete final A1-A6 regressions required')
    require(r['host_sha256']==sha(host)==build['output_sha256'],'regression host mismatch')
    require(set(r['jobs'])=={j['name'] for j in plan['jobs']}|{'a4'},'regression job set incomplete')
    require(len(r['jobs'])==19 and 'pixel-interface' in r['jobs'],'nineteen jobs including default pixel interface required')
    for name,job in r['jobs'].items():
        require(job['passed'] and job['exit_code']==0,'failed regression '+name)
        if 'record' not in job:continue
        require(sha(job['record'])==job['record_sha256'],'changed job '+name)
        bound=read(job['record']);require(bound['passed'] and not bound['errors'],'invalid native evidence '+name)
        current(bound['runtime_sha256'])
        for evidence in bound['evidence']:require(sha(evidence['path'])==evidence['sha256'],'changed evidence '+name)
        if name=='a6-special':
            special=bound['build']
            require(special.get('test_only') and special['production_parent']['sha256']==sha(host),'special derivative parent mismatch')
            require(special['render_mode']==build['render_mode'] and special.get('copy_mode','none')==build.get('copy_mode','none') and special['source_sha256']==build['source_sha256'],'special derivative renderer/copy/source mismatch')
            commands=[]
            for b in (build,special):
                cmd=list(b['command']);cmd[cmd.index('-o')+1]='<OUTPUT>'
                commands.append([v for v in cmd if v!='-DSPL3_A6_TEST_SPECIAL=1'])
            require(commands[0]==commands[1] and '-DSPL3_A6_TEST_SPECIAL=1' in special['command'],'special derivative changed flags')
        else:require(bound['host_sha256']==sha(host),'fixture host mismatch '+name)
    fallback=continuous_fallback_basis(continuous_fallback,host) if continuous_fallback else None
    require(read(Path(__file__).resolve().parents[1]/'arena/default-runtime.json').get('session_lifecycle','reuse')==('fresh_per_match' if fallback else 'reuse'),'default lifecycle requires a matching acceptance basis')
    if fallback:
        require(r['jobs']['a5'].get('fresh_processes') and not r['jobs']['a5']['continuous_same_pids'],'fresh-process A5 regression required for the explicit fallback')
    else:require(r['jobs']['a5']['continuous_same_pids'],'same-process A5 regression required')
    pixel=read(r['jobs']['pixel-interface']['record'])
    require(pixel['owned_sessions'],'default pixel M6 has no native sessions')
    for session in pixel['owned_sessions']:
        for player in (0,1):
            directory=Path(session)/f'player-{player}'
            options=read(directory/'input.json');log=(directory/'host.log').read_text(errors='replace')
            require(options.get('DM_RL_PIXELS','1')=='1' and 'RL_PIXELS enabled=1 ' in log,'default pixel M6 must enable native pixels')
            require('A8_CAMERA skipped=' not in log,'pixel session skipped camera history')
    a5job=r['jobs']['a5'];require(sha(a5job['evidence'])==a5job['evidence_sha256'],'changed A5 evidence')
    a5=read(a5job['evidence']);valid=[m for m in a5['matches'] if m['passed']]
    require(len(valid)==2 and all(m['native_winners'] and not m['void'] for m in valid),'two fresh paired Winners required')
    require({tuple(m['role_to_policy']) for m in valid}=={(0,1),(1,0)},'swapped roles required')
    if fallback:require(not set(valid[0]['host_pids'])&set(valid[1]['host_pids']),'A5 fallback pair reused native PIDs')
    historical=read(r['a5_historical_audit']['path'])
    require(historical['accepted'] and historical['valid_rounds']==70 and r['a5_historical_audit']['exit_code']==0,'historical A5 audit failed')
    require(r['a6_independent_card_audit'],'independent A6 trace audit missing')
    require(r['jobs']['a6-timing']['thresholds']=={'standing-charge':21,'surface-charge':26},'charge thresholds changed')
    from a6_motion import calibrate_roll
    roll=read(r['jobs']['a6-roll']['record']);require(len(roll['evidence'])==1,'roll evidence ambiguous')
    source=Path(roll['evidence'][0]['path']);require(read(source.with_name('roll-calibration.json'))==calibrate_roll(source),'roll calibration changed')
    cards={};runtime=dict(host=str(host),patched=str(Path(candidate['patched'])))
    for name in ('reference','alpha','bravo'):
        path=regression.parent/f'card-{name}-scorecard.json';card=read(path)
        require(card['measured']==card['total']==13,'thirteen trials required '+name)
        spec=PolicySpec.load(card['policy_version']['snapshot'])
        require(matching_card(path,spec,runtime)['status']=='available','scorecard/runtime mismatch '+name)
        audit_cards(dict(scorecards=[dict(policy_root=str(spec.root))]),[card])
        cards[name]=dict(**reference(path),source_sha256=card['source_sha256'],score=card['aggregate_score'])
    for name,digest in build['source_sha256'].items():require(sha(Path(__file__).resolve().parents[1]/name)==digest,'compile source changed '+name)
    root=Path(__file__).resolve().parents[1]
    require(build['default_unchanged'] and sha(root/'upstream/dm/host/dmhost')==build['default_sha256'],'default host changed')
    component=read(components);require(component['passed'],'component checks failed')
    for row in component['results']:
        require(row['exit_code']==0 and sha(row['log'])==row['sha256'],'component evidence changed')
    from analyze_a8_capacity import analyze as capacity_analysis
    c=read(capacity)
    require(c['passed'] and c['after'][0]['host_sha256']==sha(host),'capacity renderer mismatch')
    require(c==capacity_analysis(Path(c['before']['path']),Path(c['after'][0]['path']),[Path(p['path']) for p in c['after'][1:]]),'capacity evidence changed')
    from arena.native_runtime import default_runtime
    # The certificate produced by this successful audit activates the CLI;
    # do not require that output file before it has been written.
    selected=default_runtime(require_accepted=False)
    require(Path(selected['host'])==host.resolve() and Path(selected['patched'])==Path(candidate['patched']).resolve(),'default arena runtime differs from validated candidate')
    return dict(schema='arena.a8.acceptance.v1',passed=True,full_a8_passed=True,acceptance_basis=basis,default_runtime=selected,comparison=comparison,
        session_lifecycle='fresh_per_match' if fallback else 'reuse',continuous_fallback=fallback,
        regression=reference(regression),components=reference(components),capacity=reference(capacity),capacity_summary=c,scorecards=cards,host_build=build,
        auditor=reference(__file__),limitations=comparison['limitations'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','after','regression','components','capacity','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--user-decision',type=Path,help='Explicit version-bound user acceptance; automatic 20%% result remains unchanged')
    p.add_argument('--continuous-fallback',type=Path,help='Explicit user-authorized known-issue exception; requires fresh native BO3 and swapped pair')
    a=p.parse_args();r=audit(a.before,a.after,a.regression,a.components,a.capacity,a.user_decision,a.continuous_fallback);write_json_atomic(a.out,r);print(a.out)
