"""Rank statistics, role mapping and complete-grid guard, all offline."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .ranking import scenarios
from .ranking_report import tau_b,native_game,summary,collect,compare_pair
from .parameters import sha256


class RankingTests(unittest.TestCase):
    def test_tau_ties_and_discordant_pairs(self):
        self.assertEqual(tau_b([1,2,3],[1,2,3])['tau_b'],1.)
        self.assertEqual(tau_b([1,2,3],[3,2,1])['tau_b'],-1.)
        self.assertAlmostEqual(tau_b([1,1,3],[1,2,3])['tau_b'],2/(6**.5))
        self.assertEqual(tau_b([1,1,3],[1,1,3])['tau_b'],1.)
        self.assertIsNone(tau_b([1,1,1],[1,2,3])['tau_b'])

    def test_plan_covers_six_fixed_and_thirty_sensitivity(self):
        grid=scenarios()
        self.assertEqual(len(grid),36)
        self.assertEqual(sum(g['cohort']=='fixed' for g in grid),6)
        self.assertEqual(len({(g['stage'],g['swap'],g['seed']) for g in grid}),36)

    def test_native_policy_order_is_independent_of_host_seat(self):
        from .ranking_sources import mapped_match
        raw=dict(role_to_policy=[1,0],stage=1,outcome='a',score_by_role=[12.,17.],
                 hud_by_role={f'player_{i}':dict(enemy_hud_downs=i,own_environmental_downs=0) for i in (0,1)},
                 artifacts='fixture',session='fixture')
        mapped=mapped_match(raw)
        self.assertEqual(mapped['turf_pp'],[17.,12.])
        game=native_game(mapped)
        self.assertTrue(game['swap']);self.assertEqual(game['winner'],0)

    def test_weighted_summary_handles_draws_and_zero_weight_strata(self):
        games=[dict(winner=w,turf_pp=[1.,2.],hud_downs=[0,1],environmental_downs=[0,0]) for w in (0,1,None)]
        r=summary(games,[0,1,1])
        self.assertEqual(r['strength'],[.25,.75])
        self.assertEqual(r['win_rate'],[0.,.5])

    def test_final_report_rejects_partial_grid(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            source=dict(public_library_sha256={})
            (out/'sources.json').write_text(json.dumps(source))
            (out/'plan.json').write_text(json.dumps(dict(sources_sha256=sha256(out/'sources.json'),scenarios=scenarios())))
            with self.assertRaisesRegex(ValueError,'incomplete/duplicate'):collect(out)

    def test_bo3_same_seat_weighting_separate_from_balanced_direction(self):
        native=[dict(stage=s,role_to_policy=[1,0],outcome='a',turf_pp=[20.,10.],
                     hud_downs=[0,0],environmental_downs=[0,0]) for s in (1,2,3)]
        simulated=[dict(**p,winner=0 if p['swap'] else 1,
                        turf_ratio_by_role=[.2,.1] if p['swap'] else [.1,.2],
                        hud_downs=[0,0],environmental_downs=[0,0],mechanics={},unsupported={},
                        trajectory_sha256=str((p['stage'],p['swap'],p['seed']))) for p in scenarios()]
        result=compare_pair(native,simulated)
        self.assertTrue(result['same_direction'])
        self.assertFalse(result['same_direction_balanced'])
        self.assertEqual(result['simulated_native_strata_weighted']['strength'],[1.,0.])
        for value in result['simulated_balanced']['strength']:self.assertAlmostEqual(value,.5)

    def test_scheduler_keeps_same_complete_grid_and_limits_workers(self):
        from .ranking_schedule import pending,main
        from .ranking_sources import PAIRS
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            names={name for pair in PAIRS.values() for name in pair}
            source=dict(policies={n:dict(directory_sha256=n) for n in names})
            (out/'sources.json').write_text(json.dumps(source))
            plan=dict(sources_sha256=sha256(out/'sources.json'),sim_source_sha256={},
                      scenarios=scenarios(),frames=10800)
            (out/'plan.json').write_text(json.dumps(plan))
            with patch('sim.ranking_schedule.core_hashes',return_value={}):jobs=pending(out)
            self.assertEqual(len(jobs),36)
            self.assertEqual(len({j['name'] for j in jobs}),36)
            self.assertTrue(all(j['pair']=='R4' for j in jobs[:6]))
            for pair in PAIRS:
                selected=[p for j in jobs if j['pair']==pair for p in j['plans']]
                self.assertCountEqual(selected,scenarios())
        with self.assertRaisesRegex(ValueError,'one or two'):main(workers=3)

    def test_native_input_attempts_are_edges_and_full_hold_candidates(self):
        import numpy as np
        from .ranking_input_audit import attempts
        actions=np.zeros((50,2,13))
        actions[:21,0,7]=1;actions[21,0,1]=1
        actions[:20,1,7]=1;actions[20,1,1]=1  # adjacent non-full counterexample
        actions[2:4,0,9]=1;actions[25,0,10]=1
        actions[30:34,0,8]=1;actions[31:33,0,11]=1
        self.assertEqual(attempts(actions),dict(R_press=1,R_release=1,RS_press=1,ZL_B_edge=1,
                                               full_forward_release_candidate=1))


if __name__=='__main__':unittest.main()
