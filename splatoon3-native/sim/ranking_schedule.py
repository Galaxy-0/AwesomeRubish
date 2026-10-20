"""Bounded two-CPU scheduling of the SAME registered sim.ranking.group kernel.

No policy, cadence, physics or scenario changes. Long groups are assigned first;
the next pending group goes to whichever CPU is free. An exclusive scheduler
lock prevents two copies of this entry point; do not run sim.ranking alongside.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import time

from arena.config import PolicySpec
from .parameters import ROOT,Parameters,sha256
from .ranking import Models,core_hashes,group,run
from .ranking_sources import WORK,PAIRS
from .terrain import Terrain

_CACHE={}


def pending(out,batch_size=6):
    plan=json.loads((out/'plan.json').read_text());source=json.loads((out/'sources.json').read_text())
    if sha256(out/'sources.json')!=plan['sources_sha256'] or core_hashes()!=plan['sim_source_sha256']:
        raise ValueError('experiment source/core binding differs')
    jobs=[]
    for stage in (1,2,3):
        plans=[p for p in plan['scenarios'] if p['stage']==stage]
        for pair in PAIRS:
            for offset in range(0,len(plans),batch_size):
                name=f'{pair}-map{stage}-batch{offset//batch_size:02}'
                expected=plans[offset:offset+batch_size];file=out/name/'result.json'
                if file.exists():
                    old=json.loads(file.read_text())
                    if (old['model_sha256']!=plan['model_sha256'] or old['sim_source_sha256']!=plan['sim_source_sha256']
                        or old['frames_per_game']!=plan['frames']
                        or old['policy_sha256']!=[source['policies'][n]['directory_sha256'] for n in PAIRS[pair]]
                        or [{k:g[k] for k in ('stage','swap','seed','cohort')} for g in old['games']]!=expected
                        or any(g['frame']!=plan['frames'] for g in old['games'])):
                        raise ValueError('existing group binding differs: '+name)
                    continue
                jobs.append(dict(out=str(out),name=name,pair=pair,plans=expected,frames=plan['frames']))
    # Order has no input to the simulator or policy. It only reduces idle CPUs.
    cost={'R4':3,'R3':2,'R2':2,'R1':2,'R0':1,'A5':1}
    return sorted(jobs,key=lambda j:-cost[j['pair']])


def execute_group(job):
    out=Path(job['out']);plan=json.loads((out/'plan.json').read_text())
    source=json.loads((out/'sources.json').read_text());stage=job['plans'][0]['stage'];pair=job['pair']
    if not _CACHE:
        _CACHE['parameters']=Parameters.local()
        _CACHE['models']=Models(ROOT/'work/sim/fidelity/motion.json',ROOT/'work/sim/fidelity/weapon.json',ROOT/'work/sim/advanced/model.json')
    if stage not in _CACHE:_CACHE[stage]=Terrain.load(stage)
    paths=[ROOT/source['policies'][n]['root'] for n in PAIRS[pair]];specs=[PolicySpec.load(p) for p in paths]
    if ([s.source_sha256 for s in specs]!=[source['policies'][n]['directory_sha256'] for n in PAIRS[pair]]
        or core_hashes()!=plan['sim_source_sha256']
        or {k:sha256(p) for k,p in _CACHE['models'].paths.items()}!=plan['model_sha256']):
        raise ValueError('live job binding drift')
    directory=out/job['name'];directory.mkdir(parents=True,exist_ok=True)
    result=directory/'result.json'
    if result.exists():raise ValueError('group concurrently produced by another runner')
    data=group(pair,specs,job['plans'],paths,directory,_CACHE['parameters'],_CACHE[stage],_CACHE['models'],job['frames'])
    data['scheduler_source_sha256']=sha256(__file__)
    temporary=directory/'result.json.tmp';temporary.write_text(json.dumps(data,indent=2)+'\n');temporary.replace(result)
    return dict(name=job['name'],pid=os.getpid(),games=len(data['games']),seconds=round(data['wall_seconds'],2),
                fps=round(data['environment_frames_per_second'],1),winners=[g['winner'] for g in data['games']])


def main(out=WORK,workers=2):
    if workers not in (1,2):raise ValueError('one or two CPU workers only')
    out=Path(out).resolve()
    if ROOT/'work' not in out.parents:raise ValueError('artifacts must stay under work/')
    out.mkdir(parents=True,exist_ok=True)
    with (out/'scheduler.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # Empty pair list registers/verifies exactly the normal experiment,
        # without launching any policy worker or simulation match.
        run(out,seeds=6,frames=10800,pairs=(),batch_size=6)
        jobs=pending(out)
        started=time.perf_counter()
        print(json.dumps(dict(pending_groups=len(jobs),workers=workers)),flush=True)
        with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as pool:
            for future in as_completed([pool.submit(execute_group,j) for j in jobs]):
                print(json.dumps(future.result()),flush=True)
        result=dict(schema='sim.ranking.schedule.v1',wall_seconds=time.perf_counter()-started,
                    groups=len(jobs),workers=workers,source_sha256=sha256(__file__))
        (out/'schedule.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=WORK)
    p.add_argument('--workers',type=int,choices=(1,2),default=2);a=p.parse_args();main(a.out,a.workers)
