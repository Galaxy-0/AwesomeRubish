"""Predictive offline ranking after P0; never launches a native game or T1.

Only the historical observed map/seat strata are compared. No native prefix,
trajectory or game-specific clock is injected. Seeds remain sensitivities.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path

from arena.config import PolicySpec
from sim.parameters import ROOT,Parameters,sha256
from sim.ranking import Models,group,core_hashes
from sim.ranking_sources import WORK,PAIRS
from sim.terrain import Terrain
from sim.opening import OpeningModel
from sim.paint_model import PaintModel


def run(job):
    pair,stage,swap,seeds,directory,models_dir,clock=job
    out=Path(directory);out.mkdir(parents=True,exist_ok=False)
    source=json.loads((WORK/'sources.json').read_text())
    paths=[ROOT/source['policies'][p]['root'] for p in PAIRS[pair]]
    specs=[PolicySpec.load(p) for p in paths]
    if [s.source_sha256 for s in specs]!=[source['policies'][p]['directory_sha256'] for p in PAIRS[pair]]:
        raise ValueError('frozen policies changed')
    directory=Path(models_dir)
    models=Models(directory/'motion.json',ROOT/'work/sim/fidelity/weapon.json',ROOT/'work/sim/advanced/model.json')
    extras=dict(opening_model=OpeningModel.load(directory/'opening.json'),paint_model=PaintModel.load(directory/'paint.json'))
    files={**models.paths,**{k:directory/(k+'.json') for k in ('opening','paint')}}
    names=(*core_hashes(),'opening.py','paint_model.py','observation_clock.py')
    code={f'sim/{n}':sha256(ROOT/'sim'/n) for n in names}
    binding=dict(models={k:sha256(v) for k,v in files.items()},code=code,sources=sha256(WORK/'sources.json'))
    plans=[dict(stage=stage,swap=swap,seed=n,cohort='fixed' if n==0 else 'initial_sensitivity') for n in range(seeds)]
    (out/'plan.json').write_text(json.dumps(dict(binding=binding,pair=pair,plans=plans,frames=10800,clock_period=clock,
        interpretation='Predictive empirical launch, generic four-frame sample/one-frame delivery; no copied native prefix/values. Matched map/seat strata; seeds are sensitivities.'),indent=2)+'\n')
    data=group(pair,specs,plans,paths,out,Parameters.local(),Terrain.load(stage),models,10800,extras=extras,clock_period=clock)
    if any(sha256(ROOT/k)!=v for k,v in code.items()):raise ValueError('source changed during experiment')
    data['binding']=binding
    (out/'result.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(dict(pair=pair,stage=stage,swap=swap,winners=[g['winner'] for g in data['games']],seconds=data['wall_seconds'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--models',type=Path,required=True);p.add_argument('--seeds',type=int,default=6)
    p.add_argument('--workers',type=int,choices=(1,2),default=2);p.add_argument('--clock-period',type=int,default=4)
    a=p.parse_args()
    if not a.out.resolve().is_relative_to(ROOT/'work'):p.error('output must be under work/')
    if not 1<=a.seeds<=6:p.error('bounded seed count 1..6')
    source=json.loads((WORK/'sources.json').read_text());jobs=[]
    for pair in ('A5','R1','R2','R3'):
        strata=sorted({(m['stage'],m['role_to_policy'][0]==1) for m in source['references'][pair]['matches'] if pair!='A5' or m['stage']==3})
        for stage,swap in strata:jobs.append((pair,stage,swap,a.seeds,str(a.out/f'{pair}-map{stage}-side{int(swap)}'),str(a.models),a.clock_period))
    with ProcessPoolExecutor(max_workers=a.workers) as pool:list(pool.map(run,jobs))
