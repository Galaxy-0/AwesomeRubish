#!/usr/bin/env python3
"""Sign A7 only after version-bound 3+3 reproducibility and complete regressions.

Raw game artifacts stay under work/. The output contains metrics, source hashes
and evidence links, never game data or screenshots.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import statistics
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.runner import write_json_atomic


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,message):
    if not value:raise AssertionError(message)
def read(path):return json.loads(Path(path).read_text())
def reference(path):
    p=Path(path).resolve();return dict(path=str(p.relative_to(ROOT)),sha256=sha(p))
def current(mapping):
    for path,digest in mapping.items():require(sha(path)==digest,'runtime changed: '+path)


def audit_continuous(c,host_sha256):
    require(c['passed'] and not c['errors'] and c['host_sha256']==host_sha256,'final cross-map continuity failed')
    require(c['stages']==[2,3] and c['pool']=={'starts':1,'reuses':1},'cross-map process reuse missing')
    require(len(c['matches'])==2 and c['matches'][0]['host_pids']==c['matches'][1]['host_pids'],'cross-map PID mismatch')
    require(all(m['passed'] and m['native_winners'] and not m['void'] for m in c['matches']),'cross-map paired Winners missing')
    entered=[e for e in c['events'] if e['phase']=='ingame']
    require(len(entered)==2,'native scene entry evidence missing')
    for n,scene in enumerate(('Vss_District00','Vss_Yagara')):
        status=entered[n]['status']
        require(status['generation']==n and len(status['players'])==2,'native generation mismatch')
        require(all(p['scene']==scene and p['last_match_phase']=='ingame' for p in status['players']),'actual native map/phase mismatch')
        require([p['pid'] for p in status['players']]==c['matches'][n]['host_pids'],'native scene PID mismatch')


def audit(baseline,regression,continuous):
    b=read(baseline);r=read(regression);plan=read(Path(regression).parent/'plan.json')
    require(b['passed'] and not b['errors'],'reproducibility failed')
    require(r['passed'] and not r['errors'],'final regressions failed')
    require(r['host_sha256']==b['runtime_identity']['host_sha256'],'baseline/regression host mismatch')
    current(b['runtime_identity']['runtime_sha256'])
    for route in ('menu','native'):
        trials=[t for t in b['trials'] if t['route']==route]
        require(len(trials)>=3,'three trials required: '+route)
        for trial in trials:require(sha(trial['result'])==trial['sha256'],'trial changed')
    require(all(all(d<=upper+1e-6 for d,upper in zip(pair['difference_pp'],b['noise_upper_pp'])) for pair in b['cross_pairs']),
            'a cross-route pair exceeds measured own-scatter bound')
    expected={j['name'] for j in plan['jobs']}|{'a4'}
    require(set(r['jobs'])==expected,'regression job set incomplete')
    jobs={}
    for name,job in r['jobs'].items():
        require(job['passed'] and job['exit_code']==0,'failed job '+name)
        if 'record' in job:
            require(sha(job['record'])==job['record_sha256'],'job record changed '+name)
            bound=read(job['record']);require(bound['passed'] and not bound['errors'],'invalid bound job '+name)
            if name=='a6-special':
                build=bound['build'];parent=build.get('production_parent',{})
                require(build.get('test_only') and build.get('test_feature')=='special_meter' and parent.get('sha256')==r['host_sha256'],'special host must derive from final production host')
                require(sha(ROOT/parent['path'])==parent['sha256'],'special parent changed')
                production=read((ROOT/parent['path']).with_suffix('.build.json'))
                require(all(build['source_sha256'].get(p)==d for p,d in production['source_sha256'].items()),'special derivative sources differ')
                require('-DSPL3_A6_TEST_SPECIAL=1' in build['command'],'special derivative lacks compile feature')
                commands=[]
                for cmd in (production['command'],build['command']):
                    cmd=list(cmd);cmd[cmd.index('-o')+1]='<OUTPUT>'
                    commands.append([v for v in cmd if v!='-DSPL3_A6_TEST_SPECIAL=1'])
                require(commands[0]==commands[1],'special derivative changed other build flags')
                require(bound['host_sha256']==build['output_sha256'],'special derivative identity mismatch')
            else:require(bound['host_sha256']==r['host_sha256'],'job host mismatch '+name)
            current(bound['runtime_sha256'])
            for evidence in bound['evidence']:require(sha(evidence['path'])==evidence['sha256'],'native evidence changed '+name)
        jobs[name]=job
    c=read(continuous);audit_continuous(c,r['host_sha256'])
    require(r['jobs']['a5']['continuous_same_pids'],'final continuous startup missing')
    a5=read(r['jobs']['a5']['evidence']);require(sha(r['jobs']['a5']['evidence'])==r['jobs']['a5']['evidence_sha256'],'A5 changed')
    require(a5['statistics']['valid_games']==2,'two fresh swapped games missing')
    require(all(m.get('native_winners') and not m.get('void') for m in a5['matches'] if m.get('passed')),'fresh A5 must reach paired native Winners')
    historical=read(r['a5_historical_audit']['path'])
    require(r['a5_historical_audit']['exit_code']==0 and historical['accepted'] and historical['valid_rounds']==70,'historical 70 audit missing')
    require(r['a6_independent_card_audit'],'independent A6 trace audit missing')
    require(r['jobs']['a6-timing']['thresholds']=={'standing-charge':21,'surface-charge':26},'A6 timing changed')
    roll_job=read(r['jobs']['a6-roll']['record']);require(len(roll_job['evidence'])==1,'fresh roll evidence ambiguous')
    roll_source=Path(roll_job['evidence'][0]['path']);calibration=roll_source.with_name('roll-calibration.json')
    from a6_motion import calibrate_roll
    require(read(calibration)==calibrate_roll(roll_source) and read(calibration)['passed'],'fresh closed roll calibration changed')
    revision=ROOT/'work/a7/fixture-revision-proof.json'
    if revision.exists():
        proof=read(revision);snapshot=Path(proof['snapshot'])
        require(sha(snapshot)==proof['sha256'],'tested fixture snapshot changed')
        def body(text,name):return ast.dump(next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name),include_attributes=False)
        for name in ('combat','combo_bomb','aim_surge'):
            bound=read(r['jobs']['a6-'+name]['record'])
            require(bound['fixture_sha256']==proof['sha256'] or bound['fixture_sha256']==sha(ROOT/'tests/probe_a6_regression.py'),'unknown fixture revision')
            require(body(snapshot.read_text(),name)==body((ROOT/'tests/probe_a6_regression.py').read_text(),name),'completed operation controller changed '+name)
    cards={}
    for name in ('reference','alpha','bravo'):
        path=Path(regression).parent/('card-'+name+'-scorecard.json');card=read(path)
        require(card['measured']==card['total']==13,'thirteen native trials required '+name)
        cards[name]=dict(**reference(path),policy_source_sha256=card['source_sha256'],measured=card['measured'],total=card['total'],aggregate_score=card['aggregate_score'],lateral_window_hits=card['lateral_window_hits'],lateral_window_trials=card['lateral_window_trials'],approach_downs=card['approach_downs'],approach_trials=card['approach_trials'])
    host=Path(plan['host']);build=read(host.with_suffix('.build.json'))
    require(sha(ROOT/'upstream/dm/host/dmhost')==build['default_sha256'] and build['default_unchanged'],'default host changed')
    for path,digest in build['source_sha256'].items():require(sha(ROOT/path)==digest,'host source changed '+path)
    phases={route:{key:statistics.mean(t['phase_wall_seconds'][key] for t in b['trials'] if t['route']==route)
        for key in ('boot','room','loading','controlled','settlement','cleanup')} for route in ('menu','native')}
    return dict(schema='arena.a7.acceptance.v1',passed=True,full_a7_passed=True,
        score_criterion=b['criterion'],noise_upper_pp=b['noise_upper_pp'],mean_difference_pp=b['mean_difference_pp'],
        maximum_cross_difference_pp=b['maximum_cross_difference_pp'],all_cross_pairs_within_noise=True,
        scores_by_route={k:v['scores'] for k,v in b['within'].items()},outcomes=b['outcomes'],
        baseline=reference(baseline),regression=reference(regression),cross_map_continuous=reference(continuous),regression_plan=reference(Path(regression).parent/'plan.json'),
        historical_a5=reference(r['a5_historical_audit']['path']),scorecards=cards,jobs=jobs,
        cross_map_startup_seconds=[next(e['wall'] for e in c['events'] if e['round']==n and e['phase']=='ingame')-next(e['wall'] for e in c['events'] if e['round']==n and e['phase']=='startup') for n in (0,1)],
        cross_map_match_wall_seconds=[m['wall_seconds'] for m in c['matches']],
        auditor=reference(__file__),
        roll_calibration=reference(calibration),fixture_revision_proof=reference(revision) if revision.exists() else None,
        host_build=build,phase_wall_mean_seconds=phases,
        controlled_fps_group_mean={route:statistics.mean(t['controlled_fps'] for t in b['trials'] if t['route']==route) for route in ('menu','native')},
        performance_scope='Three-worker mixed-route batch; overlap varies. Not an isolated GPU speedup.',
        interpretation='Empirical measured equivalence, not determinism or a confidence interval. A3b and accepted A6 unsupported operations remain unsupported.',
        a8_started=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--regression',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--continuous',type=Path,required=True)
    args=p.parse_args();result=audit(args.baseline,args.regression,args.continuous);write_json_atomic(args.out,result);print(args.out)
