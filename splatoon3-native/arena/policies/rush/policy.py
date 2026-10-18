"""Weak example: walk straight toward the Turf center, fire at visible peers."""
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
    visible=next((e for e in obs['enemies'] if e['visible']),None)
    goal=visible['position'] if visible else controller.objective()
    try:r=controller.move_to(obs,goal)
    except ValueError:r=None
    if visible:
        target=list(goal);target[1]+=.7;aim=aim_at(obs,target)
        a=r.action if r is not None else neutral();a['sticks'][2:]=aim.action['sticks'][2:];a['gyro']=aim.action['gyro']
        a['buttons'][0]=int(aim.done and obs['frame']%36<12);return a
    if r is not None and not r.done and r.status!='blocked':return r.action
    yaw=own.get('view_yaw') or 0.
    a=ink_at(obs,(p[0]+4*math.sin(yaw),p[1],p[2]+4*math.cos(yaw))).action
    # Release ZR regularly so the Stamper actually swings instead of holding charge.
    a['buttons'][0]=int(bool(a['buttons'][0]) and obs['frame']%36<12)
    return a
