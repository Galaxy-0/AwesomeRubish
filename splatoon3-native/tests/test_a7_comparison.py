"""Comparison cannot pass merely because each individual match was valid."""
import unittest
from analyze_a7_routes import verdict


class ComparisonTests(unittest.TestCase):
    def test_score_resolution_allows_one_quantum_with_same_winner(self):
        a=dict(passed=True,native_winners=True,score_by_role=[.9,1.85],outcome='b')
        self.assertTrue(verdict(a,a|dict(score_by_role=[.9,1.9]),True,True)['passed'])
        self.assertFalse(verdict(a,a|dict(score_by_role=[.9,1.7]),True,True)['passed'])

    def test_winner_input_identity_and_native_completion_are_all_required(self):
        a=dict(passed=True,native_winners=True,score_by_role=[1.,1.],outcome='draw')
        for b,inputs,identity in [(a|dict(outcome='a'),True,True),(a,False,True),(a,True,False),
                                  (a|dict(passed=False),True,True),(a|dict(native_winners=False),True,True)]:
            with self.subTest(b=b,inputs=inputs,identity=identity):self.assertFalse(verdict(a,b,inputs,identity)['passed'])
        with self.assertRaises(ValueError):verdict(a,a,True,True,.2)
        self.assertFalse(verdict(a,dict(passed=False,score_by_role=None),True,True)['passed'])


if __name__=='__main__':unittest.main()
