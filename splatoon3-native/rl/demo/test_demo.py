"""No-game checks for demonstration privacy, action labels and formal rejection."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import torch
from rl.demo.capture import safe_out, summary, trace
from rl.demo.convert import quantize
from rl.gpu.test_env import fixture_config
from rl.gpu.stage1.controller import physical
from rl.native_start import validate_runtime


class DemoTests(unittest.TestCase):
    def test_toggle_roundtrip(self):
        cfg = fixture_config()
        cam = dict(matrix=[[-0.064, 0, 0, 0, 0.25], [0, 0.012, -0.14, 0, 0]])
        prev = [0, 4, 4, 0, 0, 0, 0, 0]
        for buttons in [
            [1, 0, 0, 0, 0, 0],
            [1, 1, 0, 0, 0, 0],
            [0, 1, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 0],
        ]:
            a = dict(sticks=[0, 0.8, 0.1, 0], gyro=[0, 0, 0.02], buttons=buttons)
            lv, cmd, e = quantize(a, cfg, cam, prev)
            got = physical(torch.tensor(cmd), torch.tensor(prev), "toggle")
            self.assertEqual(got.tolist(), lv)
            prev = lv
            self.assertLess(e["move_l2"], 0.3)

    def test_camera_sign_and_clipping(self):
        cfg = fixture_config()
        cam = dict(matrix=[[-0.064, 0, 0, 0, 0.25], [0, 0.012, -0.14, 0, 0]])
        prev = [0, 4, 4, 0, 0, 0, 0, 0]

        def q(sticks, gyro):
            return quantize(
                dict(sticks=sticks, gyro=gyro, buttons=[0] * 6), cfg, cam, prev
            )

        self.assertLess(q([0, 0, 1, 0], [0, 0, 0])[0][1], 4)
        self.assertGreater(q([0, 0, 0, 0], [0, 0, 1])[0][1], 4)
        self.assertTrue(q([0, 0, -1, 0], [0, 0, 1])[2]["camera_clipped"][0])

    def test_output_is_private(self):
        with self.assertRaises(ValueError):
            safe_out("/tmp/public-demo")

    def test_formal_flag_rejected_before_files(self):
        with patch.dict(os.environ, {"DM_TEST_DEMO": "1"}):
            with self.assertRaisesRegex(ValueError, "forbidden"):
                validate_runtime("missing", "missing")
            from arena.runner import run_match

            with self.assertRaisesRegex(ValueError, "forbidden"):
                run_match({})
            from arena.t1 import run_round

            with self.assertRaisesRegex(ValueError, "forbidden"):
                run_round(None, None, 0, None)

    def test_demo_host_rejected_without_flag(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "host"
            p.with_suffix(".build.json").write_text(
                json.dumps(dict(test_feature="demonstration_capture"))
            )
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, "forbidden"):
                    validate_runtime(p, Path(d))

    def test_summary_does_not_overwrite_frame_counter(self):
        i = dict(frame=12, score_valid=0, turf_valid=0)
        self.assertNotIn("frames", summary({"p": i}, {"p": dict(frame=2)}))
        self.assertEqual(
            summary({"p": i}, {"p": dict(frame=2)})["frames_by_role"]["p"], 10
        )

    def test_partial_trace_retains_sample_clock(self):
        info = dict(
            frame=102,
            position_sample_frame=100,
            position_valid=1,
            position=[1, 2, 3],
            hp_valid=1,
            hp=1,
            ink_valid=1,
            ink=0.8,
            alive_valid=1,
            alive=1,
            own_view=dict(valid=1, yaw=0.1, pitch=0.2),
        )
        rows = [
            dict(frame=0, infos={"player_0": info, "player_1": info}),
            dict(frame=1, infos={"player_0": info, "player_1": info}),
        ]
        with tempfile.TemporaryDirectory() as d:
            trace(rows, [], Path(d))
            r = json.loads((Path(d) / "trace.json").read_text())
            self.assertEqual(r["players"][0]["states"][0][1], -2)

    def test_physical_gyro_does_not_clip_to_one_turn(self):
        from rl.demo.protocol import DemoClient
        from collections import deque

        class Sink:
            def sendall(self, data):
                self.data = data

        c = object.__new__(DemoClient)
        c.socket = Sink()
        c.sequence = 0
        c.pending = deque()
        c.send_step(dict(sticks=[0] * 4, gyro=[2.5, 0, 0], buttons=[0] * 6), 1)
        self.assertIn(b"2.5", c.socket.data)
        with self.assertRaises(ValueError):
            c.send_step(dict(sticks=[0] * 4, gyro=[9, 0, 0], buttons=[0] * 6), 1)

    def test_human_X_is_native_bit2_and_not_a_BC_action(self):
        from collections import deque
        from .protocol import DemoClient, DemoEnv
        from .capture import as_native, scripted
        from rl.env import NativeParallelEnv

        c = object.__new__(DemoClient)
        c.socket = type("Sink", (), {"sendall": lambda self, data: setattr(self, "data", data)})()
        c.sequence, c.pending = 0, deque()
        action = scripted(600, "minimap")
        self.assertEqual(scripted(900, "minimap")["observer_buttons"], [1])
        self.assertEqual(scripted(1200, "minimap")["observer_buttons"], [0])
        c.send_step(action, 1)
        self.assertEqual(c.socket.data.split()[3], b"4")
        native = as_native(action)
        self.assertTrue(DemoEnv().action_space("player_0").contains(native))
        self.assertFalse(NativeParallelEnv().action_space("player_0").contains(native))
        self.assertEqual(len(action["buttons"]), 6)
        cfg = fixture_config()
        cam = dict(matrix=[[0] * 5, [0] * 5])
        x = quantize(action, cfg, cam, [0] * 8)
        action["observer_buttons"] = [0]
        y = quantize(action, cfg, cam, [0] * 8)
        self.assertEqual(x[:2], y[:2])
        self.assertTrue(x[2]["unrepresented_X"])
        self.assertFalse(y[2]["unrepresented_X"])
        for bad in ([2], [0, 1], [float("nan")]):
            with self.assertRaises(ValueError):
                c.send_step(dict(action, observer_buttons=bad), 1)

    def test_asymmetric_settlement_uses_live_agents_but_retains_both(self):
        from rl.demo.protocol import DemoEnv
        from rl.demo.capture import as_native

        e = DemoEnv(players=2, reward_fn=None)
        e.agents = ["player_1"]
        e.observations = {}
        infos = {"player_0": dict(phase=3), "player_1": dict(phase=2)}

        def advance(actions):
            self.assertEqual(set(actions), {"player_1"})
            e.process_infos = infos
            return {k: {} for k in infos}, infos

        with patch.object(e, "_advance", advance):
            e.step(
                {
                    p: as_native(dict(sticks=[0] * 4, gyro=[0] * 3, buttons=[0] * 6))
                    for p in e.agents
                }
            )
        self.assertEqual(set(e.process_infos), {"player_0", "player_1"})
        self.assertFalse(e.agents)

    def test_controller_sdl_sensor_event_layout(self):
        import struct

        raw = struct.pack("<IIIIfff4xQ", 0x659, 1, 0, 2, 0.1, 0.2, 0.3, 12345)
        self.assertEqual(len(raw), 40)
        self.assertEqual(struct.unpack_from("<IIIIfff4xQ", raw)[-1], 12345)


if __name__ == "__main__":
    unittest.main()
