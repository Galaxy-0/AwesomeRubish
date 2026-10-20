"""Owned native evidence must include both A2 rounds and reject foreign rooms."""
import unittest
from run_native_regression import owns_result

class EvidenceTests(unittest.TestCase):
    def test_rounds_are_owned_and_foreign_rounds_are_rejected(self):
        owned={'room-a','room-b'}
        self.assertTrue(owns_result({'rounds':[{'session':'room-a'},{'session':'room-b'}]},owned,set()))
        self.assertFalse(owns_result({'rounds':[{'session':'foreign'}]},owned,set()))
        self.assertFalse(owns_result({'rounds':[{'passed':True}]},owned,set()))
    def test_direct_and_linked_parent_evidence(self):
        self.assertTrue(owns_result({'session':'room-a'},{'room-a'},set()))
        self.assertTrue(owns_result({'maps':[{'evidence':'child.json'}]},set(),{'child.json'}))
        self.assertFalse(owns_result({'native_evidence':'foreign.json'},set(),{'child.json'}))

if __name__=='__main__':unittest.main()
