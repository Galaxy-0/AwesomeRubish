"""Human-like script information boundary, timing, movement and legacy checks."""

import argparse
import math
import unittest
from unittest.mock import Mock
import numpy as np
from arena.lib.skills import SkillResult, neutral, aim_at
from .opponent52 import LEVELS, Opponent52, SaberFixture, world_stick


class Atlas:
    points = [(0, 0, 0), (0, 0, 5), (4, 0, 0), (-4, 0, 0)]

    def objective(self):
        return (0, 0, 0)

    def nearest(self, p):
        return min(range(len(self.points)), key=lambda i: math.dist(p, self.points[i]))


def view(f=0, visible=True, position=(0, 0, 10), hp=1.0, ink=1.0):
    return dict(
        frame=f,
        own=dict(
            position=[0, 0, 0],
            view_yaw=0.0,
            view_pitch=0.0,
            hp=hp,
            ink=ink,
            sample_frame=f,
            submerged=False,
            public=dict(alive=True),
        ),
        enemies=[
            dict(
                visible=visible,
                position=position,
                sample_frame=f,
                public=dict(player_id="enemy", alive=True),
            )
        ],
    )


class OpponentTests(unittest.TestCase):
    def bot(self, level="medium", seed=0):
        b = Opponent52(level, Atlas(), seed=seed)
        b.skills = Mock(move_to=lambda *args: SkillResult(neutral()), failed=False)
        return b

    def test_reaction_delays_and_seed_repeatability(self):
        means = []
        for level, p in LEVELS.items():
            delays = []
            for seed in range(50):
                b = self.bot(level, seed)
                first = None
                for f in range(0, 61, 2):
                    a = b.act(view(f))
                    if a["buttons"][0]:
                        first = f
                        break
                self.assertIsNotNone(first)
                self.assertGreaterEqual(first, p.reaction_frames - p.reaction_jitter)
                self.assertLessEqual(first, p.reaction_frames + p.reaction_jitter + 2)
                delays.append(first)
            means.append(sum(delays) / len(delays))
        self.assertGreater(means[0], means[1])
        self.assertGreaterEqual(means[1], means[2])
        a, b = self.bot(seed=7), self.bot(seed=7)
        self.assertEqual(
            [a.act(view(f)) for f in range(0, 200, 6)],
            [b.act(view(f)) for f in range(0, 200, 6)],
        )

    def test_hidden_truth_poison_never_updates_memory_or_combat_aim(self):
        b = self.bot()
        b.act(view(0))
        old = b.last_seen.copy()
        v = view(6, False, position=object())
        v["enemies"][0].update(last_seen_position=[100, 100, 100], last_seen_frame=6)
        b.act(v)
        np.testing.assert_equal(b.last_seen, old)
        self.assertEqual(b.seen_frame, 0)
        self.assertFalse(
            b.debug["fire"]
        )  # path painting is allowed, target firing is not
        self.assertEqual(b.debug["mode"], "memory_search")
        b._patrol = Mock(return_value=neutral())
        b.act(view(b.p.memory_frames + 12, False, position=object()))
        self.assertIsNone(b.last_seen)

    def test_outside_view_cone_or_stale_sample_is_not_perceived(self):
        for point in [(10, 0, 0), (0, 0, -5), (0, 0, 40)]:
            b = self.bot()
            b._patrol = Mock(return_value=neutral())
            b.act(view(position=point))
            self.assertFalse(b.debug["visible"])
        b = self.bot()
        b._patrol = Mock(return_value=neutral())
        v = view(20)
        v["enemies"][0]["sample_frame"] = 0
        b.act(v)
        self.assertFalse(b.debug["visible"])

    def test_limited_turning_and_distance_lateral_noise(self):
        b = self.bot("easy")
        own = view()["own"]
        a, e = b._look(own, [10, 1, 0], 6)
        self.assertLessEqual(
            abs(a["gyro"][2]) * 0.25 * 60, math.radians(LEVELS["easy"].yaw_degrees_s)
        )
        self.assertNotEqual(a["gyro"][2], 0)
        b.act(view(0, position=(0, 0, 6)))
        near = b.debug["aim_sigma_degrees"]
        b.act(view(6, position=(1, 0, 12)))
        self.assertGreater(b.debug["aim_sigma_degrees"], near)

    def test_all_tiers_strafe_and_never_use_sub_or_special(self):
        for level in LEVELS:
            b = self.bot(level)
            for f in range(0, 240, 6):
                a = b.act(view(f))
                self.assertGreater(math.hypot(*a["sticks"][:2]), 0)
                self.assertEqual(a["buttons"][2:4], [0, 0])
                self.assertLessEqual(max(abs(g) for g in a["gyro"]), 8)
                self.assertLessEqual(math.hypot(*a["sticks"][:2]), 1)

    def test_new_easy_motor_settings_exceed_old_hard(self):
        p = LEVELS["easy"]
        self.assertLess(p.aim_tau, 0.20)
        self.assertGreater(p.yaw_degrees_s, 200)
        self.assertLess(p.error_degrees, 2)
        self.assertLessEqual(p.reaction_frames, 10)
        self.assertLess(p.settle_frames, 9)
        self.assertGreater(p.paint_duty, 0.70)

    def test_policy_and_legacy_cadence_preserved_and_explicit_zero_rejected(self):
        from .capture import resolve_opponent_stride

        self.assertEqual(resolve_opponent_stride(None, "hard", None), 2)
        self.assertEqual(resolve_opponent_stride(None, "turret", None), 6)
        self.assertEqual(
            resolve_opponent_stride(argparse.Namespace(step_frames=12), None, None), 12
        )
        self.assertEqual(resolve_opponent_stride(None, "hard", 4), 4)
        with self.assertRaisesRegex(ValueError, "positive"):
            resolve_opponent_stride(None, "hard", 0)

    def test_far_visible_target_triggers_route_approach_not_static_strafe(self):
        b = self.bot()
        b.act(view(0, position=(0, 0, 25)))
        self.assertEqual(b.debug["mode"], "approach")
        self.assertFalse(b.debug["fire"])

    def test_approach_painting_keeps_yaw_tracking_the_visible_target(self):
        b = self.bot("hard")
        a = b.act(view(0, position=(10, 0, 25)))
        self.assertEqual(b.debug["mode"], "approach")
        self.assertGreater(a["gyro"][2], 0)  # must not be replaced by path-sweep yaw

    def test_brief_sight_break_does_not_restart_first_detection_delay(self):
        b = self.bot("hard")
        b.act(view(0))
        deadline = b.reaction_at
        b.act(view(6, False))
        b.act(view(20))
        self.assertEqual(b.reaction_at, deadline)
        self.assertEqual(b.acquired_at, 0)
        b.act(view(80, False))
        b.act(view(90))
        self.assertEqual(b.acquired_at, 90)
        self.assertGreater(b.reaction_at, 90)

    def test_idle_fixture_never_launches_or_shoots(self):
        from .capture import scripted

        for f in (0, 60, 180, 2000, 10800):
            self.assertEqual(scripted(f, "idle"), neutral())

    def test_low_health_or_ink_recovers_then_reengages(self):
        for hp, ink in [(0.2, 0.6), (1.0, 0.1)]:
            b = self.bot()
            b.act(view(30, hp=hp, ink=ink))
            self.assertTrue(b.recovering)
            a = b.act(view(60, hp=hp, ink=ink))
            self.assertEqual(a["buttons"][1], 1)
            b.act(view(90, hp=1.0, ink=0.9))
            self.assertFalse(b.recovering)

    def test_no_combat_route_paints_and_advances(self):
        b = self.bot()
        v = view(6, False)
        v["own"]["position"] = [0, 0, -30]
        b.skills.move_to = lambda *a: SkillResult(
            dict(neutral(), sticks=[0, 0.85, 0, 0])
        )
        # _patrol resets its navigator only when selecting a waypoint.
        b.patrol = [0, 0, 0]
        a = b.act(v)
        self.assertEqual(b.debug["mode"], "paint_advance")
        self.assertEqual(a["buttons"][0], 1)
        self.assertGreater(abs(a["sticks"][1]), 0)

    def test_legacy_turret_exact_action(self):
        v = view(100, position=(3, 0, 10))
        b = self.bot("turret")
        expected = aim_at(v, [3, 1, 10]).action
        expected["buttons"][0] = 1
        self.assertEqual(b.act(v), expected)
        self.assertEqual(b.act(v)["sticks"][:2], [0, 0])

    def test_camera_relative_motion_basis(self):
        self.assertEqual(world_stick((0, 1), 0, 0.5), [0, 0.5])
        self.assertAlmostEqual(world_stick((0, 1), math.pi / 2, 0.5)[0], 0.5)

    def test_dead_self_has_no_actions_and_forgets_target(self):
        b = self.bot()
        b.act(view())
        v = view(6)
        v["own"]["public"]["alive"] = False
        self.assertEqual(b.act(v), neutral())
        self.assertIsNone(b.last_seen)

    def test_hunter_never_plans_in_spawn_launcher(self):
        b = SaberFixture(Atlas())
        b.skills = Mock()
        v = view(30, False)
        v["own"]["position"] = [0, 31, 0]
        a = b.act(v)
        self.assertEqual(a["buttons"][0], 1)
        self.assertFalse(b.skills.failed)
        self.assertEqual(b.skills.path, [])
        self.assertGreaterEqual(b.landing_until, 150)

    def test_script_only_headless_gate_precedes_hardware(self):
        from .capture import run

        with self.assertRaisesRegex(ValueError, "script-fixture only"):
            run(argparse.Namespace(fixture_headless=True, source="controller"))

    def test_player_policy_rejects_controller_or_other_fixture_before_hardware(self):
        from .capture import run

        for source, replay, pattern in [
            ("controller", None, "legacy"),
            ("script", "work/replay.jsonl", "legacy"),
            ("script", None, "hunter"),
        ]:
            with self.assertRaisesRegex(ValueError, "script-only fixture"):
                run(
                    argparse.Namespace(
                        source=source,
                        fixture_player_policy="unused",
                        fixture_inputs=replay,
                        script_pattern=pattern,
                    )
                )

    def test_equipment_mask_is_after_overrides_preserves_X_and_original(self):
        from .capture import primary_actions

        original = dict(player_0=dict(neutral(), buttons=[1] * 6, observer_buttons=[1]))
        masked = primary_actions(original)
        self.assertEqual(masked["player_0"]["buttons"], [1, 1, 0, 0, 1, 1])
        self.assertEqual(masked["player_0"]["observer_buttons"], [1])
        self.assertEqual(original["player_0"]["buttons"], [1] * 6)

    def test_player_replay_preserves_launch_gyro_X_without_overwriting_opponent(self):
        from .capture import replay_actions, run

        current = dict(
            player_0=neutral(), player_1=dict(neutral(), buttons=[1, 0, 0, 0, 0, 0])
        )
        recorded = dict(
            player_0=dict(neutral(), gyro=[0.1, 0.2, 0.3], observer_buttons=[1]),
            player_1=neutral(),
        )
        result = replay_actions(current, recorded, True)
        self.assertEqual(result["player_0"], recorded["player_0"])
        self.assertEqual(result["player_1"], current["player_1"])
        self.assertEqual(replay_actions(current, recorded, False), recorded)
        with self.assertRaisesRegex(ValueError, "script-only"):
            run(argparse.Namespace(source="controller", fixture_player_replay="unused"))

    def test_hard_cover_uses_static_occlusion_from_last_seen(self):
        mesh = Mock(clear=lambda a, b: a[2] < 5)
        b = Opponent52("hard", Atlas(), mesh, 0)
        goal = b._cover_goal(view()["own"], [0, 0, 10], 0)
        self.assertIsNotNone(goal)
        self.assertIsNotNone(
            Opponent52("easy", Atlas(), mesh, 0)._cover_goal(
                view()["own"], [0, 0, 10], 0
            ),
        )
