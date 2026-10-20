"""The A8 empirical gate must reject systematic drift, not just large deltas."""
import unittest
import json
import tempfile
from pathlib import Path
from analyze_a8 import trajectory_comparison
from analyze_a8 import load_group
from analyze_a8_gpu import shared_union,category,read_stream
from analyze_a8_capacity import batch as capacity_batch


class GPUAttributionTests(unittest.TestCase):
    def row(self,kind,start,end):
        return dict(kind=kind,w=1,h=1,cfmt=0,dfmt=0,t0_tick=start,t1_tick=end)

    def test_overlapping_spans_share_union_without_double_counting(self):
        rows=[self.row('R',10,30),self.row('C',20,40)]
        covered,allocated=shared_union(rows)
        self.assertEqual(covered,30)
        self.assertEqual(allocated[category(rows[0])],15)
        self.assertEqual(allocated[category(rows[1])],15)
        self.assertEqual(sum(allocated.values()),covered)

    def test_gaps_and_zero_length_spans_do_not_create_gpu_time(self):
        rows=[self.row('R',10,20),self.row('B',20,20),self.row('C',30,40)]
        covered,allocated=shared_union(rows)
        self.assertEqual(covered,20)
        self.assertNotIn(category(rows[1]),allocated)
        self.assertEqual(sum(allocated.values()),covered)

    def test_timestamp_ticks_use_reported_frequency(self):
        header='frame\trelative\tencoder\tpass\tkind\tw\th\tcfmt\tdfmt\tdraws\tt0_tick\tt1_tick\tfrequency_hz\tspan_ms\n'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'gpu.tsv'
            path.write_text(header+'1\t600\t1\t1\tR\t1280\t720\t92\t252\t4\t24000\t48000\t24000000\t1.000000\n')
            self.assertEqual(read_stream(path)[0]['span_ms'],1)
            path.write_text(path.read_text().replace('1.000000','0.024000'))
            with self.assertRaisesRegex(ValueError,'unit mismatch'):read_stream(path)
            path.write_text(path.read_text().replace('0.024000','nan'))
            with self.assertRaisesRegex(ValueError,'invalid GPU span'):read_stream(path)


class TrajectoryGateTests(unittest.TestCase):
    def test_instrumented_data_cannot_become_performance_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'plan.json').write_text(json.dumps(dict(pass_gpu=True)))
            (root/'completed.json').write_text(json.dumps(dict(passed=True)))
            with self.assertRaisesRegex(ValueError,'diagnostic'):load_group(root)
            with self.assertRaisesRegex(ValueError,'diagnostic'):capacity_batch(root)
    def test_identical_deterministic_trajectories_pass_but_offset_fails(self):
        before=[[[0,1],[1,2]]]*3
        self.assertTrue(trajectory_comparison(before,before)['passed'])
        after=[[[.01,1],[1,2]]]*3
        self.assertFalse(trajectory_comparison(before,after)['passed'])

    def test_shift_is_compared_to_measured_internal_scatter(self):
        before=[[0,0],[1,1],[2,2]]
        measured=trajectory_comparison(before,[[1,1],[2,2],[3,3]])
        self.assertTrue(measured['passed']);self.assertEqual(measured['mean_trajectory_rms'],1)
        self.assertEqual(measured['within_maximum_rms'],2)
        self.assertFalse(trajectory_comparison(before,[[3,3],[4,4],[5,5]])['passed'])

    def test_missing_repeats_nonfinite_and_misaligned_grids_are_rejected(self):
        good=[[0,1]]*3
        for bad in ([[0,1]]*2,[[0,float('nan')]]*3,[[0]]*3):
            with self.assertRaises(ValueError):trajectory_comparison(good,bad)


if __name__=='__main__':unittest.main()
