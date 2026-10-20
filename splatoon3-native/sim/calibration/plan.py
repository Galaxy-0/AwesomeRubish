"""Declarative, resumable one-command calibration suite (offline by default)."""
import hashlib
import json

LEVELS=(0,3,10,19,38,57)
BASE='quick_super_jump'  # control skill; no super jumps used in these cases


def loadout(skill, ap):
    if skill==BASE or ap not in LEVELS:
        raise ValueError('invalid target skill/AP')
    pieces=('head','clothes','shoes')
    result={p:dict(main=BASE,subs=[BASE]*3) for p in pieces}
    mains,subs=next((m,s) for m in range(4) for s in range(10) if 10*m+3*s==ap)
    for p in pieces[:mains]:result[p]['main']=skill
    for index in range(subs):result[pieces[index//3]]['subs'][index%3]=skill
    return result


def suite():
    cases=[]
    def add(kind, *, skill='run_speed_up', ap=0, stage=1, repeats=3, **settings):
        payload=dict(kind=kind,skill=skill,ap=ap,stage=stage,repeats=repeats,
                     loadout=loadout(skill,ap),settings=settings,frame_budget=9000)
        identifier=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:12]
        cases.append(dict(id=kind+'-'+identifier,**payload))
    for surface in ('dry','own','enemy'):
        for form in ('human','squid'):
            add('motion',surface=surface,form=form)
    for skill in ('run_speed_up','swim_speed_up','ink_resistance_up'):
        for ap in LEVELS[1:]:
            for surface in ('dry','own','enemy'):
                for form in ('human','squid'):
                    add('motion',skill=skill,ap=ap,surface=surface,form=form)
    for skill in ('ink_saver_main','ink_saver_sub','ink_recovery_up'):
        for ap in LEVELS:
            add('ink',skill=skill,ap=ap,surface='own' if skill=='ink_recovery_up' else 'dry')
    for ap in LEVELS:
        add('roll',skill='intensify_action',ap=ap,repeats=1,
            runups=[6,12,18,30],angles=[45,90,120,180],travel_frames=120)
        add('surge',skill='intensify_action',ap=ap,repeats=1,charges=[1,20,30,40,44,45,46,60])
    for stage in (1,2,3):
        for shape in ('slope','step'):
            add('terrain',stage=stage,shape=shape,repeats=3)
    for distance in (1.,1.5,1.8,2.,2.5,3.,5.8,6.2,12.,19.):
        add('contact',distance=distance,repeats=1)
    add('recovery',repeats=3)
    add('dash',repeats=3)
    add('bomb',repeats=3)
    add('zip',repeats=1)
    return dict(schema='sim.native.calibration.plan.v1',cases=cases,
        serial_rooms=True,hosts_per_room=2,active_native_execution=False,
        sampling='STEP1; deduplicate by each own position_sample_frame; retain both-host origins and input intervals.',
        surface_truth='Own submergence can confirm own ink; dry/enemy remain procedural until visual/manual annotation or native paint readback.',
        acceptance='Collection completion is not mechanism acceptance. Exclude unknown surfaces/collision/expired samples from fits.',
        source_required=['game build ID','host SHA256','sim/calibration/*.py and reused tests/public skill SHA256',
                         'native gear readback','stage mesh/navigation SHA256','input+sample frame+validity+pose+HP+ink+form+camera',
                         'setup/measurement separation','start/end screenshots','case status and reason'])
