"""Three-map T1 BO3, preserving A5 scoring, void classification and ownership."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import math
import multiprocessing
import os
from pathlib import Path
import time

from .config import PolicySpec
from .proficiency import report_cards
from .runner import ROOT,initialize_worker,run_match,write_json_atomic
from .schedule import schedule,overlap_windows
from .scoring import SCORING_RULE
from .statistics import tournament_statistics
from .versions import snapshot_policy,loader_slots
from .native_runtime import runtime_files

STAGES={1:'Yunohana',2:'District00',3:'Yagara'}
DEFAULT_SLOTS=ROOT/'work/arena/t1-load-slots'


def fixtures(number):
    if type(number) is not int or number<0:raise ValueError('round must be a nonnegative integer')
    roles=[0,1] if number%2==0 else [1,0]
    return [dict(round=n,t1_round=number,stage=stage,roles=list(roles),attempt=0)
            for n,stage in enumerate(STAGES)]


def summarize(report):
    valid={m['round']:m for m in report['matches'] if m.get('passed')}
    wins={'a':0,'b':0,'draw':0};games=[]
    for fixture in fixtures(report['round']):
        match=valid.get(fixture['round']);game=dict(fixture=fixture['round'],stage=fixture['stage'],
            map=STAGES[fixture['stage']],role_to_policy=fixture['roles'],winner=None)
        if match:
            outcome=match['outcome'];wins[outcome]+=1
            game.update(winner=outcome,winner_name=report['policies'][0 if outcome=='a' else 1] if outcome!='draw' else None,
                        score_by_role=match['score_by_role'],
                        score_by_policy={label:match['score_by_role'][match['role_to_policy'].index(n)] for n,label in enumerate(('a','b'))},
                        hud_by_policy={label:match['hud_by_role'][f"player_{match['role_to_policy'].index(n)}"] for n,label in enumerate(('a','b'))},
                        suspect=match.get('suspect',False),attempt=match.get('attempt',0),artifacts=match['artifacts'])
        games.append(game)
    complete=len(valid)==3
    winner=None if not complete else 'a' if wins['a']>wins['b'] else 'b' if wins['b']>wins['a'] else 'draw'
    return dict(schema='arena.t1.summary.v1',round=report['round'],policies=report['policies'],
                source_hashes=report['source_hashes'],passed=report['passed'],complete=complete,games=games,wins=wins,
                round_winner=winner,round_winner_name=report['policies'][0 if winner=='a' else 1] if winner in ('a','b') else None,
                void_attempts=sum(bool(m.get('void')) for m in report['matches']),errors=report['errors'])


def runtime_hashes(native_runtime=None):
    # Author policy trees intentionally excluded; only the captured revision is
    # used. Adding new policy versions must not invalidate a running round.
    paths=[ROOT/'upstream/dm/host/dmhost']
    paths+=runtime_files(native_runtime)
    paths+=list((ROOT/'arena').glob('*.py'))+list((ROOT/'arena/lib').glob('*.py'))+list((ROOT/'rl').glob('*.py'))
    paths+=[ROOT/'tests/t1_round.py']
    paths+=[ROOT/f'work/arena/maps/{name}/{filename}' for name in STAGES.values() for filename in ('navigation.json','sight.npz')]
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run_round(policy_a,policy_b,number,out,timeout=7200,shared_slots=DEFAULT_SLOTS,native_runtime=None):
    tasks=fixtures(number)
    if os.environ.get('DM_TEST_SPECIAL'):raise ValueError('DM_TEST_SPECIAL is forbidden in arena/T1 matches')
    if not math.isfinite(timeout) or timeout<=0:raise ValueError('timeout must be positive and finite')
    out=Path(out).resolve()
    if not out.is_relative_to(ROOT/'work'):raise ValueError('raw game records must stay under ignored work/')
    out.mkdir(parents=True,exist_ok=False)
    specs=[snapshot_policy(path,out/'policies'/label) for path,label in ((policy_a,'a'),(policy_b,'b'))]
    if specs[0].name==specs[1].name:raise ValueError('policy names must differ')
    shared=loader_slots(shared_slots);profiles=report_cards(specs,native_runtime=native_runtime);frozen=runtime_hashes(native_runtime)
    write_json_atomic(out/'runtime-sha256.json',frozen)
    report=dict(schema='arena.t1.round.v1',round=number,passed=False,full_a5_passed=False,
        scoring_rule=SCORING_RULE,games_requested=3,parallel_games=3,global_loader_slots=2,
        policies=[s.name for s in specs],source_hashes=[s.source_sha256 for s in specs],
        policy_snapshots=[str(s.root) for s in specs],policy_sources=[str(Path(p).resolve()) for p in (policy_a,policy_b)],
        shared_load_slots=str(shared),matches=[],errors=[],started_wall=time.time(),artifacts=str(out),
        proficiency_by_policy=profiles,native_runtime=native_runtime)
    context=multiprocessing.get_context('spawn');stop=context.Event()

    def save(matches,reason):
        report['matches']=sorted(matches,key=lambda m:(m['round'],m.get('attempt',0)))
        report['statistics']=tournament_statistics(matches);report['stop_reason']=reason
        report['concurrency_windows']=overlap_windows(matches,3)
        report['elapsed_wall_seconds']=time.time()-report['started_wall']
        write_json_atomic(out/'result.json',report);write_json_atomic(out/'summary.json',summarize(report))

    save([],None)
    try:
        for task in tasks:
            task.update(policy_paths=[str(s.root) for s in specs],timeout=timeout,
                        shared_load_slots=str(shared),proficiency_by_policy=profiles,native_runtime=native_runtime)
        with ProcessPoolExecutor(max_workers=3,mp_context=context,initializer=initialize_worker,initargs=(stop,)) as pool:
            def submit(task):
                return pool.submit(run_match,dict(task,out=str(out/f"game-{task['round']}-attempt-{task['attempt']:03d}")))
            try:
                matches,reason=schedule(tasks,submit,stop,save,3,math.inf)
            except BaseException:
                stop.set();raise
        if reason:report['errors'].append(reason)
        if [PolicySpec.load(s.root).source_sha256 for s in specs]!=report['source_hashes']:
            raise AssertionError('captured policy source changed')
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h for p,h in frozen.items()):
            raise AssertionError('arena runtime changed during round')
        if not report['concurrency_windows']:raise AssertionError('three native rooms did not overlap')
        report['passed']=report['statistics']['valid_games']==3 and not report['errors'] and report['statistics']['failed_or_cancelled']==0
    except BaseException as error:
        stop.set();report['errors'].append(repr(error))
    save(report['matches'],report.get('stop_reason'))
    return report
