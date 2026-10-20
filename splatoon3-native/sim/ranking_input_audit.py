"""Count native advanced INPUT ATTEMPTS; these are not activation witnesses."""
import json
from pathlib import Path

import numpy as np

from .parameters import ROOT,sha256
from .ranking_sources import WORK


def attempts(actions):
    actions=np.asarray(actions)
    if actions.ndim!=3 or not len(actions) or actions.shape[1:]!=(2,13) or not np.isfinite(actions).all():
        raise ValueError('invalid normalized native actions')
    b=actions[:,:,7:]!=0
    previous=np.concatenate([np.zeros((1,2,6),bool),b[:-1]])
    clock=np.arange(1,len(actions)+1)[:,None]
    last_off=np.maximum.accumulate(np.where(~b[:,:,0],clock,0),axis=0)
    holds=np.where(b[:,:,0],clock-last_off,0)
    hold_before=np.concatenate([np.zeros((1,2),int),holds[:-1]])
    return dict(R_press=int(np.count_nonzero(b[:,:,2]&~previous[:,:,2])),
                R_release=int(np.count_nonzero(~b[:,:,2]&previous[:,:,2])),
                RS_press=int(np.count_nonzero(b[:,:,3]&~previous[:,:,3])),
                ZL_B_edge=int(np.count_nonzero(b[:,:,1]&b[:,:,4]&~previous[:,:,4])),
                full_forward_release_candidate=int(np.count_nonzero(~b[:,:,0]&previous[:,:,0]&(hold_before>=21)&(actions[:,:,1]>=.9))))


def main(out=WORK,emit=True):
    source=json.loads((out/'sources.json').read_text())
    report=dict(schema='sim.ranking.input-audit.v1',sources_sha256=sha256(out/'sources.json'),
                code_sha256=sha256(__file__),
                pairs={},evidence={},
                interpretation='Native controller attempts only, NOT roll/surge/dash/bomb/zip activation proof; R can also be a special hook.')
    for pair,reference in source['references'].items():
        counts={};games=0;missing=[]
        for match in reference['matches']:
            path=(ROOT/Path(match['source'])).resolve()/'inputs-per-present.jsonl'
            if not path.exists() or not path.stat().st_size:
                missing.append(dict(source=match['source'],reason='missing/empty native inputs'));continue
            rows=[json.loads(line) for line in path.open() if line.strip()]
            actions=[];durations=[];end=0
            for row in rows:
                lo,hi=row['frame_interval']
                if lo!=end or hi<=lo:raise ValueError('native input gap/overlap')
                end=hi;durations.append(hi-lo)
                actions.append([[*row['actions'][f'player_{i}']['sticks'],*row['actions'][f'player_{i}']['gyro'],
                                 *row['actions'][f'player_{i}']['buttons']] for i in range(2)])
            values=attempts(np.repeat(np.array(actions,float),durations,axis=0))
            for k,v in values.items():counts[k]=counts.get(k,0)+v
            games+=1
            report['evidence'][str(path.relative_to(ROOT))]=dict(input_sha256=sha256(path),frames=end,
                 result_sha256=sha256(path.parent/'result.json'))
        report['pairs'][pair]=dict(games=games,missing=missing,attempts=counts)
    (out/'native-input-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    if emit:print(json.dumps(report['pairs'],indent=2))
    return report


if __name__=='__main__':main()
