"""Reject same-map or unverified continuity after the paired-game scheduling trap."""
import copy
import unittest
from audit_a7 import audit_continuous


class ContinuousAcceptanceTests(unittest.TestCase):
    def fixture(self):
        matches=[dict(passed=True,native_winners=True,void=False,host_pids=[10,11]) for _ in range(2)]
        events=[dict(phase='ingame',status=dict(generation=n,players=[dict(pid=10+p,scene=scene,last_match_phase='ingame') for p in (0,1)])) for n,scene in enumerate(('Vss_District00','Vss_Yagara'))]
        return dict(passed=True,errors=[],host_sha256='host',stages=[2,3],pool=dict(starts=1,reuses=1),matches=matches,events=events)

    def test_cross_map_paired_winners_with_real_scene_evidence(self):
        audit_continuous(self.fixture(),'host')

    def test_same_map_declared_change_and_restarted_process_are_rejected(self):
        good=self.fixture()
        for change in ('same-native-map','fresh-process','missing-winner','wrong-host'):
            c=copy.deepcopy(good)
            if change=='same-native-map':
                for p in c['events'][1]['status']['players']:p['scene']='Vss_District00'
            elif change=='fresh-process':c['matches'][1]['host_pids']=[20,21]
            elif change=='missing-winner':c['matches'][1]['native_winners']=False
            else:c['host_sha256']='other'
            with self.subTest(change=change),self.assertRaises(AssertionError):audit_continuous(c,'host')


if __name__=='__main__':unittest.main()
