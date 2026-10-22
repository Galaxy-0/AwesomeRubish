import unittest
import numpy as np
from tools.zipcaster_d4.contact_field import triangle_box,triangle_cylinder

class FieldShapeTests(unittest.TestCase):
    def test_triangle_interior_can_intersect_without_any_vertex_inside(self):
        triangle=np.array([[0,-4,-4],[0,4,-4],[0,0,4]],float)
        self.assertTrue(triangle_box(triangle,np.zeros(3),np.ones(3)))
        self.assertTrue(triangle_cylinder(triangle,np.array([-.5,0,0]),np.array([.5,0,0]),1))
    def test_flat_end_does_not_gain_a_sphere_cap(self):
        triangle=np.array([[.7,-.2,-.2],[.7,.2,-.2],[.7,0,.2]])
        self.assertFalse(triangle_cylinder(triangle,np.array([-.5,0,0]),np.array([.5,0,0]),1))
    def test_axial_slab_clipping_finds_crossing_triangle(self):
        self.assertTrue(triangle_cylinder(np.array([[-3,0,0],[3,.2,0],[3,0,.2]]),np.array([-.5,0,0]),np.array([.5,0,0]),1))
    def test_aabb_overlap_is_insufficient_for_triangle_box(self):
        triangle=np.array([[3,0,0],[0,3,0],[3,3,0]],float)
        self.assertFalse(triangle_box(triangle,np.zeros(3),np.ones(3)))

if __name__=='__main__':unittest.main()
