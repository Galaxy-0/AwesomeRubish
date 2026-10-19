"""Native 1v1 tournament coordinator. Policies get only filtered stdio JSON."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import datetime
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import sys
import time
import threading
import traceback
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'arena/lib'))
from atlas import MapAtlas
from skills import neutral
from rl import NativeParallelEnv
from arena.config import PolicySpec
from arena.hud_events import HudEvents
from arena.process import PolicyProcess
from arena.referee_api import RefereeAPI
from arena.policy import encode_policy
from arena.statistics import tournament_statistics,meets_a5_threshold
from arena.schedule import schedule,overlap_windows
from arena.scoring import compare_scores,SCORING_RULE
from arena.checkpoint import load_resume,relative,sha256

_STOP=None

def write_json_atomic(path, data):
    """Persist a complete checkpoint before replacing the previous version."""
    path=Path(path);temporary=path.with_name(path.name+'.tmp')
    with temporary.open('w') as stream:
        json.dump(data,stream,indent=2)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)

def initialize_worker(stop):
    global _STOP
    _STOP=stop


def link_load_slots(session,shared):
    """Keep activation per room while sharing M5's two flock inodes."""
    local=session.out/'load-slots';shared=Path(shared)
    if (local/'active').exists():raise RuntimeError('shared load slots configured after activation')
    for n in range(2):
        target=(shared/f'slot-{n}').resolve()
        if not target.is_file():raise RuntimeError('missing shared loader slot')
        link=local/f'slot-{n}'
        if link.is_symlink():
            if link.resolve()!=target:raise RuntimeError('wrong shared loader slot')
        elif link.exists():raise RuntimeError('unshared loader slot already opened')
        else:link.symlink_to(target)


def abort_on_cancel(env,stop,finished,shared_slots=None,slot_errors=None,slots_ready=None):
    """Configure slots before map loading; cancel this worker's owned PIDs."""
    configured=None
    while not finished.wait(.05):
        session=env.session
        if session is None:continue
        if shared_slots is not None and configured is not session:
            configured=session
            try:
                link_load_slots(session,shared_slots)
                if slots_ready:slots_ready.set()
            except BaseException as error:
                if slot_errors is not None:slot_errors.append(repr(error))
                if stop is not None:stop.set()
        if stop is None or not stop.is_set():continue
        processes=[p for _,p,_ in list(session.hosts)]
        if session.air is not None:processes.append(session.air)
        for process in processes:
            if process.poll() is None:
                try:process.terminate()
                except ProcessLookupError:pass


