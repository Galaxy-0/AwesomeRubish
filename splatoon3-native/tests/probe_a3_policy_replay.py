#!/usr/bin/env python3
"""Replay actual screenshot-scenario native states through the policy subprocess."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.referee_api import RefereeAPI
from arena.process import PolicyProcess


def main(path):
    path=path.resolve()
    if not path.is_relative_to(ROOT/'work'):raise ValueError('native replay must stay under ignored work/')
    result=json.loads(path.read_text());steps=[json.loads(s) for s in path.with_name('steps.jsonl').read_text().splitlines()]
    agents=list(steps[0]['infos']);api=RefereeAPI(path.parent.name,steps[0]['infos'],dict.fromkeys(agents,8000),
            dict(zip(agents,(0,1))),ROOT/'work/arena/maps/Yunohana/sight.npz')
    cases={c['host_frame']:c for c in result['cases']};root=path.parent/'policy-fixture';root.mkdir(exist_ok=True)
    (root/'policy.py').write_text('''def act(obs):
    assert obs['schema']=='arena.policy.v1'
    assert all('hp' not in e and 'ink' not in e for e in obs['enemies'])
    assert all(e['visible'] or (e['position'] is None and e['sample_frame'] is None) for e in obs['enemies'])
    return dict(sticks=[0]*4,gyro=[0]*3,buttons=[int(any(e['visible'] for e in obs['enemies']))]+[0]*5)
''')
    checks=[]
    with PolicyProcess(root,path.parent/'policy-replay.log',timeout=2) as child:
        for row in steps:
            api.update(row['infos']);frame=row['infos']['player_0']['frame']
            if frame not in cases:continue
            obs=api.policy_observation('player_0');reply=child.act(obs)
            expected=cases[frame]['expected_geometry']
            if bool(reply['buttons'][0])!=expected:raise AssertionError('native replay policy visibility mismatch')
            checks.append(dict(label=cases[frame]['label'],visible=bool(reply['buttons'][0])))
        try:child.act(api.state())
        except TypeError:rejected=True
        else:raise AssertionError('private referee type was accepted')
    report=dict(diagnostic_completed=True,full_a3_passed=False,checks=checks,referee_rejected=rejected,
                note='Real native states + actual sandboxed process; remaining A3 native paint/events are separate.')
    path.with_name('policy-subprocess-replay.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('result',type=Path);main(p.parse_args().result)
