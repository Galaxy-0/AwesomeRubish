"""Independent raw-input/native-lifecycle audit of the opt-in A6 test host."""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
FILL=re.compile(r'A6_TEST_SPECIAL_FILL frame=(\d+) slot=(\d+) mode=(\w+) count=(\d+) old_charge=([^ ]+) remaining=(\d+) cost=([^\s]+)')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_test_special(item,read_evidence):
    if item.get('status')!='verified' or 'native' not in item:
        raise AssertionError('A6 test-special full/infinite native validation is pending; core evidence passed')
    run=read_evidence(item['native'])
    if not run.get('passed') or not run.get('probe_completed') or not run.get('default_unchanged') or \
            run.get('test_special_modes')!={'player_0':'full','player_1':'infinite'}:
        raise AssertionError('test-special needs a completed full/infinite native room')
    build=read_evidence(run['test_host_build'])
    default=ROOT/'upstream/dm/host/dmhost';alt=ROOT/build['output']
    if alt.resolve()==default.resolve() or not build.get('test_only') or not build.get('default_unchanged') or \
            sha(default)!=build['default_sha256'] or sha(alt)!=build['output_sha256'] or \
            run['actual_host_sha256']!=build['output_sha256']:
        raise AssertionError('test-special host identity/default preservation failed')
    for name,digest in build['source_sha256'].items():
        if sha(ROOT/name)!=digest:raise AssertionError('native test-host source differs from delivered source')
    driver=ROOT/'tests/probe_a6_test_special.py'
    if run.get('code_sha256',{}).get(str(driver))!=sha(driver):
        raise AssertionError('native test-special driver changed')
    if [(x['mode'],x['actual_executable'],x['sha256']) for x in run['launches']]!=[
            (mode,build['output'],build['output_sha256']) for mode in ('full','infinite')]:
        raise AssertionError('test-only executable was not launched for both modes')
    directory=(ROOT/item['native']['path']).parent
    trace=directory/'steps.jsonl';attachments=item['native'].get('attachments_sha256',{})
    if str(trace.relative_to(ROOT)) not in attachments:
        raise AssertionError('test-special raw steps hash missing')
    steps=[json.loads(line) for line in trace.read_text().splitlines()]
    by_label={}
    for step in steps:
        by_label.setdefault(step['label'],[]).append(step)
        for n in (0,1):
            action=step['actions'][f'player_{n}'];expected=[0]*6
            if step['label']=='special-1-press' or step['label']=='special-2-press' and n==1:
                expected[3]=1
            if action['buttons']!=expected or any(action['sticks']) or any(action['gyro']):
                raise AssertionError('test-special proof contains painting, movement or extra input')
    for label in ('special-1-press','special-2-press'):
        rows=by_label.get(label,[])
        if len(rows)!=1 or rows[0]['frames']!=1:
            raise AssertionError('test-special RS must be a single actual present')
    cases=run['cases']
    for kind,values in (('initial-full-idle',(1.,1.)),('after-first-idle',(0.,1.)),('after-second-idle',(0.,1.))):
        case=next(c for c in cases if c['kind']==kind);rows=by_label.get(kind,[])
        if sum(x['frames'] for x in rows)<90 or [x['infos'] for x in rows]!=[x['infos'] for x in case['history']]:
            raise AssertionError('test-special stable idle lacks 90 raw native presents')
        for row in rows:
            for n,value in enumerate(values):
                info=row['infos'][f'player_{n}']
                if not info['alive'] or not info['special_valid'] or abs(info['special']-value)>.001:
                    raise AssertionError('test-special full/infinite idle mismatch')
    cycles=sorted((c for c in cases if c['kind']=='special-cycle'),key=lambda c:c['number'])
    if len(cycles)!=2 or [c['players'] for c in cycles]!=[[0,1],[1]]:
        raise AssertionError('test-special needs first use in both modes and a second infinite use')
    for number,case in enumerate(cycles,1):
        rows=by_label[f'special-{number}-press']+by_label[f'special-{number}-active']
        if [x['infos'] for x in rows]!=[x['infos'] for x in case['history']]:
            raise AssertionError('test-special lifecycle differs from actual raw STEP feedback')
        for n in case['players']:
            p=f'player_{n}';before=case['before'][p];samples=[x['infos'][p] for x in rows]
            values=[i['special'] for i in samples]
            if before['special']!=1. or not before['special_valid'] or \
                    not all(i['special_valid'] and i['alive'] and i['hp_valid'] and i['hp']>=.999 for i in samples) or \
                    min(values)>.04 or len({v for v in values if .05<v<.95})<20 or \
                    samples[-1]['frame']-before['frame']<450:
                raise AssertionError('test-special lacks gradual native activation/consumption/end')
        if case['after']['player_0']['special']!=0. or case['after']['player_1']['special']!=1.:
            raise AssertionError('test-special modes did not diverge after native use')
        if number==2 and any(x['infos']['player_0']['special']!=0. for x in rows):
            raise AssertionError('full mode unexpectedly refilled')
    session=Path(run['session'])
    for n,mode,count in ((0,'full',1),(1,'infinite',3)):
        host_log=session/f'player-{n}/host.log';input_path=session/f'player-{n}/input.json'
        for path in (host_log,input_path):
            if str(path.relative_to(ROOT)) not in attachments:
                raise AssertionError('native test-special launch/log hash missing')
        if json.loads(input_path.read_text()).get('DM_TEST_SPECIAL')!=mode:
            raise AssertionError('native test-special mode was not supplied at launch')
        rows=FILL.findall(host_log.read_text(errors='replace'))
        if rows!=[tuple(x) for x in run['host_fills'][f'player_{n}']] or len(rows)!=count:
            raise AssertionError('test-special native fill count differs')
        slot=cycles[0]['before'][f'player_{n}']['self_slot']
        if any(int(r[1])!=slot or r[2]!=mode or int(r[3])!=i+1 or abs(float(r[4]))>.02 or \
               int(r[5])!=0 or float(r[6])!=210. for i,r in enumerate(rows)):
            raise AssertionError('test-special filled during activation or used a wrong own slot/cost')
    return dict(modes=['full','infinite'],one_room=True,painting_inputs=0,
                full_native_uses=1,infinite_native_uses=2,full_fills=1,infinite_fills=3,
                idle_presents=90,default_unchanged=True)
