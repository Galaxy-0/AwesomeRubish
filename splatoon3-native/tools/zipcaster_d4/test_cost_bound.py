import unittest
from tools.zipcaster_d4.calibration_plan_v4 import lower_bound


class CostBoundTests(unittest.TestCase):
    def test_contact_bound_already_includes_larger_first_hit(self):
        for speed in [40,60,129]:
            b=lower_bound(speed)
            self.assertAlmostEqual(b['global_cost_lower_bound'],(20+speed+8)/600+.078)
            self.assertGreater(b['one_or_more_hooks_lower_bound'],b['global_cost_lower_bound'])
    def test20f_cannot_credit_an_unfinished_full_charge(self):
        b=lower_bound(20)
        self.assertNotIn('full1',b['program_cost_lower_bounds'])
        self.assertAlmostEqual(b['global_cost_lower_bound'],(20+20+45)/600+2*(.052/1.5))


if __name__=='__main__':unittest.main()
