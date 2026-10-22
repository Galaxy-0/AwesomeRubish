"""Derived numerical inputs for the contact-disjoint browser model."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.zipcaster_d4.blade_only import contact_exclusion
import numpy as np


def compile_safe_model(root,source):
    p=json.loads(source('work/a6/parameters.json').read_text())
    # Sparse numeric projectile configuration only, never resource files.
    parameters={k:{'CollisionParam':p[k]['CollisionParam']}for k in ['vertical_projectile','horizontal_projectile']}
    bounds={style:contact_exclusion(p,np.zeros((4,3)),np.tile([0.,0.,10.],(4,1)),style)['horizontal_bound']for style in ['full','light']}
    fit=json.loads(source('work/d4/restart-v3/attack-fit-v1.json').read_text())
    recoil=json.loads(source('work/d4/restart-v3/recoil-fit-v2.json').read_text())['profiles']
    for path in ['showcase/d4_safe_worker.js','showcase/d4_safe_runtime.py','tools/zipcaster_d4/blade_only.py','tools/zipcaster_d4/model_blade_only.py','tools/zipcaster_d4/attack_model_safe.py','tools/zipcaster_d4/attack_batch_safe.py','tools/zipcaster_d4/optimistic_blade_only.py']:
        source(path)
    return dict(schema='showcase.d4.safe-model.v1',parameters=parameters,contact_bounds=bounds,fit=fit,recoil=recoil,
                scope='Contact unknown; require disjoint4frames. All field balls must clear before body intersection. Ideal aim, finite programs, native/global optimality unclosed.')


if __name__=='__main__':
    import argparse,hashlib
    from pathlib import Path
    from showcase.d4_runtime_data import compile_runtime
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    assert not args.out.exists(),'fresh numerical runtime output required'
    root=Path(__file__).resolve().parents[1];bindings={}
    def source(path):
        p=Path(path);p=p if p.is_absolute()else root/p
        bindings[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest();return p
    runtime=compile_runtime(root,source);runtime['safe_model']=compile_safe_model(root,source)
    runtime['safe_sources']=bindings
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(runtime,allow_nan=False,separators=(',',':'))+'\n')
    print(args.out,args.out.stat().st_size)