def run_match(task):
    out=Path(task['out']);out.mkdir(parents=True)
    started=time.time()
    result=dict(round=task['round'],attempt=task.get('attempt',0),stage=task['stage'],passed=False,void=False,errors=[],artifacts=str(out),
                role_to_policy=task['roles'],screenshot_resolution=[128,72],paint=None,knockdowns=None)
    specs=[PolicySpec.load(path) for path in task['policy_paths']]
    roles=[specs[i] for i in task['roles']];atlas=MapAtlas.load(task['stage']);env=None;children=[];frame=0
    finished=threading.Event();cancel_thread=None;slots_ready=threading.Event();slot_errors=[]
    worker_stop=_STOP if _STOP is not None else threading.Event()
    if task.get("shared_load_slots") is None:slots_ready.set()
    native_trace=(out/'native-barriers.jsonl').open('w');inputs=(out/'inputs-per-present.jsonl').open('w')
    policy_traces=[(out/f'policy-{slot}.jsonl').open('w') for slot in (0,1)]
    try:
        if _STOP is not None and _STOP.is_set():raise InterruptedError('tournament cancelled before startup')
        env=NativeParallelEnv(players=2,mode=0,stage_id=task['stage'],weapons=[8000,8000],loadouts=[s.loadout for s in roles],
                              frame_skip=math.gcd(*(s.step_frames for s in roles)),reward_fn=None,timeout=task['timeout'],step_timeout=150)
        cancel_thread=threading.Thread(target=abort_on_cancel,args=(env,worker_stop,finished,task.get('shared_load_slots'),slot_errors,slots_ready),daemon=True);cancel_thread.start()
        _,initial=env.reset(seed=137+task['round']);result['session']=str(env.session.out)
        if slot_errors or not slots_ready.is_set():raise RuntimeError('shared loader slots were not ready: '+repr(slot_errors))
        result['shared_load_slots']=task.get('shared_load_slots')
        result['controlled_start_wall']=time.time();result['host_pids']=[p.pid for _,p,_ in env.session.hosts]
        origins={a:i['frame'] for a,i in initial.items()};agents=env.possible_agents
        events=HudEvents(initial,atlas);api=RefereeAPI(out.name,initial,dict.fromkeys(agents,8000),dict(zip(agents,(0,1))),
              ROOT/f"work/arena/maps/{atlas.data['name']}/sight.npz",stage_id=task['stage'],
              splash_suppressed=[a for a,s in zip(agents,roles) if s.loadout['clothes']['main']=='ninja_squid'])
        api.update(initial)
        for n,s in enumerate(roles):children.append(PolicyProcess(s.root,out/f'policy-{n}.stderr.log',timeout=s.step_timeout))
        held={a:neutral() for a in agents};settling=False;last_capture=-600
        while env.agents:
            if _STOP is not None and _STOP.is_set():raise InterruptedError('tournament cancelled')
            if not settling:
                for n,agent in enumerate(agents):
                    if frame%roles[n].step_frames==0:
                        observation=api.policy_observation(agent);held[agent]=children[n].act(observation)
                        policy_traces[n].write(json.dumps(dict(observation=json.loads(encode_policy(observation)),action=held[agent]))+'\n')
                        policy_traces[n].flush()
            actions={a:(neutral() if settling else held[a]) for a in env.agents}
            native_actions={a:{k:np.asarray(v,dtype=np.int8 if k=='buttons' else np.float32) for k,v in action.items()} for a,action in actions.items()}
            previous=frame;_,_,_,truncated,_=env.step(native_actions)
            if any(truncated.values()):raise TimeoutError('native tournament deadline')
            infos=env.process_infos;frame=infos[agents[0]]['frame']-origins[agents[0]]
            if any(i['frame']-origins[a]!=frame for a,i in infos.items()):raise AssertionError('native match barrier mismatch')
            for tick in range(previous,frame):
                inputs.write(json.dumps(dict(frame_interval=[tick,tick+1],actions={a:actions.get(a,neutral()) for a in agents}))+'\n')
            result['last_progress_wall']=time.time()
            inputs.flush();native_trace.write(json.dumps(dict(frame=frame,wall_time=result['last_progress_wall'],infos=infos))+'\n');native_trace.flush()
            before=len(events.events);events.update(infos,frame)
            if len(events.events)>before or frame-last_capture>=600:
                for agent,o in env.observations.items():Image.fromarray(o['pixels']).save(out/f'frame-{frame}-{agent}.png')
                last_capture=frame
            if all(i['phase']==1 for i in infos.values()) and not settling:api.update(infos)
            else:settling=True
        for child in children:child.close()
        for _ in range(120):
            if all(i['phase']==3 for i in env.process_infos.values()):break
            if _STOP is not None and _STOP.is_set():raise InterruptedError('tournament cancelled during settlement')
            previous=frame;env.advance_settlement()
            if env.timed_out:raise TimeoutError('native settlement deadline')
            infos=env.process_infos;frame=infos[agents[0]]['frame']-origins[agents[0]]
            for tick in range(previous,frame):inputs.write(json.dumps(dict(frame_interval=[tick,tick+1],actions={a:neutral() for a in agents},settlement=True))+'\n')
            result['last_progress_wall']=time.time()
            inputs.flush();events.update(infos,frame);native_trace.write(json.dumps(dict(frame=frame,wall_time=result['last_progress_wall'],infos=infos,settlement=True))+'\n');native_trace.flush()
        final=env.process_infos
        if not all(i['phase']==3 and i['score_valid'] and i['turf_valid'] and i['score_units']==1 for i in final.values()):raise AssertionError('native Winners/final Turf scores unavailable')
        result.update(compare_scores(final[agents[0]]['score'],final[agents[1]]['score'],task['roles']))
        result.update(hud_by_role={a:events.summary(a,agents[1-n]) for n,a in enumerate(agents)},
                      frames=frame,native_winners=True,source_hashes=[s.source_sha256 for s in specs])
        if any(v['enemy_hud_downs'] is None or v['own_hud_downs'] is None for v in result['hud_by_role'].values()):raise AssertionError('HUD event counters unavailable')
        (out/'hud-events.json').write_text(json.dumps(events.events,indent=2)+'\n')
        for agent,o in env.observations.items():Image.fromarray(o['pixels']).save(out/f'winners-{agent}.png')
        result['controlled_end_wall']=time.time();result['passed']=not result['void']
    except BaseException as error:
        result['errors'].append(repr(error));result['traceback']=traceback.format_exc()
        result['cancelled']=worker_stop.is_set()
        if slot_errors:result['slot_link_errors']=slot_errors
    finally:
        if env is not None and env.artifacts:
            result['sessions_created']=[str(p) for p in env.artifacts]
            result.setdefault('session',str(env.artifacts[-1]))
        # Preserve the real watchdog evidence, never turn an arbitrary policy or
        # integrity error into a void. Remaining peers are owned by this room.
        stalls=[]
        for session in result.get('sessions_created',[]):
            for log in Path(session).glob('player-*/host.log'):
                for line in log.read_text(errors='replace').splitlines():
                    if 'FATAL RL_STALL no present progress' in line:stalls.append(dict(log=str(log),line=line))
        if stalls and not result.get('cancelled'):
            result.update(void=True,void_reason='native_progress_watchdog',watchdog_evidence=stalls)
        finished.set()
        if cancel_thread:cancel_thread.join(1)
        for child in children:child.close()
        if env is not None:
            try:env.close()
            except BaseException as error:result['passed']=False;result['errors'].append('cleanup: '+repr(error))
        for stream in [native_trace,inputs,*policy_traces]:stream.close()
    result['wall_seconds']=time.time()-started
    if result.get('controlled_start_wall'):
        result['controlled_seconds']=result.get('controlled_end_wall',time.time())-result['controlled_start_wall']
    write_json_atomic(out/'result.json',result)
    return result


