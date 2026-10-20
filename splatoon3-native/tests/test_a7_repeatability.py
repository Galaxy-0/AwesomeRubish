"""Noise gate must reject a mean shift exceeding either route's own scatter."""
import unittest
from probe_a7_repeatability import compare

class RepeatabilityTests(unittest.TestCase):
    def test_own_scatter_can_exceed_the_old_fixed_quantum(self):
        r=compare([[1.,1.],[1.4,1.4],[1.2,1.2]],[[1.1,1.2],[1.3,1.5],[1.4,1.1]])
        self.assertTrue(r['passed']);self.assertEqual(len(r['cross_pairs']),9)
        self.assertEqual(len(r['within']['menu']['pairwise']),3)
    def test_large_shift_fails_even_with_same_winner(self):
        self.assertFalse(compare([[1.,2.],[1.1,2.1],[1.,2.]],[[2.,3.],[2.1,3.1],[2.,3.]])['passed'])
    def test_deterministic_reference_requires_equal_scores(self):
        self.assertTrue(compare([[1.,2.]]*3,[[1.,2.]]*3)['passed'])
        self.assertFalse(compare([[1.,2.]]*3,[[1.1,2.]]*3)['passed'])
    def test_reject_missing_or_nonfinite_samples(self):
        for bad in ([[1.,2.]]*2,[[float('nan'),2.]]*3):
            with self.assertRaises(ValueError):compare(bad,[[1.,2.]]*3)

if __name__=='__main__':unittest.main()
