#!/usr/bin/env python3
"""Measure controlled release threshold from full-cost native ink deductions."""
import argparse
import traceback
from a6_lab import Lab,neutral


def main(args):
    lab=Lab('timing',args.timeout)
    try:
        lab.start()
        a=lab.actions()
        for v in a.values():v['sticks'][1]=1.
        lab.step(a,'leave-spawn',90);lab.step(lab.actions(),'land',60)
        lab.paint_floor(0);lab.look(0,.85)
        for submerged in (False,True):
            for hold in (1,5,18,19,20,21,22,24,30):
                lab.refill(0,180,surface=not submerged)
                before=lab.info(0);initial=lab.obs(0)['own']
                if before['ink']<.999:raise AssertionError('timing trial not full tank')
                if submerged and initial['submerged'] is not True:raise AssertionError('surface trial did not start in own ink')
                a=neutral();a['buttons'][0]=1;history=[]
                for _ in range(hold):history.append(lab.act(0,a,'charge',1)['player_0'])
                release=lab.info(0)['frame'];history.append(lab.step(lab.actions(),'release',36)['player_0'])
                cost=before['ink']-min(i['ink'] for i in history)
                human=[i['position_sample_frame'] for i in history if i.get('referee_motion',{}).get('form_squid')==0]
                lab.add(dict(kind='surface-charge' if submerged else 'standing-charge',hold_frames=hold,
                             start_frame=before['frame'],release_frame=release,cost=cost,full_cost=cost>=.1168,
                             before_form=initial['form_squid'],first_human_sample=min(human) if human else None,
                             position=list(before['position'])))
        thresholds={}
        for kind in ('standing-charge','surface-charge'):
            rows=[c for c in lab.result['cases'] if c['kind']==kind]
            full=[c['hold_frames'] for c in rows if c['full_cost']]
            if not full:raise AssertionError('no full charge threshold')
            threshold=min(full)
            if not any(c['hold_frames']==threshold-1 and not c['full_cost'] for c in rows):raise AssertionError('threshold predecessor unmeasured')
            thresholds[kind]=threshold
        lab.result.update(passed=True,thresholds=thresholds,definition='Input ZL release + ZR press to ZR release in controlled presents; native human form retains sampled timestamp uncertainty.')
    except BaseException as e:lab.result['errors'].append(repr(e));lab.result['traceback']=traceback.format_exc()
    finally:lab.close()
    print(lab.out,flush=True);return 0 if lab.result['passed'] and not lab.result['errors'] else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--timeout',type=float,default=3600);raise SystemExit(main(p.parse_args()))
