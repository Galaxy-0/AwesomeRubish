#!/usr/bin/env python3
"""Fresh A6 operation regressions using accepted fixture controllers/controls.

Each suite owns one ordinary-length game. Effect assertions remain separate
from completed inputs. Zip traversal and charge-keep remain unsupported.
"""
import argparse
import math
import traceback
from unittest.mock import patch
from a6_lab import Lab,neutral
from probe_a6_combat import prepare,trial
from probe_a6_validation import roll_case
from probe_a6_movement import aim_checks,surge_checks
from a6_motion import calibrate_roll
from a6_metrics import large_hp_drops
from stamper import charge_slash,emerge_charge,light_combo,burst_bomb
from rl.loadout import uniform_loadout
from rl.native_start import NativeSession


def combat(lab):
    for name,controller in [('minimum-full-damage',lambda o:charge_slash(o,21)),('emerge-full-damage',lambda o:emerge_charge(o,26)),('dash-full',lambda o:charge_slash(o,21,dash=True))]:
        prepare(lab,6,source=(8.,3.,8.))
        if name=='emerge-full-damage':lab.refill(0,180,surface=False)
        row=trial(lab,name,controller)
        if not .699<=row['target_hp_loss']<=.701 and name!='dash-full':raise AssertionError('native full damage changed')
        if name=='dash-full':
            released=[h['infos']['player_0'] for h in row['history'] if h['phase']=='charge'][-1]
            if row['target_hp_loss']<.69 or math.dist(released['position'],row['after'][0]['position'])<2.:raise AssertionError('dash movement/damage missing')


def combo_bomb(lab):
    prepare(lab,8,source=(8.,3.,8.));row=trial(lab,'light-combo-move',lambda o:light_combo(o,3,after=(-1.,0.)))
    if math.dist(row['before'][0]['position'],row['after'][0]['position'])<.3 or row['before'][0]['ink']-min(h['infos']['player_0']['ink'] for h in row['history'])<.155:raise AssertionError('combo costs/displacement missing')
    prepare(lab,6,source=(8.,3.,8.));row=trial(lab,'burst-bomb',burst_bomb)
    if row['before'][0]['ink']-min(h['infos']['player_0']['ink'] for h in row['history'])<.449 or not large_hp_drops(row['before'][1],[h['infos']['player_1'] for h in row['history']],minimum=.20):raise AssertionError('bomb native cost/damage missing')


def roll(lab):
    lab.navigate({0:(0.,3.,8.),1:(18.,3.,8.)})
    for x in (3.,6.,0.):lab.navigate({0:(x,3.,8.)});lab.paint_floor(0)
    for name,reverse,jump in [('swim-forward-jump-control',False,True),('swim-reverse-control',True,False),('squid-roll-matched',True,True)]:roll_case(lab,name,reverse,jump)
    lab.save()
    if not calibrate_roll(lab.out/'result.json')['passed']:raise AssertionError('roll matched-control witness failed')


def aim_surge(lab):
    aim_checks(lab);surge_checks(lab)
    rows={r['kind']:r for r in lab.result['cases']};turn=rows['fast-turn-gyro'];control=rows['ordinary-turn-gyro-control']
    delta=turn['after']['own_view']['yaw']-turn['before']['own_view']['yaw']
    if not turn['converged'] or abs(math.atan2(math.sin(delta),math.cos(delta)))<2.8 or turn['gyro_fallback'] or turn['after']['frame']-turn['before']['frame']>=control['after']['frame']-control['before']['frame']:raise AssertionError('fast-turn failed matched native control')
    aligned=[]
    for h in rows['predictive-track']['history']:
        if h['target'] is None or math.hypot(h['velocity'][0],h['velocity'][2])<=.01:continue
        p=h['own']['position'];t=h['target'];error=math.atan2(t[0]-p[0],t[2]-p[2])-h['own']['view_yaw'];aligned.append(abs(math.atan2(math.sin(error),math.cos(error)))<=.08)
    if not any(aligned):raise AssertionError('predictive lead alignment missing')
    r=rows['surge-stopped-charge'];c=rows['surge-stopped-control']
    held=[h['infos']['player_0'] for h in r['history'] if h['phase']=='wall_charge'];released=[h['infos']['player_0'] for h in r['history'] if h['phase']=='surge_release']
    gain=max(h['position'][1] for h in released)-held[-1]['position'][1];baseline=max(h['infos']['player_0']['position'][1] for h in c['history'])-c['before']['position'][1]
    if len(held)<8 or max(h['position'][1] for h in held[2:])-min(h['position'][1] for h in held[2:])>.35 or gain<4. or gain<baseline+1. or not all(h['alive'] and h['hp']>=.999 for h in held+released):raise AssertionError('charged wall release/control witness failed')


def special(lab):
    def idle(label,expected):
        for _ in range(15):
            infos=lab.step(lab.actions(),label,6)
            if any(not infos[f'player_{n}']['special_valid'] or abs(infos[f'player_{n}']['special']-v)>.001 or not infos[f'player_{n}']['alive'] for n,v in expected.items()):raise AssertionError('native special meter unstable')
    idle('full-idle',{0:1.,1:1.})
    for cycle,players in [(1,[0,1]),(2,[1])]:
        before={n:lab.info(n) for n in (0,1)};a=lab.actions()
        for n in players:a[f'player_{n}']['buttons'][3]=1
        history=[dict(phase='press',frames=1,infos=lab.step(a,'special-press',1))];interior={n:False for n in players}
        for _ in range(200):
            infos=lab.step(lab.actions(),'special-active',6);history.append(dict(phase='active',infos=infos))
            for n in players:
                i=infos[f'player_{n}'];interior[n]|=.05<i['special']<.95
                if not i['alive'] or not i['special_valid']:raise AssertionError('special feedback unavailable')
            if all(interior.values()) and lab.info(0)['special']==0. and lab.info(1)['special']==1.:break
        else:raise AssertionError('special lifecycle/full-infinite behavior failed')
        lab.add(dict(kind='special-cycle',number=cycle,before=before,history=history,after={n:lab.info(n) for n in (0,1)}))
        idle('after-special',{0:0.,1:1.})


def main(args):
    lab=Lab('regression-'+args.suite,args.timeout,loadouts=[uniform_loadout('special_charge_up'),uniform_loadout()])
    original=NativeSession.host_options
    def options(session,player):return original(session,player)|dict(DM_TEST_SPECIAL=('full','infinite')[player])
    try:
        if args.suite=='special':
            with patch.object(NativeSession,'host_options',options):lab.start()
        else:lab.start()
        dict(combat=combat,combo_bomb=combo_bomb,roll=roll,aim_surge=aim_surge,special=special)[args.suite](lab)
        lab.result.update(passed=True,probe_completed=True)
    except BaseException as e:lab.result['errors'].append(repr(e));lab.result['traceback']=traceback.format_exc()
    finally:lab.close()
    print(lab.out,flush=True);return 0 if lab.result['passed'] and not lab.result['errors'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--suite',choices=('combat','combo_bomb','roll','aim_surge','special'),required=True);p.add_argument('--timeout',type=float,default=2400)
    raise SystemExit(main(p.parse_args()))
