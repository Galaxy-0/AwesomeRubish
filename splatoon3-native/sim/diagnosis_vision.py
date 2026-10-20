"""Reproject historical native poses with indexed sim sight geometry, offline.

This checks implementation parity with the arena's accepted geometric rule,
not native renderer perception or a new true-visibility sensor.
"""
import json
from arena.geometry import GeometricVision
from arena.native_referee import NativeRefereeAdapter
from arena.visibility import PolicyProjector
from .diagnosis import OUT, WORK, records
from .parameters import ROOT, sha256
from .terrain import Terrain


def main():
    source=json.loads((WORK/'sources.json').read_text());results=[]
    terrains={i:Terrain.load(i) for i in (1,2,3)}
    for pair in ('A5','R1','R2'):
        seen=set()
        for match in source['references'][pair]['matches']:
            if pair=='A5' and match['stage']!=3:continue
            key=(match['stage'],tuple(match['role_to_policy']))
            if key in seen:continue
            seen.add(key);logs=records(match);expected={}
            for policy,rows in enumerate(logs):
                role=match['role_to_policy'].index(policy)
                expected[role]={row['observation']['frame']:row['observation'] for row in rows}
            path=ROOT/match['source']/'native-barriers.jsonl'
            adapter=None;projector=PolicyProjector('native-vision-check',stage_id=match['stage'])
            vision=GeometricVision(terrains[match['stage']].sight)
            checks=0;mismatches=[]
            for line in path.open():
                row=json.loads(line);frame=row['frame']
                if frame>10800:break
                if adapter is None:
                    origins={p:dict(info,frame=info['frame']-frame) for p,info in row['infos'].items()}
                    adapter=NativeRefereeAdapter('native-vision-check',origins,dict.fromkeys(row['infos'],8000),{f'player_{i}':i for i in (0,1)})
                truth=adapter.snapshot(row['infos'])
                if truth.frame!=frame:raise ValueError('native origin mismatch')
                for role in (0,1):
                    obs=expected[role].get(frame)
                    if obs is None:continue
                    observer=f'player_{role}'
                    projected=projector.observe(truth,observer,vision.witnesses(truth,observer))
                    native=obs['enemies'][0];sim=projected.enemies[0]
                    checks+=1
                    if sim.visible!=native['visible']:
                        mismatches.append(dict(frame=frame,role=role,native=native['visible'],reprojected=sim.visible,
                                               position=[p.position for p in truth.players]))
            results.append(dict(pair=pair,stage=match['stage'],source=match['source'],checks=checks,
                mismatches=mismatches,source_sha256=sha256(path)))
            print(pair,match['stage'],'visibility parity',checks,len(mismatches),flush=True)
    report=dict(results=results,code_sha256={str(p.relative_to(ROOT)):sha256(p) for p in
                [ROOT/'sim/diagnosis_vision.py',ROOT/'sim/terrain.py',ROOT/'arena/geometry.py',ROOT/'arena/native_referee.py',ROOT/'arena/visibility.py']},
                scope='Historical native poses through accepted arena visibility rule and sim indexed sight mesh; no renderer/native-vision truth claim.')
    (OUT/'vision-parity.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
