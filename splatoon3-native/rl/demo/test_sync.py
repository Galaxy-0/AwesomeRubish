"""Native import must not integrate, leak future fields, or hide missing truth."""

import json, os, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import Mock
import torch
from rl.gpu.test_env import flat, fixture_config
from rl.gpu.env import ParallelEnv, CHARGE, COOL, HP
from rl.gpu.env import SUB, YAW
from rl.demo.state_sync import NativeRebuilder, CausalIndex


def row(frame=50, age=2):
    return dict(
        frame=frame,
        infos={
            f"player_{n}": dict(
                frame=frame,
                phase=1,
                position_sample_frame=frame - age,
                position_valid=True,
                position=[float(n), 0.0, 5.0 * n],
                own_view=dict(yaw=0.0, pitch=0.0, valid=True),
                hp_valid=True,
                hp=0.7,
                ink_valid=True,
                ink=0.8,
                special_valid=True,
                special=0.2,
                heading=0.0,
                alive=True,
                referee_motion=dict(form_squid=0, ground_contact=4),
                time_valid=True,
                remaining_time=157.0,
            )
            for n in range(2)
        },
    )


class SyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        cls.tmp = tempfile.TemporaryDirectory()
        flat(os.environ["RL_STAGE0_DATA"], cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def builder(self):
        e = ParallelEnv(
            self.tmp.name,
            fixture_config(decision_frames=1, loadout_mode="primary_only"),
        )
        origins = {f"player_{n}": dict(frame=0) for n in range(2)}
        return e, NativeRebuilder(e, self.tmp.name, origins)

    def test_no_physics_and_no_hidden_simulated_weapon_truth(self):
        e, b = self.builder()
        e.state.fill_(123)
        e.shots.fill_(1)
        e.paint.fill_(1)
        e.step = Mock(side_effect=AssertionError("physics forbidden"))
        obs, q = b.observe(row())
        e.step.assert_not_called()
        self.assertTrue(
            torch.allclose(e.state[0, 0, :3], torch.tensor([0.0, 0.0, 0.0]))
        )
        self.assertEqual(e.state[0, 0, HP], 0.7)
        self.assertEqual(e.state[0, 0, CHARGE], 0)
        self.assertEqual(e.state[0, 0, COOL], 0)
        self.assertFalse(e.shots.any())
        self.assertTrue((e.paint == -1).all())
        self.assertFalse(q["dense_paint_native_valid"])
        self.assertFalse(q["projectiles_native_valid"])
        self.assertEqual(q["weapon_native_valid"], [False, False])
        self.assertEqual(obs["hud"][0, 0, 6], 157)

    def test_native_primary_bullet_requires_exact_frame_and_does_not_ghost(self):
        e, b = self.builder()
        bullet = dict(
            owner=1,
            position=[0.0, 1.0, 4.0],
            velocity=[0.0, 0.0, -3.06],
            age_frames=1,
            damage=52.0,
            kind=3,
        )
        b.projectiles = CausalIndex(
            [
                dict(
                    frame=49,
                    observer=0,
                    primary_projectile_set_qualified=True,
                    projectiles=[bullet],
                ),
                dict(
                    frame=50,
                    observer=0,
                    primary_projectile_set_qualified=True,
                    projectiles=[],
                ),
            ]
        )
        _, q = b.observe(row(50))
        self.assertTrue(q["projectiles_native_valid"])
        self.assertEqual(e.shots[0, 1, 0, 10], 1)
        self.assertEqual(e.shots[0, 1, 0, 9], 3)
        self.assertAlmostEqual(float(e.shots[0, 1, 0, 5]), -3.06, places=4)
        # Explicit release snapshot is known empty; absence next tick is unknown.
        q, _ = b.sync(row(51))
        self.assertTrue(q["projectiles_native_valid"])
        self.assertFalse(e.shots.any())
        q, _ = b.sync(row(52))
        self.assertFalse(q["projectiles_native_valid"])
        self.assertFalse(e.shots.any())

    def test_unqualified_projectile_set_is_not_imported(self):
        e, b = self.builder()
        b.projectiles = CausalIndex(
            [
                dict(
                    frame=49,
                    observer=0,
                    primary_projectile_set_qualified=False,
                    projectiles=[{}],
                )
            ]
        )
        q, _ = b.sync(row(50))
        self.assertFalse(q["projectiles_native_valid"])
        self.assertFalse(e.shots.any())

    def test_invalid_old_packet_is_not_integrated_or_marked_current(self):
        e, b = self.builder()
        q, _ = b.sync(row(age=9))
        self.assertEqual(q["state_valid"], [False, False])
        self.assertEqual(q["source_age_frames"], [9, 9])
        self.assertFalse(e.state.any())

    def test_strict_causal_cutoff_excludes_same_numbered_next_ack(self):
        e, b = self.builder()
        c = dict(frame=50, yaw=0.5, pitch=0.0, eye=[0, 3, -6], at=[0, 1, 0])
        b.camera = [CausalIndex([c]), CausalIndex([c])]
        q, override = b.sync(row(50))
        self.assertIsNone(override)
        self.assertEqual(q["camera_native_valid"], [False, False])
        q, override = b.sync(row(51))
        self.assertIsNotNone(override)
        self.assertEqual(q["camera_native_valid"], [True, True])

    def test_index_never_interpolates_future_or_extends_stale_events(self):
        i = CausalIndex([dict(frame=2, v=1), dict(frame=10, v=999)])
        self.assertEqual(i.latest(5)["v"], 1)
        self.assertIsNone(i.latest(7))
        self.assertIsNone(i.latest(1))
        self.assertEqual(i.latest(10)["v"], 999)

    def test_measured_velocity_is_held_between_repeated_native_packets(self):
        e, b = self.builder()
        b.sync(row(50, 2))
        moved = row(54, 2)
        moved["infos"]["player_0"]["position"][0] = 1.0
        b.sync(moved)
        self.assertEqual(float(e.state[0, 0, 3]), 0.25)
        repeated = row(55, 3)
        repeated["infos"]["player_0"]["position"][0] = 1.0
        q, _ = b.sync(repeated)
        self.assertEqual(float(e.state[0, 0, 3]), 0.25)
        self.assertFalse(q["entity_velocity_native_valid"])

    def test_optional_camera_override_does_not_change_default_observation(self):
        e, b = self.builder()
        one = e._observe(e.state, e.shots, e.paint, e.steps)
        two = e._observe(e.state, e.shots, e.paint, e.steps, camera_override=None)
        for k in one:
            self.assertTrue(torch.equal(one[k], two[k]), k)

    def test_visible_enemy_positive_control_and_submerged_mask(self):
        e, _ = self.builder()
        e.state[0, 0, :3] = torch.tensor([0.0, 0.0, 0.0])
        e.state[0, 1, :3] = torch.tensor([0.0, 0.0, 6.0])
        e.state[..., YAW] = 0
        visible = e._observe(e.state, e.shots, e.paint, e.steps)
        self.assertTrue(visible["entity_mask"][0, 0].any())
        e.state[0, 1, SUB] = 1
        hidden = e._observe(e.state, e.shots, e.paint, e.steps)
        self.assertFalse(hidden["entity_mask"][0, 0].any())

    def test_export_stops_at_native_timer_zero_without_any_physics(self):
        from rl.demo.bc_sync import convert_synced

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [row(f, 0) for f in range(7)]
            for r in rows[4:]:
                for i in r["infos"].values():
                    i["remaining_time"] = 0
            actions = {
                f"player_{n}": dict(sticks=[0] * 4, gyro=[0] * 3, buttons=[0] * 6)
                for n in range(2)
            }
            inputs = [
                dict(frame_interval=[f, f + 1], actions=actions) for f in range(6)
            ]
            for filename, data in [
                ("native-barriers.jsonl", rows),
                ("inputs-per-present.jsonl", inputs),
            ]:
                (root / filename).write_text(
                    "".join(json.dumps(x) + "\n" for x in data)
                )
            (root / "result.json").write_text(
                json.dumps(
                    dict(
                        weapons=[8000, 50],
                        loadout_mode="primary_only",
                        complete=True,
                        errors=[],
                        source="scripted_smoke",
                    )
                )
            )
            (root / "camera.json").write_text(
                json.dumps(dict(matrix=[[0] * 5, [0] * 5], rank=5))
            )
            cfg = fixture_config()
            keys = [
                "stick_plus5_radians_per_frame",
                "camera_horizontal_fov_degrees",
                "camera_vertical_fov_degrees",
                "camera_distance",
                "camera_target_height",
                "camera_pitch_offset_radians",
            ]
            (root / "calibration.json").write_text(
                json.dumps({k: getattr(cfg, k) for k in keys})
            )
            args = SimpleNamespace(
                cpu_threads=1,
                recording=root,
                out=root / "bc",
                allow_approximate=True,
                camera=root / "camera.json",
                calibration=root / "calibration.json",
                data=self.tmp.name,
                device="cpu",
                stride=2,
                shard_size=256,
                max_frames=None,
            )
            with (
                patch("rl.demo.bc_sync.safe_out", side_effect=Path),
                patch.object(
                    ParallelEnv,
                    "step",
                    side_effect=AssertionError("BC must not integrate physics"),
                ),
            ):
                result = convert_synced(args)
            self.assertEqual(result["samples"], 2)
            self.assertEqual(result["last_frame_exclusive"], 4)
            self.assertEqual(result["physics_steps_for_bc"], 0)
            self.assertFalse(result["ready_for_training"])


if __name__ == "__main__":
    unittest.main()
