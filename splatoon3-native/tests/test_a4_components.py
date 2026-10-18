#!/usr/bin/env python3
"""Public controller / conservative navigation regression, without game assets."""
import math
from pathlib import Path
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'arena/lib'))
from atlas import MapAtlas
from skills import Skills,aim_at,ink_at
from tools.build_arena_maps import graph


def observation(position=(0.,0.,0.),yaw=0.,pitch=0.,frame=10,**changes):
    own=dict(public=dict(alive=True),position=list(position),sample_frame=frame,
             view_yaw=yaw,view_pitch=pitch,ink=1.,submerged=False)
    own.update(changes)
    return dict(frame=frame,own=own)


def quad(x0,x1,z0,z1,y):
    a=(x0,y,z0);b=(x0,y,z1);c=(x1,y,z1);d=(x1,y,z0)
    return [[a,b,c],[a,c,d]]


class ControllerTests(unittest.TestCase):
    def test_aim_wrap_and_pitch_sign(self):
        r=aim_at(observation(),(10,1.1,0))
        self.assertLess(r.action['sticks'][2],0)
        self.assertEqual(r.action['sticks'][:2],[0.,0.])
        self.assertLess(aim_at(observation(),(0,3,10)).action['gyro'][0],0)
        self.assertTrue(aim_at(observation(),(0,1.1,10)).done)
        r=aim_at(observation(yaw=math.pi-.01),(-.1,1.1,-10))
        self.assertTrue(r.done)

    def test_missing_stale_dead_never_fire(self):
        for kwargs in (dict(sample_frame=None),dict(sample_frame=1),dict(view_yaw=None),dict(public=dict(alive=False))):
            r=ink_at(observation(**kwargs),(0,0,4))
            self.assertEqual(r.status,'unavailable')
            self.assertFalse(any(r.action['buttons']))
        self.assertEqual(ink_at(observation(ink=.01),(0,0,4)).status,'refilling')

    def test_own_view_only_and_invalid_native_view_unknown(self):
        from dataclasses import replace
        from arena.referee import PlayerTruth,RefereeSnapshot
        from arena.policy import encode_policy
        from arena.visibility import PolicyProjector
        from arena.native_referee import NativeRefereeAdapter
        own=PlayerTruth('a',0,8000,True,(0.,0.,0.),0.,1.,1.,False,10,False,False,.2,.1)
        enemy=replace(own,player_id='b',team=1,view_yaw=2.,view_pitch=-.5)
        truth=RefereeSnapshot('m',10,(own,enemy))
        import json
        wire=encode_policy(PolicyProjector('m',stage_id=1).observe(truth,'a'))
        data=json.loads(wire)
        self.assertEqual(data['own']['view_yaw'],.2)
        self.assertEqual(data['stage_id'],1)
        self.assertNotIn('view_yaw',data['enemies'][0])
        changed=replace(truth,players=(own,replace(enemy,view_yaw=-2.,view_pitch=.9)))
        self.assertEqual(wire,encode_policy(PolicyProjector('m',stage_id=1).observe(changed,'a')))
        adapter=NativeRefereeAdapter('m',{'a':{'frame':0}},{'a':8000},{'a':0})
        state=adapter.snapshot({'a':dict(frame=10,phase=1,position_sample_frame=10,own_view=dict(valid=0,yaw=1.,pitch=.2))})
        self.assertIsNone(state.players[0].view_yaw)
        self.assertIsNone(state.players[0].view_pitch)

    def test_direction_path_arrival_and_timeout(self):
        atlas=MapAtlas(dict(schema='arena.map.v1',nodes=[[0,0,0,1],[0,0,1,1],[0,0,2,1]],
                            edges=[[1],[0,2],[1]],regions={'center':{'center':[0,0,1]}},spawns={},resolution=1))
        s=Skills(atlas);r=s.move_to(observation(),(0,0,2))
        self.assertGreater(r.action['sticks'][1],0)
        near=s.move_to(observation(position=(0,0,1.25),frame=11),(0,0,2))
        self.assertGreater(abs(near.action['sticks'][1]),.8)
        self.assertEqual(s.move_to(observation(position=(0,0,1.25),frame=200),(0,0,2)).status,'blocked')
        self.assertTrue(s.move_to(observation(position=(0,0,2),frame=201),(0,0,2)).done)
        self.assertEqual(s.objective(),(0,0,1))

    def test_multiple_layers_ledge_direction_and_non_swim_material(self):
        floor=quad(-2,2,-2,2,0)+quad(-2,2,-2,2,3)
        nodes,edges=graph(np.array(floor,float),np.array([True,True,False,False]))
        self.assertTrue(any(n[:3]==[0.,0.,0.] for n in nodes))
        self.assertTrue(any(n[:3]==[0.,3.,0.] and n[3]==0 for n in nodes))
        for i,links in enumerate(edges):
            self.assertTrue(all(nodes[j][1]-nodes[i][1]<=.7 for j in links))
        # A geometrically swim-capable material is not evidence of current ink.
        self.assertNotIn('paint',MapAtlas.__dict__)

    def test_wall_and_diagonal_corner_are_not_shortcuts(self):
        floor=quad(-3,3,-3,3,0)
        wall=[[(0.,0.,-4.),(0.,3.,-4.),(0.,3.,4.)],[(0.,0.,-4.),(0.,3.,4.),(0.,0.,4.)]]
        nodes,edges=graph(np.array(floor+wall),np.ones(4,bool))
        atlas=MapAtlas(dict(schema='arena.map.v1',nodes=nodes,edges=edges,regions={},spawns={},resolution=1))
        with self.assertRaises(ValueError):atlas.route((-2,0,0),(2,0,0))


if __name__=='__main__':unittest.main()
