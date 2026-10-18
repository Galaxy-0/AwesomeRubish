#!/usr/bin/env python3
"""Geometry/visibility behavior fixtures; native screenshots have a separate gate."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.geometry import CollisionMesh,GeometricVision,VisionConfig
from arena.visibility import PolicyProjector
from test_a3_components import snapshot


def wall(height=4):return CollisionMesh([[[-10,0,5],[10,0,5],[10,height,5]],[[-10,0,5],[10,height,5],[-10,height,5]]])


class GeometryTest(unittest.TestCase):
    def state(self):
        s=snapshot();a=replace(s.players[0],position=(0.,0.,0.),heading=0.,form_squid=False)
        b=replace(s.players[1],position=(0.,0.,10.),form_squid=False)
        return replace(s,players=(a,b))

    def visible(self,s,mesh,config=VisionConfig()):
        w=GeometricVision(mesh,config).witnesses(s,'a')
        return PolicyProjector('match').observe(s,'a',w).enemies[0].visible

    def test_wall_blocks_both_directions_and_far_wall_does_not(self):
        m=wall();self.assertFalse(m.clear((0,1,0),(0,1,10)))
        self.assertFalse(m.clear((0,1,10),(0,1,0)))
        self.assertTrue(m.clear((0,1,0),(0,1,4)))
        self.assertFalse(self.visible(self.state(),m))

    def test_one_body_point_above_low_cover_is_enough(self):
        self.assertTrue(self.visible(self.state(),wall(.95)))

    def test_back_and_range_and_unknown_observer_form(self):
        s=self.state();m=wall(.1)
        self.assertTrue(self.visible(s,m))
        self.assertFalse(self.visible(replace(s,players=(replace(s.players[0],heading=3.14159),s.players[1])),m))
        self.assertFalse(self.visible(s,m,VisionConfig(max_distance=9)))
        self.assertFalse(self.visible(replace(s,players=(replace(s.players[0],form_squid=None),s.players[1])),m))

    def test_submerged_stationary_hidden_but_splash_and_jump_visible(self):
        s=self.state();m=wall(.1);a,b=s.players
        hidden=replace(s,players=(a,replace(b,submerged=True,form_squid=True,motion_visible=False)))
        self.assertFalse(self.visible(hidden,m))
        self.assertTrue(self.visible(replace(hidden,players=(a,replace(hidden.players[1],motion_visible=True))),m))
        self.assertTrue(self.visible(replace(s,players=(a,replace(b,submerged=False,form_squid=True))),m))


if __name__=='__main__':unittest.main()
