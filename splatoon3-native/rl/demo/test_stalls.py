"""Offline timing and warm coverage regressions, no native game required."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from .stall_report import summarize
from .warmup import assemble, collect_shaders, wait_ready, pack


class StallTests(unittest.TestCase):
    def test_warm_pack_preserves_both_recording_branches_and_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed.tsv"
            seed.write_text("S\tseed\t0\n")
            for name, parent in (("base", None), ("a", "base"), ("b", "base")):
                p = root / name
                p.mkdir()
                (p / "warm-0.tsv").write_text(f"S\t{name}\t0\n")
                (p / "result.json").write_text(
                    json.dumps(
                        dict(
                            session=str(p),
                            warm_from=str(root / parent) if parent else None,
                        )
                    )
                )
            before = (root / "a/warm-0.tsv").read_bytes()
            r = pack([root / "a", root / "b"], root / "pack", seed)
            self.assertEqual(r["audits"][0]["counts"]["S"], 4)
            self.assertEqual((root / "a/warm-0.tsv").read_bytes(), before)
            self.assertNotIn("passed", r)
            with self.assertRaises(ValueError):
                pack([root / "a"], root / "pack", seed)

    def test_ack_vs_client_work_and_tail_definition(self):
        rows = [
            dict(frame=i, sample_ns=s, send_ns=s + 1_000_000, ack_ns=s + ack)
            for i, s, ack in [
                (1, 0, 10_000_000),
                (2, 20_000_000, 210_000_000),
                (3, 240_000_000, 10_000_000),
            ]
        ]
        r = summarize(rows)
        self.assertEqual(r["over_ms"]["100"], 1)
        self.assertEqual(r["over_ms"]["200"], 1)
        self.assertEqual(r["ack_ms"]["max"], 209)
        self.assertEqual(r["input_processing_ms"]["max"], 1)
        self.assertAlmostEqual(r["intervals"]["one_percent_low_fps"], 1000 / 220)

    def test_manifest_provenance_union_and_original_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed.tsv"
            seed.write_text("# seed\nS\ta\t0\n")
            for n in range(2):
                (root / f"player-{n}").mkdir()
            a, b = root / "player-0/pso_user.tsv", root / "player-1/pso_user.tsv"
            a.write_text("S\ta\t0\nR\t1234\n")
            b.write_text("S\tb\t1\nR\t1234\n")
            before = [p.read_bytes() for p in (seed, a, b)]
            audit = assemble(seed, [root], 0, root / "out.tsv")
            self.assertEqual(audit["counts"], dict(S=2, R=1, C=0))
            self.assertEqual([p.read_bytes() for p in (seed, a, b)], before)
            self.assertEqual(json.loads((root / "out.json").read_text())["records"], 3)
            b.write_text("wrong format\n")
            with self.assertRaises(ValueError):
                assemble(seed, [root], 0, root / "bad.tsv")

    def test_historical_shader_only_coverage_does_not_import_old_pipelines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "corpus"
            corpus.mkdir()
            (corpus / "pso_user.tsv").write_text("S\told\t1\nR\tignored\n")
            extra = root / "shaders.tsv"
            self.assertEqual(collect_shaders(corpus, extra)["shaders"], 1)
            self.assertEqual(extra.read_text(), "S\told\t1\n")
            with self.assertRaises(ValueError):
                collect_shaders(corpus, extra)
            seed = root / "seed.tsv"
            seed.write_text("S\tnew\t0\nR\tcurrent\n")
            r = assemble(seed, [], 0, root / "out.tsv", extra)
            self.assertEqual(r["counts"], dict(S=2, R=1, C=0))
            extra.write_text("R\told\n")
            with self.assertRaises(ValueError):
                assemble(seed, [], 0, root / "bad.tsv", extra)

    def test_warm_ready_requires_both_native_completion_records_and_is_cancellable(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hosts = []
            for n in (0, 1):
                d = root / str(n)
                d.mkdir()
                (d / "host.log").write_text("管线预热清单\n")
                hosts.append((n, Mock(poll=lambda: None), d))

            def completed(_):
                for _, _, d in hosts:
                    (d / "host.log").write_text("管线预热完成：done\n")

            with patch("rl.demo.warmup.time.sleep", side_effect=completed) as sleep:
                result = wait_ready(hosts, 1)
                self.assertTrue(result["ready"])
                sleep.assert_called_once()
            with self.assertRaises(InterruptedError):
                wait_ready(hosts, 1, cancelled=lambda: True)
            (hosts[1][2] / "host.log").write_text("still compiling\n")
            with self.assertRaises(TimeoutError):
                wait_ready(hosts, 0)
            hosts[1][1].poll = lambda: 1
            with self.assertRaises(RuntimeError):
                wait_ready(hosts, 1)
