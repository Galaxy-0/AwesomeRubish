import unittest
from arena.lib.atlas import MapAtlas
from tools.zipcaster_d3r.setup_navigation import route_view
class SetupTests(unittest.TestCase):
 def atlas(self):return MapAtlas(dict(schema='arena.map.v1',nodes=[[0,0,0,1],[1,0,0,1],[0,.01,0,1]],edges=[[1],[0],[]],regions={},spawns={},resolution=1))
 def test_close_disconnected_overlay_is_not_a_game_pose_write(self):
  atlas=self.atlas();pose=[0,.009,0];self.assertEqual(atlas.nearest(pose),2)
  with self.assertRaises(ValueError):atlas.plan(pose,[1,0,0])
  view,n=route_view(atlas,[1,0,0]);self.assertEqual(n,2);self.assertEqual(view.plan(pose,[1,0,0]),[0,1]);self.assertEqual(atlas.nearest(pose),2);self.assertIs(view.points,atlas.points)
 def test_distant_projection_is_rejected(self):
  view,_=route_view(self.atlas(),[1,0,0])
  with self.assertRaises(ValueError):view.nearest([10,0,0])
if __name__=='__main__':unittest.main()
