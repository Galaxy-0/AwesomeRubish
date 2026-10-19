#!/usr/bin/env python3
"""Sequential one-room combat/range experiments against a native player."""
import argparse
import math
import traceback
from a6_lab import Lab, neutral
from stamper import charge_slash, light_combo, burst_bomb, emerge_charge
from a6_metrics import large_hp_drops


def healthy(lab):
    return all(lab.info(n)['alive_valid'] and lab.info(n)['alive'] and lab.info(n)['hp_valid'] and lab.info(n)['hp']>.999 and lab.info(n)['ink']>.999 for n in (0,1))


def heal_and_refill(lab):
    a=lab.actions()
    for action in a.values():action['buttons'][1]=1
    for _ in range(16):
        lab.step(a,'heal-refill',15)
        if healthy(lab):break
    else:raise AssertionError('combat baseline must be healthy and full ink')
    lab.step(lab.actions(),'emerge',12)
    if not healthy(lab):raise AssertionError('combat baseline changed on emergence')


def prepare(lab, distance, source=(-8.,3.,8.), target=None,precise_pose=False):
    target=target or (source[0]+distance,3.,8.)
    lab.navigate({0:source,1:target},'duel-setup')
    if precise_pose:
        lab.restore(0,source);lab.restore(1,target)
    for n in (0,1):lab.paint_floor(n)
    heal_and_refill(lab)
    q=lab.info(1)['position'];lab.align(0,(q[0],q[1]+1.1,q[2]),precise=distance>=12)
    # Calibrate body-facing as well as camera-facing for the accepted A3a
    # geometric FOV, using only an ordinary, recorded setup movement.
    a=neutral();a['sticks'][1]=.85;lab.act(0,a,'face-target',6)
    lab.step(lab.actions(),'face-target-settle',8)


def range_reset(lab,distance):
    # Source has not moved or been attacked. Its existing own-ink patch is
    # retained; re-paint only the target after restoring the requested pose.
    lab.step(lab.actions(),'range-knockback-settle',30)
    target=(-8.+distance,3.,8.)
    lab.navigate({1:target},'range-target-reset');lab.restore(1,target)
    lab.paint_floor(1);heal_and_refill(lab)
    q=lab.info(1)['position'];lab.align(0,(q[0],q[1]+1.1,q[2]),precise=True)


def trial(lab,label,factory):
    before={n:lab.info(n) for n in (0,1)}
    history=lab.execute(0,factory(lab.obs(0)),label)
    for _ in range(12):history.append(dict(phase='observe',infos=lab.step(lab.actions(),label+'-observe',3)))
    values=[h['infos']['player_1'] for h in history]
    hps=[i['hp'] for i in values if i['hp_valid']]
    loss=before[1]['hp']-min(hps)
    events=large_hp_drops(before[1],values)
    first=next((i['frame'] for i in values if i['hp_valid'] and i['hp']<before[1]['hp']-.001),None)
    row=dict(kind=label,distance=math.dist(before[0]['position'],before[1]['position']),
             target_hp_loss=loss,hit=bool(events),native_damage_events=events,before=before,after={n:lab.info(n) for n in (0,1)},
             first_damage_sample=first,history=history)
    lab.add(row);lab.capture(label);return row


def main(args):
    if args.range_distances and (args.phase!='range' or args.kind=='both' or any(not 1<=d<=28 for d in args.range_distances)):
        raise ValueError('custom distances require one range kind and values in the flat 1..28 unit lane')
    lab=Lab(args.phase,args.timeout)
    try:
        lab.start()
        if args.phase=='range':
            # All poses are on the same native flat lane, z=8, y=3.
            # Record actual positions; requested distance is not a measurement.
            initial=True
            for kind,distances,hold in [('light',(14,22,18,20,19),1),('full',(20,24,22,23),args.charge)]:
                if args.kind!='both' and args.kind!=kind:continue
                if args.range_distances:distances=args.range_distances
                for distance in distances:
                    if initial:
                        prepare(lab,distance,precise_pose=args.precise_poses);initial=False
                    else:range_reset(lab,distance)
                    trial(lab,f'{kind}-{distance}',lambda obs,h=hold:charge_slash(obs,h))
            brackets={}
            for kind in ('light','full'):
                if args.kind!='both' and args.kind!=kind:continue
                rows=[r for r in lab.result['cases'] if r['kind'].startswith(kind+'-')]
                hits=[r['distance'] for r in rows if r['hit']]
                misses=[r['distance'] for r in rows if not r['hit']]
                brackets[kind]=dict(farthest_hit=max(hits) if hits else None,
                                    nearest_miss=min(misses) if misses else None)
            lab.result['range_brackets']=brackets
            lab.result['passed']=all(b['farthest_hit'] is not None and b['nearest_miss'] is not None and b['farthest_hit']<b['nearest_miss'] for b in brackets.values())
        else:
            prepare(lab,6,source=(8.,3.,8.))
            trial(lab,'minimum-predecessor-damage',lambda obs:charge_slash(obs,args.charge-1))
            prepare(lab,6,source=(8.,3.,8.))
            trial(lab,'minimum-full-damage',lambda obs:charge_slash(obs,args.charge))
            prepare(lab,6,source=(8.,3.,8.))
            lab.refill(0,180,surface=False)
            trial(lab,'emerge-full-damage',lambda obs:emerge_charge(obs,args.surface_charge))
            prepare(lab,6,source=(8.,3.,8.))
            trial(lab,'dash-full',lambda obs:charge_slash(obs,args.charge,dash=True))
            prepare(lab,8,source=(8.,3.,8.))
            trial(lab,'light-combo-move',lambda obs:light_combo(obs,3,after=(-1.,0.)))
            prepare(lab,6,source=(8.,3.,8.))
            trial(lab,'burst-bomb',lambda obs:burst_bomb(obs))
            lab.result['passed']=True  # completed experiments; audit checks effects separately
        lab.result['probe_completed']=True
    except BaseException as e:
        lab.result['errors'].append(repr(e));lab.result['traceback']=traceback.format_exc()
    finally:lab.close()
    print(lab.out,flush=True)
    return 0 if lab.result['passed'] and not lab.result['errors'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase',choices=('range','combat'),required=True)
    p.add_argument('--kind',choices=('light','full','both'),default='both',help='Use separate sequential rooms when the full sweep exceeds a normal game')
    p.add_argument('--range-distances',type=float,nargs='+')
    p.add_argument('--precise-poses',action='store_true',help='Restore measured range poses to .12 units before painting/healing')
    p.add_argument('--charge',type=int,default=24);p.add_argument('--surface-charge',type=int,default=24)
    p.add_argument('--timeout',type=float,default=3600)
    raise SystemExit(main(p.parse_args()))
