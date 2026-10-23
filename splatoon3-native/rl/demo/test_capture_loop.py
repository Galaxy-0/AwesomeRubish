"""Exercise the entire recorder through asynchronous phase changes, no game."""

import argparse, json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from rl.demo import capture


def info(frame, phase):
    return dict(
        frame=100 + frame,
        phase=phase,
        position_sample_frame=100 + frame,
        position_valid=int(phase == 1),
        position=[0, 0, 0],
        heading=0,
        hp=1,
        hp_valid=int(phase == 1),
        ink=1,
        ink_valid=int(phase == 1),
        alive=1,
        alive_valid=int(phase == 1),
        score_valid=int(phase == 3),
        score=[40, 60],
        turf_valid=int(phase == 3),
        turf_ratio=[0.4, 0.6],
        own_view=dict(valid=int(phase == 1), yaw=0, pitch=0),
        hud_downs=[0] * 8,
    )


class FakeEnv:
    def __init__(self, **kwargs):
        self.possible_agents = ["player_0", "player_1"]
        self.frame = 0
        self.agents = ["player_0", "player_1"]
        self.artifacts = []
        self.closed = False
        self.process_infos = {p: info(0, 1) for p in self.agents}
        self.session = argparse.Namespace(out=Path("/private/fake-session"), hosts=[])

    def reset(self):
        return {}, self.process_infos

    def step(self, actions):
        assert set(actions) == set(self.agents), "actions sent to retired agent"
        previous = self.agents[:]
        self.frame += 1
        phases = {1: [1, 1], 2: [2, 1], 3: [2, 2]}[self.frame]
        self.process_infos = {
            f"player_{n}": info(self.frame, v) for n, v in enumerate(phases)
        }
        self.agents = [p for p in previous if self.process_infos[p]["phase"] == 1]
        return (
            {},
            {},
            {},
            {p: False for p in previous},
            {p: self.process_infos[p] for p in previous},
        )

    def advance_settlement(self):
        assert not self.agents
        self.frame += 1
        self.process_infos = {f"player_{n}": info(self.frame, 3) for n in range(2)}
        return {}, self.process_infos

    def close(self):
        self.closed = True


class LoopTests(unittest.TestCase):
    def test_complete_recording_through_asymmetric_judge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            host = root / "host"
            host.write_bytes(b"unit-test")
            host.with_suffix(".build.json").write_text(
                json.dumps(
                    dict(
                        test_feature="demonstration_capture",
                        render_mode="none",
                        direct_aim=False,
                    )
                )
            )
            out = root / "recording"
            made = []
            api = MagicMock()

            def api_update(infos):
                assert all(v["phase"] == 1 for v in infos.values()), (
                    "referee updated after InGame"
                )

            api.update.side_effect = api_update

            def create(**kw):
                e = FakeEnv(**kw)
                made.append(e)
                return e

            child = MagicMock()
            child.act.return_value = capture.neutral()
            args = argparse.Namespace(
                fixture=True,
                host=host,
                modules=root,
                source="script",
                allow_unqualified=False,
                out=out,
                opponent="policy",
                policy="unused",
                loadout="primary_only",
                timeout=60,
                resolution=None,
                present_link=0,
                opponent_stride=1,
                max_frames=None,
                pace=False,
            )
            with (
                patch.object(capture, "validate_runtime", return_value=(host, root)),
                patch.object(capture, "safe_out", return_value=out),
                patch.object(capture, "DemoEnv", side_effect=create),
                patch.object(capture, "RefereeAPI", return_value=api),
                patch.object(
                    capture.PolicySpec,
                    "load",
                    return_value=argparse.Namespace(
                        source_sha256="unit", root=root, step_timeout=1, loadout={}
                    ),
                ),
                patch.object(capture, "ControlProcess", return_value=child),
                patch.object(capture.MapAtlas, "load", return_value=MagicMock()),
            ):
                self.assertEqual(capture.run(args), 0)
            result = json.loads((out / "result.json").read_text())
            self.assertTrue(result["complete"])
            self.assertTrue(result["passed"])
            self.assertEqual(result["frames"], 4)
            rows = [json.loads(x) for x in (out / "native-barriers.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 5)
            self.assertTrue(
                all(set(r["infos"]) == {"player_0", "player_1"} for r in rows)
            )
            self.assertEqual(api.update.call_count, 2)
            self.assertTrue(made[0].closed)
            child.close.assert_called_once()
            actions = [json.loads(x) for x in (out / "inputs-per-present.jsonl").read_text().splitlines()]
            self.assertTrue(
                all(not any(a["buttons"]) for a in actions[-1]["actions"].values())
            )


if __name__ == "__main__":
    unittest.main()
