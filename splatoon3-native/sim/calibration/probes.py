"""P0 gameplay-surface sampling, mixed-axis motion and lethal/respawn probe."""
import json
import math

from .p0 import controls,sequence


def flat_setup(lab):
    lab.navigate({0:(-8.,3.,8.),1:(18.,3.,-8.)},'setup-flat')
    lab.restore(0,(-8.,3.,8.))
    lab.align(0,(12.,4.1,8.))
    lab.result['flat_baseline']={str(i):lab.info(i) for i in (0,1)};lab.save()


def motion(lab,case):
    flat_setup(lab)
    vectors=[(0.,.25),(0.,.5),(0.,.85),(0.,1.),(.6,.6),(.85,.4),(1.,.25)]
    for n,(x,y) in enumerate(vectors):
        lab.restore(0,(-8.,3.,8.));lab.align(0,(12.,4.1,8.))
        sequence(lab,controls(),f'baseline-vector-{n}',30)
        a=controls();a['player_0']['sticks'][:2]=[x,y]
        sequence(lab,a,f'measure-vector-{n}-accelerate',45)
        sequence(lab,controls(),f'measure-vector-{n}-brake',30)
    lab.restore(0,(-8.,3.,8.));lab.align(0,(12.,4.1,8.))
    for f in range(216):
        a=controls();a['player_0']['sticks'][1]=.85;a['player_0']['buttons'][0]=int(f%36<12)
        lab.step(a,'measure-weapon-locomotion',1)
    sequence(lab,controls(),'measure-weapon-stop',90)
    # Ordinary jump in place gives a complete rise/apex/landing, without
    # mistaking a descending ledge for gravity.
    lab.restore(0,(-8.,3.,8.));sequence(lab,controls(),'jump-rest',40)
    a=controls();a['player_0']['buttons'][4]=1
    sequence(lab,a,'measure-inplace-jump-edge',1)
    sequence(lab,controls(),'measure-inplace-jump-land',120)
    lab.result['motion_status']='collected';lab.save()


def bends(lab,case):
    # Direct controller primitives at actual launch landings. No policy/T1
    # worker is resumed, no pose is written, and no atlas ground anchor used.
    sequence(lab,controls(),'measure-bend-neutral-launch',240)
    lab.result['bend_start']={str(i):lab.info(i) for i in (0,1)};lab.save()
    for n,(x,y,jump,frames) in enumerate(((0.,.85,0,120),(1.,.25,0,90),(0.,.85,1,1),(0.,.85,0,100),(-1.,.25,0,90),(0.,0.,0,80))):
        a=controls()
        for value in a.values():value['sticks'][:2]=[x,y];value['buttons'][4]=jump
        sequence(lab,a,f'measure-bend-leg-{n}',frames)
    lab.result['bend_end']={str(i):lab.info(i) for i in (0,1)}
    lab.result['bend_scope']='Observed movement/blocking/support at actual spawn-side geometry; no automatic slope/prop labels.';lab.save()


def scan(lab,case):
    flat_setup(lab);lab.look(0,-.28)
    lab.result['paint_before']={str(i):lab.info(i) for i in (0,1)}
    a=controls();a['player_0']['buttons'][0]=1
    sequence(lab,a,'measure-isolated-hold',case['settings'].get('hold',12))
    sequence(lab,controls(),'measure-isolated-release',90)
    lab.result['paint_after']={str(i):lab.info(i) for i in (0,1)}
    a=controls();a['player_0']['buttons'][1]=1
    sequence(lab,a,'measure-foot-own-submergence-control',12)
    lab.result['own_submergence_control']=lab.obs(0)['own']
    sequence(lab,controls(),'measure-foot-emerge',12);lab.save()
    # The character is a world-position probe: before any shot the lane was
    # procedurally unpainted, the sole source is role0's one controlled shot.
    # Code0 is a local gameplay surface witness, not native texture/UV truth.
    for n,z in enumerate((5.,6.5,8.,9.5,11.)):
        start,end=((-11.,12.) if n%2==0 else (12.,-11.))
        lab.navigate({0:(start,3.,z)},f'measure-scan-row-{z}-start')
        lab.navigate({0:(end,3.,z)},f'measure-scan-row-{z}')
    lab.result['scan_scope']='Own-ink gameplay contact at actual sampled XYZ; unknown wall/air/other layers excluded, no full native paint map claim.'
    lab.save()


def combat(lab,case):
    from probe_a6_combat import trial
    from stamper import charge_slash
    distance=case['settings'].get('distance',1.5)
    source=(-8.,3.,8.);target=(-8.+distance,3.,8.)
    lab.navigate({0:source,1:target},'duel-dry-setup')
    lab.restore(0,source);lab.restore(1,target)
    q=lab.info(1)['position'];lab.align(0,(q[0],q[1]+1.1,q[2]))
    a=controls();a['player_0']['sticks'][1]=.85
    sequence(lab,a,'duel-face-target',6);sequence(lab,controls(),'duel-face-settle',12)
    if not all(lab.info(i)['hp']>.999 and lab.info(i)['ink']>.999 for i in (0,1)):
        raise AssertionError('dry duel initial baseline not full')
    trial(lab,'measure-light-timing',lambda obs:charge_slash(obs,1))
    # Do not demand full HP while standing in the shooter's new paint. That
    # confounds regeneration with enemy-ink damage and broke the old setup.
    # The close full slash supplies an ordinary measured death; no HP writes.
    trial(lab,'measure-full-timing',lambda obs:charge_slash(obs,21))
    if lab.info(1).get('alive'):
        trial(lab,'measure-second-full',lambda obs:charge_slash(obs,21))
    lab.result['death_before_respawn']=lab.info(1);lab.save()
    death=not lab.info(1).get('alive',True);launched=False
    if death:
        for f in range(1100):
            a=controls();i=lab.info(1)
            if i.get('hp_valid') and i['hp']>.99 and i.get('position_valid') and i['position'][1]>20:
                a['player_1']['buttons'][0]=int(f%30==0)
            lab.step(a,'measure-true-respawn-launch',1)
            if lab.info(1).get('alive_valid') and lab.info(1)['alive']:
                launched=True;break
        if launched:sequence(lab,controls(),'measure-true-respawn-flight-land',240)
    lab.result['respawn_status']='launched' if launched else 'no_death_or_launch_observed'
    lab.save()


def collect(lab,case):
    return {'p0_motion':motion,'p0_scan':scan,'p0_combat':combat,'p0_bends':bends}[case['kind']](lab,case)
