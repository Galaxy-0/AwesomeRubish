"""Weak example: occupy the public central high region and paint from there."""
from atlas import MapAtlas
from skills import Skills,aim_at,ink_at,neutral
import math
controller=None


def act(obs):
    global controller
    if controller is None:controller=Skills(MapAtlas.load(obs['stage_id']))
    own=obs['own'];p=own.get('position')
    if p is None or own['public']['alive'] is not True:return neutral()
    if own.get('ink') is not None and own['ink']<.18:
        a=neutral();a['buttons'][1]=1;return a
    try:r=controller.move_to(obs,controller.atlas.region('central_high'))
    except ValueError:r=None
    if r is not None and not r.done and r.status!='blocked':return r.action
    enemy=next((e for e in obs['enemies'] if e['visible']),None)
    if enemy:
        target=list(enemy['position']);target[1]+=.7;a=aim_at(obs,target);a.action['buttons'][0]=int(a.done and obs['frame']%36<12);return a.action
    yaw=(obs['frame']//180)*.5
    a=ink_at(obs,(p[0]+4*math.sin(yaw),p[1],p[2]+4*math.cos(yaw))).action
    # Release ZR regularly so the Stamper actually swings instead of holding charge.
    a['buttons'][0]=int(bool(a['buttons'][0]) and obs['frame']%36<12)
    return a
