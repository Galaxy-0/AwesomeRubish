#!/usr/bin/env python3
"""BO3 semantics and immutable version capture, without starting game rooms."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.config import PolicySpec
from arena.scoring import compare_scores
from arena.schedule import schedule
from arena.t1 import fixtures,summarize,run_round
from arena.versions import snapshot_policy,loader_slots
from arena.runner import link_load_slots

module=importlib.util.spec_from_file_location('t1_proficiency',ROOT/'tests/proficiency.py')
proficiency=importlib.util.module_from_spec(module);module.loader.exec_module(proficiency)


def match(fixture,outcome='a',**updates):
    roles=fixture['roles'];winning_seat=roles.index(0 if outcome=='a' else 1)
    scores=[40.,40.] if outcome=='draw' else [60. if n==winning_seat else 40. for n in (0,1)]
    hud={'player_0':dict(enemy_hud_downs=2,own_hud_downs=1,enemy_environmental_downs=0,own_environmental_downs=0),
         'player_1':dict(enemy_hud_downs=1,own_hud_downs=2,enemy_environmental_downs=0,own_environmental_downs=0)}
    result=dict(round=fixture['round'],stage=fixture['stage'],attempt=fixture.get('attempt',0),
                role_to_policy=roles,passed=True,errors=[],artifacts='test',hud_by_role=hud,
                host_pids=[100+fixture['round']*2,101+fixture['round']*2],
                controlled_start_wall=10.,last_progress_wall=20.,wall_seconds=30.,controlled_seconds=10.,
                **compare_scores(scores,scores[::-1],roles))
    result.update(updates);return result


class T1Tests(unittest.TestCase):
    def temporary(self):return tempfile.TemporaryDirectory(dir=ROOT/'work/tests')

    def test_every_map_alternates_and_balances_over_rounds(self):
        for number in range(8):
            tasks=fixtures(number);self.assertEqual([t['stage'] for t in tasks],[1,2,3])
            self.assertEqual([t['round'] for t in tasks],[0,1,2])
            self.assertTrue(all(t['roles']==([0,1] if number%2==0 else [1,0]) for t in tasks))
        for stage in (1,2,3):
            seats=[next(t for t in fixtures(n) if t['stage']==stage)['roles'].index(0) for n in range(8)]
            self.assertEqual(seats.count(0),4);self.assertEqual(seats.count(1),4)
        for number in (-1,1.5,True):
            with self.assertRaises(ValueError):fixtures(number)

    def test_summary_winner_scores_and_hud_are_policy_not_seat(self):
        for number in (0,1):
            report=dict(round=number,passed=True,policies=['rush','high-ground'],source_hashes=['x','y'],errors=[],
                        matches=[match(t,outcome=o) for t,o in zip(fixtures(number),('a','b','b'))])
            summary=summarize(report);self.assertEqual(summary['round_winner'],'b')
            self.assertEqual(summary['round_winner_name'],'high-ground')
            self.assertEqual(summary['wins'],dict(a=1,b=2,draw=0))
            self.assertEqual(summary['games'][0]['score_by_policy'],dict(a=60.,b=40.))
            self.assertEqual(summary['games'][0]['hud_by_policy']['a']['enemy_hud_downs'],2 if number==0 else 1)

    def test_pending_draw_and_void_do_not_invent_a_round_winner(self):
        tasks=fixtures(1);report=dict(round=1,passed=False,policies=['a','b'],source_hashes=['x','y'],errors=[],matches=[])
        self.assertIsNone(summarize(report)['round_winner'])
        report['matches']=[match(t,o) for t,o in zip(tasks,('a','b','draw'))]
        report['matches'].insert(0,match(tasks[0],passed=False,void=True,outcome=None))
        summary=summarize(report);self.assertEqual(summary['round_winner'],'draw')
        self.assertEqual(summary['void_attempts'],1);self.assertEqual(len(summary['games']),3)

    def test_void_retries_exact_map_and_seat_without_stopping_peers(self):
        seen=[];stop=threading.Event();barrier=threading.Barrier(3)
        def play(task):
            seen.append(dict(task))
            if task['attempt']==0:barrier.wait(3)
            if task['round']==0 and task['attempt']==0:return match(task,passed=False,void=True)
            self.assertFalse(stop.is_set());return match(task)
        with ThreadPoolExecutor(max_workers=3) as pool:
            rows,reason=schedule(fixtures(3),lambda t:pool.submit(play,t),stop,lambda *x:None,3,float('inf'))
        self.assertIsNone(reason);self.assertEqual(sum(r['passed'] for r in rows),3)
        retried=[t for t in seen if t['round']==0]
        self.assertEqual(retried[0]['stage'],retried[1]['stage']);self.assertEqual(retried[0]['roles'],retried[1]['roles'])
        self.assertEqual([t['attempt'] for t in retried],[0,1])

    def test_special_flag_rejected_before_snapshot_or_room_start(self):
        with patch.dict(os.environ,DM_TEST_SPECIAL='full'),patch('arena.t1.snapshot_policy') as snapshot:
            with self.assertRaisesRegex(ValueError,'forbidden'):run_round('missing','missing',1,'unused')
            snapshot.assert_not_called()
            with self.assertRaisesRegex(ValueError,'natural meter'):proficiency.run('missing','unused')

    def test_direct_aim_fixture_rejected_before_any_runtime_or_policy_io(self):
        from arena.runner import tournament,run_match
        from rl.native_start import validate_runtime
        for key,value in [('DM_TEST_AIM','1'),('DM_TEST_AIM_FILE','/private/fixture-only')]:
            with patch.dict(os.environ,{key:value}),patch('arena.t1.snapshot_policy')as snapshot:
                with self.assertRaisesRegex(ValueError,'DM_TEST_AIM'):run_round('missing','missing',1,'unused')
                with self.assertRaisesRegex(ValueError,'DM_TEST_AIM'):tournament('missing','missing')
                with self.assertRaisesRegex(ValueError,'DM_TEST_AIM'):run_match({})
                with self.assertRaisesRegex(ValueError,'DM_TEST_AIM'):proficiency.run('missing','unused')
                with self.assertRaisesRegex(ValueError,'DM_TEST_AIM'):validate_runtime('missing','missing')
                snapshot.assert_not_called()

    def test_snapshot_preserves_hash_and_author_updates_do_not_touch_copy(self):
        with self.temporary() as directory:
            root=Path(directory);source=root/'source';shutil.copytree(ROOT/'arena/policies/rush',source)
            old=PolicySpec.load(source);captured=snapshot_policy(source,root/'copy')
            self.assertEqual(old.source_sha256,captured.source_sha256)
            with (source/'policy.py').open('a') as stream:stream.write('\n# author new version\n')
            self.assertNotEqual(PolicySpec.load(source).source_sha256,captured.source_sha256)
            self.assertEqual(PolicySpec.load(captured.root).source_sha256,captured.source_sha256)
            with self.assertRaises(ValueError):snapshot_policy(source,source/'recursive')

    def test_snapshot_does_not_follow_symlink_to_other_policy(self):
        with self.temporary() as directory:
            root=Path(directory);source=root/'source';shutil.copytree(ROOT/'arena/policies/rush',source)
            (source/'foreign').symlink_to(ROOT/'arena/policies/high-ground',target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'symlink'):snapshot_policy(source,root/'copy')

    def test_shared_loader_inodes_and_independent_activation_markers(self):
        from types import SimpleNamespace
        with self.temporary() as directory:
            root=Path(directory);a=loader_slots(root/'shared');b=loader_slots(root/'shared')
            self.assertEqual(a,b)
            for name in ('round','proficiency'):
                out=root/name;(out/'load-slots').mkdir(parents=True);link_load_slots(SimpleNamespace(out=out),a)
            (root/'round/load-slots/active').touch()
            self.assertFalse((root/'proficiency/load-slots/active').exists())
            self.assertEqual((root/'round/load-slots/slot-0').stat().st_ino,(root/'proficiency/load-slots/slot-0').stat().st_ino)

    def test_orchestrator_uses_captured_revision_even_if_author_updates(self):
        def executor(**kwargs):return ThreadPoolExecutor(max_workers=3)
        with self.temporary() as directory:
            root=Path(directory);source=root/'author';shutil.copytree(ROOT/'arena/policies/rush',source)
            old=PolicySpec.load(source).source_sha256
            def play(task):
                if task['round']==0:
                    with (source/'policy.py').open('a') as stream:stream.write('\n# concurrent author update\n')
                self.assertNotEqual(Path(task['policy_paths'][0]),source)
                return match(task)
            with patch('arena.t1.ProcessPoolExecutor',side_effect=executor),patch('arena.t1.run_match',side_effect=play):
                report=run_round(source,ROOT/'arena/policies/high-ground',1,root/'out',shared_slots=root/'slots')
            self.assertTrue(report['passed'],report['errors']);self.assertEqual(report['source_hashes'][0],old)
            self.assertNotEqual(PolicySpec.load(source).source_sha256,old)
            self.assertEqual(json.loads((root/'out/summary.json').read_text())['round_winner'],'a')

    def test_proficiency_full_and_smoke_cover_all_three_scenarios(self):
        for repeats,expected in ((1,5),(2,9),(3,13)):
            jobs=proficiency.episodes(repeats)
            count=sum(proficiency.episode_repeats(scenario,repeats)*(len(distances) if distances else 1) for scenario,distances in jobs)
            self.assertEqual(count,expected)
            self.assertEqual(sum(s=='stationary' for s,_ in jobs),repeats)
            self.assertTrue(all(proficiency.episode_repeats(s,repeats)==1 for s,_ in jobs if s=='stationary'))
            self.assertEqual([d for s,ds in jobs if s=='lateral' for d in ds],[6.,12.,18.])


if __name__=='__main__':unittest.main()
