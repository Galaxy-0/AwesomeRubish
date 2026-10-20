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


def audit(before,after,regression,components,capacity):
    comparison=analyze(before.resolve(),after.resolve())
    require(comparison['passed'],'score/trajectory equivalence or significant speedup failed')
    r=read(regression);plan=read(regression.parent/'plan.json')
    candidate=read(after/'plan.json');host=Path(candidate['host']);build=read(host.with_suffix('.build.json'))
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
            require(special['render_mode']=='camera' and special['source_sha256']==build['source_sha256'],'special derivative renderer/source mismatch')
            commands=[]
            for b in (build,special):
                cmd=list(b['command']);cmd[cmd.index('-o')+1]='<OUTPUT>'
                commands.append([v for v in cmd if v!='-DSPL3_A6_TEST_SPECIAL=1'])
            require(commands[0]==commands[1] and '-DSPL3_A6_TEST_SPECIAL=1' in special['command'],'special derivative changed flags')
        else:require(bound['host_sha256']==sha(host),'fixture host mismatch '+name)
    require(r['jobs']['a5']['continuous_same_pids'],'same-process A5 regression required')
    a5job=r['jobs']['a5'];require(sha(a5job['evidence'])==a5job['evidence_sha256'],'changed A5 evidence')
    a5=read(a5job['evidence']);valid=[m for m in a5['matches'] if m['passed']]
    require(len(valid)==2 and all(m['native_winners'] and not m['void'] for m in valid),'two fresh paired Winners required')
    require({tuple(m['role_to_policy']) for m in valid}=={(0,1),(1,0)},'swapped roles required')
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
        audit_cards([path]);cards[name]=dict(**reference(path),source_sha256=card['source_sha256'],score=card['aggregate_score'])
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
    return dict(schema='arena.a8.acceptance.v1',passed=True,full_a8_passed=True,comparison=comparison,
        regression=reference(regression),components=reference(components),capacity=reference(capacity),capacity_summary=c,scorecards=cards,host_build=build,
        auditor=reference(__file__),limitations=comparison['limitations'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','after','regression','components','capacity','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=audit(a.before,a.after,a.regression,a.components,a.capacity);write_json_atomic(a.out,r);print(a.out)
