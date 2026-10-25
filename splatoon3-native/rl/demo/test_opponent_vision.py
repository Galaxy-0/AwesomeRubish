"""Camera-only FOV still needs LOS/freshness and hides stationary submerged foes."""

from dataclasses import replace
import math
import unittest
from arena.geometry import CollisionMesh, GeometricVision, VisionConfig
from arena.referee import PlayerTruth, RefereeSnapshot
from arena.visibility import PolicyProjector
from .opponent_vision import CameraVision


class CameraVisionTests(unittest.TestCase):
    def truth(self, camera=0):
        own = PlayerTruth(
            "p1",
            1,
            50,
            True,
            (0, 0, 0),
            math.pi,
            1.0,
            1.0,
            False,
            10,
            False,
            False,
            camera,
            0.0,
        )
        target = replace(own, player_id="p0", team=0, position=(0, 0, 10))
        return RefereeSnapshot("demo", 10, (own, target))

    def mesh(self, wall=False):
        triangles = [[[-20, -1, -20], [20, -1, -20], [0, -1, 20]]]
        if wall:
            triangles += [
                [[-20, -1, 5], [20, -1, 5], [20, 8, 5]],
                [[-20, -1, 5], [20, 8, 5], [-20, 8, 5]],
            ]
        return CollisionMesh(triangles)

    def visible(self, truth, wall=False):
        vision = CameraVision(
            self.mesh(wall), VisionConfig(half_fov_degrees=43, max_distance=35)
        )
        return (
            PolicyProjector("demo")
            .observe(truth, "p1", vision.witnesses(truth, "p1"))
            .enemies[0]
        )

    def test_turned_camera_is_not_double_filtered_by_body(self):
        t = self.truth()
        self.assertFalse(GeometricVision(self.mesh()).witnesses(t, "p1")[0].in_fov)
        self.assertTrue(self.visible(t).visible)
        self.assertEqual(t.players[0].heading, math.pi)  # original truth untouched

    def test_outside_camera_wall_unknown_camera_and_submerged_are_hidden(self):
        for truth, wall in [
            (self.truth(math.pi), False),
            (self.truth(), True),
            (self.truth(None), False),
        ]:
            e = self.visible(truth, wall)
            self.assertFalse(e.visible)
            self.assertIsNone(e.position)
        t = self.truth()
        for changes in (
            dict(submerged=True, motion_visible=False),
            dict(sample_frame=0),
        ):
            t2 = replace(t, players=(t.players[0], replace(t.players[1], **changes)))
            self.assertIsNone(self.visible(t2).position)
