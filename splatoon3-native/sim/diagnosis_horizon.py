"""Teacher-forced early-route windows for the R1/R2 counterexamples, offline."""
import json
from collections import defaultdict
import numpy as np

from .diagnosis import OUT, WORK, native_trace
from .engine import Simulator
from .horizon import reset_native, action_dict, measure
from .parameters import ROOT, Parameters, sha256
from .ranking import Models, core_hashes
from .replay import stats
from .terrain import Terrain


def main():
    sources=json.loads((WORK/'sources.json').read_text())
    models=Models(ROOT/'work/sim/fidelity/motion.json',ROOT/'work/sim/fidelity/weapon.json',ROOT/'work/sim/advanced/model.json')
    parameters=Parameters.local();terrains={i:Terrain.load(i) for i in (1,2,3)}
    result=[];binding=core_hashes()
    for pair in ('R1','R2'):
        for match in sources['references'][pair]['matches']:
            trace=native_trace(match);terrain=terrains[match['stage']]
            from arena.config import PolicySpec
            loadouts=[PolicySpec.load(ROOT/sources['policies'][name]['root']).loadout for name in sources['references'][pair]['pair']]
            env=Simulator(match['stage'],parameters=parameters,terrain=terrain,loadouts=loadouts,
                duration_frames=trace.frames,swap=match['role_to_policy'][0]==1,
                motion_model=models[0],weapon_model=models[1],advanced_model=models[2])
            windows=[]
            for anchor in range(120,1921,120):
                try:meta=reset_native(env,trace,anchor)
                except ValueError as exc:
                    windows.append(dict(anchor=anchor,skipped=str(exc)));continue
                errors=[defaultdict(list),defaultdict(list)]
                checkpoints={};initial=[p.position.tolist() for p in env.players]
                for frame in range(anchor+1,anchor+121):
                    env.step(action_dict(trace.actions[frame-1]),observe=False)
                    for role,p in enumerate(env.players):
                        row=trace.states[frame,role]
                        if np.isfinite(row[0]):
                            for key,value in measure(p,row).items():errors[role][key].append(value)
                    if frame-anchor in (30,60,120):
                        checkpoints[str(frame-anchor)]=[{key:stats(value) for key,value in err.items()} for err in errors]
                windows.append(dict(anchor=anchor,initial=initial,metadata=meta,errors=checkpoints))
            result.append(dict(pair=pair,stage=match['stage'],source=match['source'],windows=windows))
            print(pair,match['stage'],'early windows',len(windows),flush=True)
    if core_hashes()!=binding:raise ValueError('core changed during windows')
    report=dict(schema='sim.route.horizon.v1',core=binding,helper_sha256={f:sha256(ROOT/'sim'/f) for f in ('horizon.py','diagnosis.py','diagnosis_horizon.py')},source_sha256=sha256(WORK/'sources.json'),
        model_sha256={k:sha256(p) for k,p in models.paths.items()},results=result,
        protocol='Reset every120; measure first30/60/120; first1920frames. Observable states only; causal past velocity/phase estimate.',
        limitations=['No native world paint or exact velocity/weapon phase.','Diagnostic test-set residuals, no parameter fitting or selection.'])
    (OUT/'early-horizon.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
