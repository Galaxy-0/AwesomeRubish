import math,unittest
import numpy as np
from tools.zipcaster_d4.geometry import Mesh
from tools.zipcaster_d4.attack_geometry import (basis,muzzle,capsule_fraction,
    segment_box_distance,segment_cylinder_distance,contact_overlap,trace_contacts)
from tools.zipcaster_d4.contact_shape import native_shape

class AttackGeometryTests(unittest.TestCase):
    def collision(self):
        return dict(CoreIndex=0,OffsetArray=[dict(X=0,Y=0,Z=0)],
                    ParamArray=[dict(InitRadiusForField=.5,InitRadiusForPlayer=.55)])
    def test_clear_wall_does_not_grant_damage_above_body(self):
        empty=Mesh(np.empty((0,3,3)))
        points=np.array([[0,3,0],[0,3,12]],float)
        result=trace_contacts(empty,points,[0,1],[[0,0,8]]*2,0,0,self.collision())
        self.assertFalse(result['hit']);self.assertIsNone(result['core_field_time'])
    def test_player_before_wall_and_wall_before_player(self):
        wall=Mesh([[[-3,-2,5],[3,-2,5],[-3,5,5]],[[3,-2,5],[3,5,5],[-3,5,5]]])
        points=np.array([[0,1,0],[0,1,12]],float)
        front=trace_contacts(wall,points,[0,1],[[0,0,3]]*2,0,0,self.collision())
        behind=trace_contacts(wall,points,[0,1],[[0,0,8]]*2,0,0,self.collision())
        self.assertTrue(front['hit']);self.assertFalse(behind['hit'])
        self.assertLess(front['body_time'],front['core_field_time'])
    def test_finite_lifetime_does_not_extend_ray(self):
        empty=Mesh(np.empty((0,3,3)))
        result=trace_contacts(empty,[[0,1,0],[0,1,5]],[0,6],[[0,0,8]]*2,0,0,self.collision())
        self.assertFalse(result['hit']);self.assertEqual(result['lifetime_end'],6)
    def test_side_clip_and_whole_projectile_are_not_conflated(self):
        wall=Mesh([[[.7,-1,4],[1.3,-1,4],[.7,3,4]],[[1.3,-1,4],[1.3,3,4],[.7,3,4]]])
        collision=dict(CoreIndex=0,OffsetArray=[dict(X=0,Y=0,Z=0),dict(X=1,Y=0,Z=0)],ParamArray=[dict(InitRadiusForField=.1,InitRadiusForPlayer=.1)]*2)
        args=(wall,[[0,1,0],[0,1,10]],[0,6],[[1,0,8]]*2,0,0,collision)
        clipped=trace_contacts(*args);uncut=trace_contacts(*args,side_policy='core_lifetime')
        self.assertIsNone(clipped['core_field_time']);self.assertFalse(clipped['hit']);self.assertTrue(uncut['hit'])
    def test_light_muzzle_rotates_local_offset(self):
        p,_=muzzle([0,0,0],0,.7,'light')
        np.testing.assert_allclose(p,[0,math.cos(.7)+1.4*math.sin(.7),1.4*math.cos(.7)-math.sin(.7)])
        p,_=muzzle([0,0,0],0,.7,'full');np.testing.assert_allclose(p,[0,2.2,.8])
    def test_capsule_uses_native_candidate_top_1_30(self):
        self.assertIsNone(capsule_fraction([-2,1.9,0],[2,1.9,0],.55))
        self.assertIsNotNone(capsule_fraction([-2,1.8,0],[2,1.8,0],.55))
    def test_box_corner_distance_is_not_a_bounding_sphere(self):
        self.assertAlmostEqual(segment_box_distance([2,2,0],[2,2,0],[0,0,0],[1,1,1]),math.sqrt(2))
        self.assertEqual(segment_box_distance([-2,0,0],[2,0,0],[0,0,0],[1,1,1]),0)
    def test_finite_cylinder_has_flat_caps(self):
        d=segment_cylinder_distance([1.1,1.1,0],[1.1,1.1,0],[-1,0,0],[1,0,0],1)
        self.assertAlmostEqual(d,math.sqrt(.02),places=9)
        # A capsule with radius1 would falsely overlap beyond this cylinder cap.
        self.assertAlmostEqual(segment_cylinder_distance([1.8,0,0],[1.8,0,0],[-1,0,0],[1,0,0],1),.8)
    def test_oriented_box_contact_uses_real_volume(self):
        shape=dict(BoxCenter=dict(X=0,Y=0,Z=0),BoxHalfExtents=dict(X=2,Y=.2,Z=.2),HasCylinderShape=False)
        self.assertTrue(contact_overlap([0,1,0],basis(math.pi/2,0),shape,[0,0,1.8])['hit'])
        self.assertFalse(contact_overlap([0,1,0],basis(0,0),shape,[0,0,1.8])['hit'])
    def test_native_contact_forward_shift_changes_body_overlap(self):
        shape=dict(BoxCenter=dict(X=0,Y=0,Z=.7),BoxHalfExtents=dict(X=.5,Y=1.4,Z=.7),
                   HasCylinderShape=True,CylinderCenterA=dict(X=-.5,Y=0,Z=1.4),
                   CylinderCenterB=dict(X=.5,Y=0,Z=1.4),CylinderRadius=1.4)
        # Independently known shape-builder operation, not a radius increase.
        translated=native_shape(shape)
        self.assertAlmostEqual(translated['BoxCenter']['Z'],1.4)
        self.assertAlmostEqual(translated['CylinderCenterA']['Z'],2.1)
        self.assertEqual(translated['CylinderRadius'],1.4)
        self.assertAlmostEqual(shape['BoxCenter']['Z'],.7)
        self.assertFalse(contact_overlap([0,1.2,.5],basis(0,0),shape,[0,0,4.1])['hit'])
        self.assertTrue(contact_overlap([0,1.2,.5],basis(0,0),translated,[0,0,4.1])['hit'])
        self.assertFalse(contact_overlap([0,1.2,.5],basis(0,0),translated,[0,0,4.75])['hit'])

if __name__=='__main__':unittest.main()
