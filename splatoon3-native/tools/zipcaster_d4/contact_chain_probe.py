"""At most one measured full slash per invocation, passive recipient.

Uses ordinary placement/refinement, natural full health, finite native special,
and the unchanged ideal-aim v6 slash executor. Both processes observe the
read-only contact chain. This is not the new216 cohort.
"""
import argparse,json,math,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d4 import duel_v6 as duel
from tools.zipcaster_d4.attack_probe_v4 import refine
from tools.zipcaster_d3r.control import NativeSession,sha


def main(a):
    point=next(p for p in json.loads(a.plan.read_text())['points']if p['id']==a.point)
    if point['program']!='full1' or point['hooks'] or point['speed']!=40 or not a.passive:
        raise ValueError('bounded passive ground single-full probe only')
    original_options,original_place,original_new=NativeSession.host_options,duel.place,duel.new_lab
    def options(session,n):return original_options(session,n)|{'DM_D4_CONTACT_SENSOR':'1'}
    def place(lab,goals):
        original_place(lab,goals)
        for n,goal in goals.items():refine(lab,n,goal)
        lab.step(lab.actions(),'d4-chain-stable-pose',16)
        errors=[math.dist(lab.info(n)['position'],goals[n])for n in [0,1]]
        lab.result['chain_pose_gate']=dict(errors=errors,maximum=.35,paired_within005=max(errors)<=.05)
        if max(errors)>.35:raise AssertionError('predeclared chain pose gate failed beforeRS')
    def new_lab(*args,**kwargs):
        lab=original_new(*args,**kwargs)
        original_step=lab.step
        def checked_step(actions,label,frames=6):
            result=original_step(actions,label,frames)
            if label=='d4-natural-settle':
                errors=[math.dist(lab.info(n)['position'],point['source']if n==0 else point['enemy'])for n in [0,1]]
                lab.result['chain_final_pose_gate']=dict(errors=errors,maximum=.35,paired_within005=max(errors)<=.05)
                if max(errors)>.35:raise AssertionError('settled pose exceeds predeclared gate beforeRS')
            return result
        lab.step=checked_step
        (lab.out/'tested-contact_chain_probe.py').write_bytes(Path(__file__).read_bytes())
        lab.result['contact_chain_fixture']=dict(source_sha256=sha(__file__),maximum_measured_slashes=1,
            sensor_players=[0,1],pose_gate=.35,calibration_eligible=False,
            scope='Two planned cases total, successful contact is mandatory positive observation control. Native aim/special fixtures only.')
        return lab
    with patch.object(NativeSession,'host_options',options),patch.object(duel,'place',place),patch.object(duel,'new_lab',new_lab):
        return duel.main(a)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--point',required=True);p.add_argument('--host',type=Path,required=True)
    p.add_argument('--passive',action='store_true');p.add_argument('--repeat',type=int,default=0);p.add_argument('--hold-r',type=int,default=1)
    p.add_argument('--parameters',type=Path,default=ROOT/'work/d3r/attack-parameters-v1.json');p.add_argument('--ray',type=Path,default=ROOT/'work/d3r/ray-v2-frozen.json');raise SystemExit(main(p.parse_args()))
