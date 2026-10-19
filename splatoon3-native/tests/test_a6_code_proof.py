#!/usr/bin/env python3
"""Unrelated changes may reuse evidence; shared/helper changes may not."""
import unittest
from a6_code_proof import operation_digest

SOURCE='''A=1
B=2
class Plan:
    def value(self):return A
def charge():return Plan().value()
def light(period=B):return period
'''


class ProofScope(unittest.TestCase):
    def test_unrelated_constant_and_operation_do_not_invalidate_charge(self):
        changed=SOURCE.replace('B=2','B=3')
        self.assertEqual(operation_digest(SOURCE,['charge']),operation_digest(changed,['charge']))
        self.assertNotEqual(operation_digest(SOURCE,['light']),operation_digest(changed,['light']))

    def test_shared_controller_change_invalidates(self):
        changed=SOURCE.replace('return A','return A+1')
        self.assertNotEqual(operation_digest(SOURCE,['charge']),operation_digest(changed,['charge']))

    def test_eager_side_effect_is_not_reusable(self):
        with self.assertRaises(ValueError):operation_digest(SOURCE+'print(A)\n',['charge'])


if __name__=='__main__':unittest.main()
