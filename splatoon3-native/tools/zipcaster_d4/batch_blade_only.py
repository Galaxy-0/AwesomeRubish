"""Prospective native cohort, at most3 fresh rooms and no combat resampling.

Closed unchanged-input cases may be reused only with an identical dependency
manifest. A failure beforeRS gets one retry; an aborted battle stops launches.
Two failed positive predictions in the same state trigger a diagnostic stop.
"""
import argparse
from collections import deque
from concurrent.futures import FIRST_COMPLETED,ThreadPoolExecutor,wait
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha
from tools.zipcaster_d4.report_duel import reduce


def atomic(path,data):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,indent=2)+'\n')
    tmp.replace(path)


def dependencies(plan,host):
    names='batch_blade_only.py duel_blade_only.py report_duel.py model_v3.py model_v2.py flight_v2.py geometry.py geometry.cpp attack_model_v3.py attack_model_v5.py attack_cache.py attack_batch_v2.py attack_geometry.py attack_sequence_v2.py contact_shape.py point_prediction_blade_only.py model_blade_only.py blade_only.py attack_model_safe.py attack_batch_safe.py optimistic_blade_only.py attack_probe_v4.py recoil.py zero_probe_v4.py'.split()
    files=[Path(__file__).with_name(n)for n in names]
    files += [ROOT/p for p in [
        'tools/zipcaster_d3r/control.py','tools/zipcaster_d3r/weapon_aim.py',
        'tools/zipcaster_d3r/aim_solver.py','tools/zipcaster_d3r/setup_navigation.py',
        'tools/zipcaster_d3r/native_kinematics.py','tools/zipcaster_d3/native.py',
        'tools/zipcaster/validate_candidates.py','tools/zipcaster/surfaces.py',
        'tools/stage_collision.py','tests/a6_lab.py','arena/lib/atlas.py',
        'arena/geometry.py','arena/referee_api.py','arena/native_runtime.py',
        'work/d4/restart-v3/attack-fit-v1.json','work/d4/restart-v3/recoil-fit-v2.json',
        'work/a6/parameters.json','work/d3r/attack-parameters-v1.json','work/d3r/ray-v2-frozen.json']]
    files += list((ROOT/'rl').glob('*.py'))+[plan,host.with_suffix('.build.json')]
    assert all(p.is_file()for p in files)
    return sorted(set(p.resolve()for p in files))


