#!/usr/bin/env python3
"""Adjacent-frame refinement after the initial coarse emergence sweep."""
import argparse
import traceback
from a6_lab import Lab,neutral


def main(args):
    lab=Lab('timing-refine',args.timeout)
    try:
        lab.start();a=lab.actions()
        for v in a.values():v['sticks'][1]=1.
        lab.step(a,'leave-spawn',90);lab.step(lab.actions(),'land',60)
        lab.paint_floor(0);lab.look(0,.85)
        thresholds={}
        for submerged,holds in ((False,range(19,25)),(True,range(20,33))):
            kind='surface-charge' if submerged else 'standing-charge'
            previous=None
            for hold in holds:
                lab.refill(0,180,surface=not submerged)
                before=lab.info(0);initial=lab.obs(0)['own']
                if before['ink']<.999 or submerged and initial['submerged'] is not True:
                    raise AssertionError('refinement baseline invalid')
                action=neutral();action['buttons'][0]=1;history=[]
                for _ in range(hold):history.append(lab.act(0,action,kind,1)['player_0'])
                release=lab.info(0)['frame']
                history.append(lab.step(lab.actions(),'release',36)['player_0'])
                cost=before['ink']-min(i['ink'] for i in history)
                case=dict(kind=kind,hold_frames=hold,start_frame=before['frame'],release_frame=release,
                          cost=cost,full_cost=cost>=.1168,before_form=initial['form_squid'],
                          first_human_sample=min((i['position_sample_frame'] for i in history if i.get('referee_motion',{}).get('form_squid')==0),default=None),
                          position=before['position'],history=history)
                lab.add(case)
                if case['full_cost']:
                    if previous is None or previous['hold_frames']!=hold-1 or previous['full_cost']:
                        raise AssertionError('refinement lower boundary must be extended')
                    thresholds[kind]=hold;break
                previous=case
            if kind not in thresholds:raise AssertionError('no full threshold within bounded sweep')
        lab.result.update(passed=True,thresholds=thresholds,probe_completed=True,
                          definition='Controlled presents from simultaneous ZL release/ZR press to ZR release; independent native packet timestamps bound emergence.')
    except BaseException as e:
        lab.result['errors'].append(repr(e));lab.result['traceback']=traceback.format_exc()
    finally:lab.close()
    print(lab.out,flush=True);return 0 if lab.result['passed'] and not lab.result['errors'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--timeout',type=float,default=3600)
    raise SystemExit(main(p.parse_args()))
