"""P0 stationary native paint impulses and geometry-preserving texture dump.

The accepted camera host stays in geometry mode. Its existing diagnostic
TEXDUMP switch reads color targets; no shader/host/transport code is modified.
Texture pixels are UV-space observations until independently mapped to world.
"""
import json
import math
from pathlib import Path
import numpy as np

from .p0 import controls,sequence


def collect(lab,case):
    settings=case['settings']
    # Both sides stand where their native launch leaves them. Do not use the
    # atlas landing point or move/paint during setup.
    sequence(lab,controls(),'measure-neutral-opening',240)
    lab.result['paint_pose']={str(i):lab.info(i) for i in (0,1)}
    # Native gyro, same pitch on both peers; retain actual settled camera.
    for _ in range(140):
        a=controls();done=True
        for role in (0,1):
            pitch=lab.info(role).get('own_view',{}).get('pitch')
            if pitch is None:raise RuntimeError('missing pitch for paint setup')
            error=pitch-settings.get('pitch',-.28)
            if abs(error)>.012:
                done=False;a[f'player_{role}']['gyro'][0]=max(-.12,min(.12,error*.3))
        if done:break
        lab.step(a,'setup-paint-pitch',1)
    sequence(lab,controls(),'setup-pitch-settle',12)
    before={str(i):lab.info(i) for i in (0,1)}
    hold=settings.get('hold',12)
    for repeat in range(settings.get('strokes',1)):
        a=controls()
        for role in settings.get('painting_roles',(0,1)):a[f'player_{role}']['buttons'][0]=1
        sequence(lab,a,f'measure-paint-{repeat}-hold',hold)
        sequence(lab,controls(),f'measure-paint-{repeat}-release',max(40,60-hold))
    sequence(lab,controls(),'measure-paint-tail',60)
    lab.result['paint_before']=before
    lab.result['paint_after']={str(i):lab.info(i) for i in (0,1)}
    lab.save()
    if settings.get('finish_at_dump'):
        target=settings['texture_frame']+120
        if target<=lab.origins['player_0']['frame']:raise ValueError('texture frame preceded native attachment')
        while lab.info(0)['frame']<target:
            frames=min(120,target-lab.info(0)['frame'])
            lab.step(controls(),'neutral-texture-checkpoint',frames)
        files=list((lab.out/'textures').glob('*.png'))
        if not files:raise AssertionError('native diagnostic produced no texture files')
        lab.result['texture_checkpoint']=dict(frame=lab.info(0)['frame'],files=len(files),
            scope='Fixed absolute-frame UV target readback only; not a complete match or terminal score.')
        return
    # Finish without more shooting or motion; obtain real native denominator
    # and score. The configured one-shot dump occurs within this neutral tail.
    while lab.env.agents:
        if hasattr(lab,'checkpoint'):lab.checkpoint()
        if lab.budget+120>case['frame_budget']:raise RuntimeError('paint full-match frame budget')
        lab.budget+=120
        lab.env.frame_skip=120
        a={k:{name:np.asarray(v,dtype=np.int8 if name=='buttons' else np.float32) for name,v in action.items()} for k,action in controls().items() if k in lab.env.agents}
        _,_,_,truncated,infos=lab.env.step(a)
        if any(truncated.values()):raise TimeoutError('paint finish deadline')
        if all(i['phase']==1 for i in infos.values()):lab.api.update(infos)
        lab.count+=1
        lab.stream.write(json.dumps(dict(step=lab.count,label='neutral-finish',frames=120,actions=controls(),infos=infos))+'\n');lab.stream.flush()
    for _ in range(120):
        if hasattr(lab,'checkpoint'):lab.checkpoint()
        if all(i.get('phase')==3 and i.get('score_valid') for i in lab.env.process_infos.values()):break
        if lab.budget+60>case['frame_budget']:raise RuntimeError('paint settlement frame budget')
        lab.budget+=60
        lab.env.frame_skip=60;_,infos=lab.env.advance_settlement()
        lab.count+=1
        lab.stream.write(json.dumps(dict(step=lab.count,label='settlement',frames=60,actions=controls(),infos=infos))+'\n');lab.stream.flush()
    if not all(i.get('phase')==3 and i.get('score_valid') for i in lab.env.process_infos.values()):raise AssertionError('paired native Winners not observed')
    lab.result['native_winners']=lab.env.process_infos
    lab.result['score_peers']=[i['score'] for i in lab.env.process_infos.values()]
