import unittest
from probe_a7_return import branch


class ReturnBranchTests(unittest.TestCase):
    def test_only_decides_after_this_return_and_state31(self):
        self.assertIsNone(branch('A7_NET_ROOT state=34\n'))
        self.assertIsNone(branch('A7_NET_ROOT state=34\nA7_REPEAT request=LobbyLocal\nA7_NET_ROOT state=31\n'))

    def test_records_first_decisive_transition(self):
        self.assertEqual(branch('A7_REPEAT request=LobbyLocal\nA7_NET_ROOT state=31\nA7_NET_ROOT state=34\nA7_NET_ROOT state=33'),34)
        self.assertEqual(branch('A7_REPEAT request=LobbyLocal\nA7_NET_ROOT state=31\nA7_NET_ROOT state=33\nA7_NET_ROOT state=30'),33)

    def test_old_return_does_not_decide_new_generation(self):
        self.assertIsNone(branch('A7_REPEAT request=LobbyLocal\nA7_NET_ROOT state=31\nA7_NET_ROOT state=34\nA7_REPEAT request=LobbyLocal\nA7_NET_ROOT state=31\n'))


if __name__=='__main__':unittest.main()
