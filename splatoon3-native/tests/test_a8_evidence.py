"""The A8 empirical gate must reject systematic drift, not just large deltas."""
import unittest
from analyze_a8 import trajectory_comparison


class TrajectoryGateTests(unittest.TestCase):
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