def concurrency_window(matches):
    start=max(m['controlled_start_wall'] for m in matches)
    end=min(m['controlled_end_wall'] for m in matches)
    pids=[pid for m in matches for pid in m['host_pids']]
    if end<=start or len(set(pids))!=2*len(matches):
        raise AssertionError('native rooms did not overlap with distinct host processes')
    return dict(rounds=sorted(m['round'] for m in matches),rooms=len(matches),hosts=len(pids),
                host_pids=pids,start_wall=start,end_wall=end,overlap_seconds=end-start)


def tournament(policy_a,policy_b,games=70,parallel=4,timeout=7200,out=None,early_rate_check=False,resume=None):
    if type(games) is not int or games<2 or games%2:raise ValueError('an even number of games is required for swapped pairs')
    if parallel not in (1,2,3,4):raise ValueError('parallel games must be 1, 2, 3 or 4')
    specs=[PolicySpec.load(policy_a),PolicySpec.load(policy_b)]
    if specs[0].name==specs[1].name:raise ValueError('policy names must differ')
    prior=load_resume(resume,specs,games) if resume is not None else {}
    initial=prior.get('matches',[]);valid_rounds={m['round'] for m in initial if m.get('passed')}
    out=Path(out) if out is not None else ROOT/'work/arena'/datetime.datetime.now().strftime('tournament-%Y%m%d-%H%M%S-%f')
    out=out.resolve()
    if not out.is_relative_to(ROOT/'work'):raise ValueError('game records must stay under ignored work/')
    out.mkdir(parents=True,exist_ok=True)
    shared_slots=out/'load-slots-shared';shared_slots.mkdir()
    for n in range(2):(shared_slots/f'slot-{n}').touch()
    started=time.time()
    result=dict(passed=False,full_a5_passed=False,scoring_rule=SCORING_RULE,games_requested=games,parallel_games=parallel,
                global_loader_slots=2,policies=[s.name for s in specs],source_hashes=[s.source_sha256 for s in specs],matches=[],concurrency_windows=[],errors=[],artifacts=str(out),started_wall=started,
                first_started_wall=prior.get('first_started_wall',prior.get('started_wall',started)),
                evidence_sha256=prior.get('evidence_sha256',{}),immutable_runtime_sha256=prior.get('immutable_runtime_sha256',{}),
                excluded_attempts=prior.get('excluded_attempts',[]))
    if resume is not None:
        result['resumed_from']=dict(checkpoint=relative(resume),sha256=sha256(resume),valid_rounds=sorted(valid_rounds),
                                    prior_elapsed_wall_seconds=prior.get('elapsed_wall_seconds',0))
    runtime=[ROOT/'upstream/dm/host/dmhost']+list((ROOT/'arena').rglob('*.py'))+list((ROOT/'rl').glob('*.py'))
    runtime += [ROOT/f'work/arena/maps/{name}/{filename}' for name in ('Yunohana','District00','Yagara') for filename in ('navigation.json','sight.npz')]
    frozen={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime}
    (out/'runtime-sha256.json').write_text(json.dumps(frozen,indent=2)+'\n')
    context=multiprocessing.get_context('spawn');stop=context.Event()
    tasks=[dict(round=n,stage=(n//2)%3+1,roles=[0,1] if n%2==0 else [1,0],policy_paths=[str(s.root) for s in specs],
                attempt=prior.get('next_attempt_by_round',{}).get(str(n),0),
                timeout=timeout,shared_load_slots=str(shared_slots)) for n in range(games) if n not in valid_rounds]
    def save(matches,reason):
        result['matches']=list(matches);result['stop_reason']=reason
        result['statistics']=tournament_statistics(matches)
        result['concurrency_windows']=overlap_windows(matches,parallel)
        result['segment_concurrency_windows']=overlap_windows(matches[len(initial):],parallel)
        result['segment_elapsed_wall_seconds']=time.time()-started
        result['elapsed_wall_seconds']=prior.get('elapsed_wall_seconds',0)+result['segment_elapsed_wall_seconds']
        result['next_attempt_by_round']={str(n):max(prior.get('next_attempt_by_round',{}).get(str(n),0),
            max([m.get('attempt',0)+1 for m in matches if m['round']==n],default=0)) for n in range(games)}
        checkpoints=out/'checkpoints';checkpoints.mkdir(exist_ok=True)
        write_json_atomic(checkpoints/f'after-attempt-{len(matches):03d}.json',result)
        write_json_atomic(out/'result.json',result)
        print(json.dumps(dict(valid=result['statistics']['valid_games'],void=result['statistics']['void_games'],requested=games,attempts=len(matches),stop_reason=reason)),flush=True)
    save(initial,None)
    try:
        with ProcessPoolExecutor(max_workers=parallel,mp_context=context,initializer=initialize_worker,initargs=(stop,)) as pool:
            def submit(task):
                task=dict(task,out=str(out/f"round-{task['round']:03d}-attempt-{task['attempt']:03d}"))
                return pool.submit(run_match,task)
            try:
                matches,reason=schedule(tasks,submit,stop,save,parallel,max(3,games//9),early_rate_check,initial)
            except BaseException:
                stop.set();raise
        if [PolicySpec.load(s.root).source_sha256 for s in specs]!=result['source_hashes']:raise AssertionError('policy source changed during tournament')
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=sha for p,sha in frozen.items()):raise AssertionError('arena runtime changed during tournament')
        stats=result['statistics']
        result['matches'].sort(key=lambda m:(m['round'],m['attempt']))
        if reason:result['errors'].append(reason)
        result['passed']=stats['valid_games']==games and not result['errors'] and stats['failed_or_cancelled']==0 and bool(result['segment_concurrency_windows'] or not tasks)
        result['full_a5_passed']=result['passed'] and meets_a5_threshold(stats['valid_games'],stats['void_games'],parallel)
    except BaseException as error:stop.set();result['errors'].append(repr(error))
    result['segment_elapsed_wall_seconds']=time.time()-started
    result['elapsed_wall_seconds']=prior.get('elapsed_wall_seconds',0)+result['segment_elapsed_wall_seconds']
    write_json_atomic(out/'result.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--policy-a',type=Path,default=ROOT/'arena/policies/rush')
    p.add_argument('--policy-b',type=Path,default=ROOT/'arena/policies/high-ground');p.add_argument('--games',type=int,default=70)
    p.add_argument('--parallel',type=int,choices=(1,2,3,4),default=4);p.add_argument('--timeout',type=float,default=7200)
    p.add_argument('--resume',type=Path)
    args=p.parse_args();report=tournament(args.policy_a,args.policy_b,args.games,args.parallel,args.timeout,resume=args.resume)
    print(json.dumps({k:v for k,v in report.items() if k!='matches'},indent=2));raise SystemExit(0 if report['passed'] else 1)