def main(a):
    a.out=a.out.resolve();a.plan=a.plan.resolve();a.host=a.host.resolve()
    if a.out.exists():raise ValueError('fresh output directory required')
    # Foreign matches are never stopped or co-scheduled beyond the room cap.
    ps=subprocess.check_output(['ps','-axo','comm='],text=True)
    if any(Path(p.strip()).name.startswith('dmhost')for p in ps.splitlines()):
        raise RuntimeError('existing game hosts present; no process was stopped or new room launched')
    a.out.mkdir(parents=True);snapshot=a.out/'source';snapshot.mkdir()
    files=dependencies(a.plan,a.host)
    manifest={str(p):sha(p)for p in files}
    for i,p in enumerate(files):shutil.copy2(p,snapshot/f'{i}-{p.name}')
    atomic(a.out/'source-manifest.json',manifest)
    runtime=dict(host=str(a.host),sha256=sha(a.host),modules={p.name:sha(p)for p in(a.host.parent/'modules').iterdir()if p.is_file()})
    atomic(a.out/'runtime.json',runtime)
    plan=json.loads(a.plan.read_text());points=plan['points'];byid={p['id']:p for p in points}
    results=[];auxiliary=[];done=set();began=time.monotonic();stop_reason=None
    for previous in a.reuse:
        old=json.loads(previous.read_text())
        same_manifest=old.get('source_sha256')==manifest and old.get('runtime')==runtime
        for row in old['results']:
            if not row.get('artifact'):continue
            path=ROOT/row['artifact'];d=json.loads(path.read_text());p=d['point'];new=byid.get(p['id'])
            same=new is not None and all(new[k]==p[k]for k in ['graph','source','enemy','heading','speed','hooks','program'])
            if not same_manifest or not same or not row.get('eligible'):
                auxiliary.append(dict(artifact=row['artifact'],sha256=sha(path),reason='changed dependency/input or incomplete; retained outside cohort'))
                continue
            assert sha(path)==row['artifact_sha256'] and d['freeze_before']==d['freeze_after']
            key=(p['id'],d['repeat']);assert key not in done
            results.append(dict(row,reused=True));done.add(key)
    tasks=deque((p['id'],r,0)for r in range(a.repeats)for p in points if(p['id'],r)not in done)
    positive_failures={}

    def progress(pending):
        atomic(a.out/'batch.json',dict(schema='inklab.d4.blade-only.native.batch.v1',full_d4_passed=False,scope='Restricted feasible routes, no contact/global-optimum closure; old12 excluded',results=results,
            auxiliary=auxiliary,rooms=a.rooms,planned=len(points)*a.repeats,valid=len(done),
            pending=len(tasks)+len(pending),stop_reason=stop_reason,seconds=time.monotonic()-began,
            source_sha256=manifest,plan_sha256=sha(a.plan),runtime=runtime))

    def run(item):
        point,repeat,attempt=item
        log=a.out/f'{point}-r{repeat}-attempt{attempt}.log'
        command=[sys.executable,str(Path(__file__).with_name('duel_blade_only.py')),
                 '--plan',str(a.plan),'--point',point,'--repeat',str(repeat),'--host',str(a.host)]
        with log.open('w')as f:
            proc=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT,cwd=ROOT)
            atomic(log.with_suffix('.job.json'),dict(pid=proc.pid,command=command,started=time.time()))
            code=proc.wait()
        lines=log.read_text().splitlines()
        closed=[l for l in lines if l.startswith('D4_BLADE_ONLY_CLOSED ')]
        opened=[l for l in lines if l.startswith('D4_BLADE_ONLY_OPEN ')]
        path=Path((closed or opened)[-1].split(' ',1)[1])/'result.json'if(closed or opened)else None
        d=json.loads(path.read_text())if path and path.exists()else{}
        started=any(e['event']=='before-RS'for e in d.get('events',[]))
        eligible=bool(closed and d.get('calibration_eligible')and d.get('passed'))
        truth=reduce(path.resolve())if closed and 'freeze_after'in d else None
        return dict(point=point,repeat=repeat,attempt=attempt,exit_code=code,
            artifact=str(path.relative_to(ROOT))if path else None,artifact_sha256=sha(path)if path and path.exists()else None,
            eligible=eligible,combat_started=started,strict_budget_win=truth.get('strict_budget_win')if truth else None,
            enemy_down=truth.get('enemy_down')if truth else None,
            attacker_down=truth.get('attacker_down')if truth else None,
            counter_at_enemy_down=truth.get('counter_at_enemy_down')if truth else None,
            actual_pose_model=d.get('actual_pose_model'),outcome=d.get('outcome'),errors=d.get('errors'),reused=False)

    with ThreadPoolExecutor(max_workers=a.rooms)as pool:
        pending={};progress(pending)
        while tasks or pending:
            if(a.out/'STOP_LAUNCH').exists()and not stop_reason:
                stop_reason=(a.out/'STOP_LAUNCH').read_text().strip()or'operator stop'
            while tasks and len(pending)<a.rooms and not stop_reason:
                if any(sha(Path(p))!=h for p,h in manifest.items()):
                    stop_reason='dependency changed; no further launches';break
                item=tasks.popleft();pending[pool.submit(run,item)]=item
            if not pending:break
            finished,_=wait(pending,return_when=FIRST_COMPLETED)
            for future in finished:
                item=pending.pop(future);row=future.result();results.append(row)
                print('D4_BLADE_NATIVE_CASE '+json.dumps(row),flush=True)
                if row['eligible']:
                    done.add((item[0],item[1]));p=byid[item[0]]
                    if p['band']in ['top1','top2']and not row['strict_budget_win']:
                        key=(p['graph'],p['region']);positive_failures.setdefault(key,set()).add(p['band'])
                        if len(positive_failures[key])>=2:
                            stop_reason='Both positive starts failed in '+str(key)+'; inspect before remaining repeats'
                elif row['combat_started']:
                    stop_reason='Aborted/unresolved combat, never resampled as setup: '+item[0]
                elif item[2]<1:tasks.appendleft((item[0],item[1],item[2]+1))
                else:stop_reason='Two setup attempts failed: '+item[0]
                if stop_reason:(a.out/'STOP_LAUNCH').write_text(stop_reason+'\n')
            progress(pending)
    assert all(sha(Path(p))==h for p,h in manifest.items()),'frozen dependencies changed'
    assert sha(a.host)==runtime['sha256']
    assert {p.name:sha(p)for p in(a.host.parent/'modules').iterdir()if p.is_file()}==runtime['modules']
    progress({})
    print('D4_BLADE_NATIVE_CLOSED '+json.dumps(dict(valid=len(done),planned=len(points)*a.repeats,stop_reason=stop_reason)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--host',type=Path,default=ROOT/'work/d4/meter-v1/dmhost-aim')
    p.add_argument('--reuse',type=Path,nargs='*',default=[]);p.add_argument('--repeats',type=int,default=8)
    p.add_argument('--rooms',type=int,choices=[1,2,3],default=3);main(p.parse_args())
