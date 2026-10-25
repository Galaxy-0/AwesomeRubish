"""Native metric reducer: count fatal damage and preserve unknown denominators."""

import json
from pathlib import Path
import tempfile
import unittest
from .opponent_report import analyze


class ReportTests(unittest.TestCase):
    def fixture(self, root, shots=True):
        (root / "result.json").write_text(
            json.dumps(
                dict(
                    frames=240,
                    complete=True,
                    errors=[],
                    opponent_level="easy",
                    opponent_seed=0,
                    turf_ratio_by_role=dict(player_1=[0.11, 0.2]),
                    hud_downs=dict(player_1=[1, 0]),
                )
            )
        )
        rows = []
        for f in range(241):
            infos = {}
            for n in range(2):
                hp = 1.0 if n or f < 200 else 0.48 if f < 209 else 0.0
                ink = (
                    1.0
                    if not shots or n == 0 or f < 197
                    else 0.985
                    if f < 206
                    else 0.97
                )
                infos[f"player_{n}"] = dict(
                    frame=f,
                    position_sample_frame=f,
                    position_valid=1,
                    position=[0, 0, 10 * n],
                    hp_valid=1,
                    hp=hp,
                    ink_valid=1,
                    ink=ink,
                    alive=bool(n or f < 209),
                    alive_valid=1,
                )
            rows.append(dict(frame=f, infos=infos))
        (root / "native-barriers.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows)
        )
        d = [
            dict(frame=f, mode="engage", fire=True, visible=True, acquired_at=180)
            for f in range(180, 241, 6)
        ]
        (root / "opponent-decisions.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in d)
        )
        a = dict(sticks=[0, 0.65, 0, 0], gyro=[0, 0, 0], buttons=[1, 0, 0, 0, 0, 0])
        (root / "inputs-per-present.jsonl").write_text(
            "".join(
                json.dumps(dict(actions=dict(player_1=a))) + "\n" for _ in range(240)
            )
        )

    def test_fatal_hit_is_not_lost_and_turf_uses_own_perspective(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            r = analyze(root)
            self.assertEqual(r["combat_shots_from_native_ink"], 2)
            self.assertEqual(r["likely_bullet_damage_edges"], 2)
            self.assertEqual(r["hit_fraction_proxy"], 1.0)
            self.assertAlmostEqual(r["damage_to_player"], 100)
            self.assertEqual(r["opponent_turf_percent"], 11)
            self.assertTrue(r["engagements"][0]["censored"])

    def test_no_native_shots_is_unknown_not_zero_accuracy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, shots=False)
            r = analyze(root)
            self.assertIsNone(r["hit_fraction_proxy"])
            self.assertEqual(r["combat_shots_from_native_ink"], 0)
            self.assertEqual(r["likely_bullet_damage_edges"], 0)

    def test_damage_edges_cannot_reuse_a_single_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            path = root / "native-barriers.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            for row in rows:
                if row["frame"] >= 197:
                    row["infos"]["player_1"]["ink"] = 0.985
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            r = analyze(root)
            self.assertEqual(r["combat_shots_from_native_ink"], 1)
            self.assertEqual(r["likely_bullet_damage_edges"], 1)
            self.assertEqual(r["hit_fraction_proxy"], 1.0)

    def test_hud_uses_native_slot_mapping_not_observer_or_list_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            path = root / "native-barriers.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[-1]["infos"]["player_1"].update(
                hud_slot_agents={"0": "player_1", "1": "player_0"},
                hud_counter_valid=[1, 1, 0, 0, 0, 0, 0, 0],
                hud_downs=[3, 7, 0, 0, 0, 0, 0, 0],
            )
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            r = analyze(root)
            self.assertEqual(
                r["hud_downs_by_player_from_opponent_view"],
                {"player_0": 7, "player_1": 3},
            )
